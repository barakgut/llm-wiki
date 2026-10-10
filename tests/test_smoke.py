"""End-to-end smoke test: scaffold a wiki, file pages, lint, and exercise the hooks. Stdlib only.

  python3 -m unittest discover -s tests -v
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(PLUGIN / "bin" / "llm-wiki")]
TODAY = datetime.date.today().isoformat()


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve() / "my-wiki"
        cls.env = {k: v for k, v in os.environ.items() if k not in ("LLM_WIKI_ROOT", "CLAUDE_PROJECT_DIR")}
        r = subprocess.run(CLI + ["init", str(cls.root)], capture_output=True, text=True, env=cls.env)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cli(self, *args, cwd=None):
        return subprocess.run(CLI + list(args), capture_output=True, text=True, cwd=cwd or self.root, env=self.env)

    def hook(self, script, payload, cwd=None):
        return subprocess.run([sys.executable, str(PLUGIN / "hooks" / script)], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=cwd or self.root, env=self.env)

    def test_1_scaffold(self):
        for rel in (".llm-wiki/config.json", "AGENTS.md", ".claude/settings.json", ".gitignore",
                    "wiki/overview.md", "wiki/index.md", "wiki/log.md", "raw/assets"):
            self.assertTrue((self.root / rel).exists(), rel)
        self.assertTrue((self.root / "AGENTS.md").read_text().startswith("# My Wiki - LLM wiki"))
        self.assertEqual(self.cli("lint").returncode, 0)

    def test_2_init_keeps_existing_files(self):
        (self.root / "AGENTS.md").write_text("# mine\n")
        r = self.cli("init", str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("kept", r.stdout)
        self.assertEqual((self.root / "AGENTS.md").read_text(), "# mine\n")

    def test_3_pages_search_links_lint(self):
        (self.root / "raw" / "memex.md").write_text("Vannevar Bush described the memex in 1945.\n")
        self.assertIn("raw/memex.md", self.cli("pending").stdout)
        r = self.cli("new", "source", "As We May Think", "--slug", "bush-1945", "--raw", "raw/memex.md",
                     "--summary", "Proposes the memex")
        self.assertEqual(r.stdout.strip(), "wiki/sources/bush-1945.md", r.stderr)
        r = self.cli("new", "concept", "Memex", "--sources", "bush-1945", "--summary", "A desk that stores trails")
        self.assertEqual(r.returncode, 0, r.stderr)
        filler = " ".join(["word"] * 40)
        with (self.root / "wiki/sources/bush-1945.md").open("a") as f:
            f.write(f"\nIntroduces [[memex]]. {filler}\n")
        with (self.root / "wiki/concepts/memex.md").open("a") as f:
            f.write(f"\nTrails between documents [[bush-1945]]. {filler}\n")
        self.assertIn("wiki/concepts/memex.md", self.cli("search", "memex").stdout)
        self.assertIn("wiki/sources/bush-1945.md", self.cli("links", "memex", cwd=self.root / "wiki").stdout)
        r = self.cli("lint")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("(nothing pending)", self.cli("pending").stdout)
        self.assertIn("3 pages", self.cli("index").stdout)

    def test_4_outside_a_wiki(self):
        out = self.root.parent
        self.assertNotEqual(self.cli("lint", cwd=out).returncode, 0)
        r = self.cli("stats", "--hook", cwd=out)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("# Page formats", self.cli("ref", "page-formats", cwd=out).stdout)
        (out / "raw").mkdir(exist_ok=True)
        (out / "raw" / "x.md").write_text("x")
        r = self.hook("guard.py", {"tool_name": "Bash", "tool_input": {"command": "rm raw/x.md"}, "cwd": str(out)}, cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_5_guard(self):
        raw = self.root / "raw" / "memex.md"
        deny = [("Edit", {"file_path": str(raw)}), ("Write", {"file_path": str(raw)}),
                ("Edit", {"file_path": "wiki/index.md"}), ("Write", {"file_path": "wiki/log.md"}),
                ("Bash", {"command": "rm raw/memex.md"}), ("Bash", {"command": "echo x > raw/memex.md"}),
                ("Bash", {"command": "cd raw && mv memex.md other.md"}), ("Bash", {"command": "sed -i s/a/b/ wiki/log.md"})]
        allow = [("Write", {"file_path": "raw/new-source.md"}), ("Write", {"file_path": "raw/assets/p/notes/p001-015.md"}),
                 ("Edit", {"file_path": "wiki/overview.md"}), ("Bash", {"command": "cat raw/memex.md"}),
                 ("Bash", {"command": "llm-wiki log note \"x\""}), ("Bash", {"command": "cp /etc/hostname raw/host.txt"})]
        for tool, inp in deny:
            r = self.hook("guard.py", {"tool_name": tool, "tool_input": inp, "cwd": str(self.root)})
            self.assertEqual(r.returncode, 2, (tool, inp))
            self.assertIn("BLOCKED", r.stderr)
        for tool, inp in allow:
            r = self.hook("guard.py", {"tool_name": tool, "tool_input": inp, "cwd": str(self.root)})
            self.assertEqual(r.returncode, 0, (tool, inp, r.stderr))

    def test_6_post_edit(self):
        page = self.root / "wiki" / "concepts" / "bad.md"
        page.write_text("no frontmatter\n")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(page)}, "cwd": str(self.root)}
        r = self.hook("post_edit.py", payload)
        self.assertEqual(r.returncode, 2)
        self.assertIn("frontmatter", r.stderr)
        page.write_text(f"---\ntitle: Bad\ntype: concept\nsummary: Now fine\ncreated: {TODAY}\nupdated: {TODAY}\n---\n# Bad\n")
        self.assertEqual(self.hook("post_edit.py", payload).returncode, 0)
        self.assertIn("[[bad|Bad]]", (self.root / "wiki" / "index.md").read_text())
        page.unlink()
        self.cli("index")

    def test_7_template_override(self):
        d = self.root / ".llm-wiki" / "templates"
        d.mkdir()
        (d / "entity.md").write_text("---\ntitle: {{title}}\ntype: entity\nsummary: {{summary}}\ncreated: {{date}}\n"
                                     "updated: {{date}}\n---\n# {{h1}}\n\n## Custom section\n")
        self.cli("new", "entity", "Vannevar Bush")
        self.assertIn("## Custom section", (self.root / "wiki/entities/vannevar-bush.md").read_text())


if __name__ == "__main__":
    unittest.main()
