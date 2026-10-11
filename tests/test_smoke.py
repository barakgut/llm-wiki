"""End-to-end smoke test: scaffold a wiki, file pages, lint, and exercise the hooks. Stdlib only.

  python3 -m unittest discover -s tests -v
"""
import datetime
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
TODAY = datetime.date.today().isoformat()
PDF_PAGE = b"BT /F1 12 Tf 72 720 Td (The ledger is event sourced.) Tj ET"
PAGE = "---\ntitle: {0}\ntype: concept\nsummary: About {0}\ncreated: {1}\nupdated: {1}\n---\n# {0}\n"


def pdf_bytes():
    """A one-page PDF with a text layer."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(PDF_PAGE), PDF_PAGE),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, at = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        at.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    xref = b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % a for a in at)
    return out + xref + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, len(out))


class Base(unittest.TestCase):
    """A temporary wiki at `wiki`, with commands run from `cwd` (the session root)."""
    wiki = cwd = "my-wiki"
    loose = False  # the tooling as loose files under the session root's .claude/, not at the repository

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.top = Path(cls.tmp.name).resolve()
        cls.root = cls.top / cls.wiki
        cls.here = cls.top / cls.cwd
        cls.here.mkdir(parents=True, exist_ok=True)
        cls.kit = PLUGIN
        if cls.loose:
            cls.kit = cls.here / ".claude"
            for d in ("skills", "agents", "hooks", "scripts", "bin", "references", "templates"):
                shutil.copytree(PLUGIN / d, cls.kit / d, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy(PLUGIN / "templates" / "project-settings.json", cls.kit / "settings.json")
        cls.env = {k: v for k, v in os.environ.items()
                   if k not in ("LLM_WIKI_ROOT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_ENV_FILE")}
        r = cls.run_cli("init", str(cls.root))
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def run_cli(cls, *args, cwd=None, env=None):
        return subprocess.run([sys.executable, str(cls.kit / "bin" / "llm-wiki"), *args], capture_output=True, text=True,
                              cwd=cwd or cls.here, env=dict(cls.env, **(env or {})))

    def cli(self, *args, cwd=None, env=None):
        return self.run_cli(*args, cwd=cwd, env=env)

    def hook(self, script, payload, cwd=None):
        return subprocess.run([sys.executable, str(self.kit / "hooks" / script)], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=cwd or self.here, env=self.env)


class Smoke(Base):

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
        self.assertIn("  sources/bush-1945.md", self.cli("links", "memex", cwd=self.root / "wiki").stdout)
        r = self.cli("lint")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("(nothing pending)", self.cli("pending").stdout)
        self.assertIn("3 pages", self.cli("index").stdout)

    def test_4_outside_a_wiki(self):
        out = self.top / "elsewhere"
        out.mkdir()
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

    def test_8_ref_prints_the_skills(self):
        for name in ("ingest", "query", "lint"):
            self.assertIn(f"name: wiki-{name}", self.cli("ref", name).stdout)

    def test_9_session_start_puts_the_cli_on_path(self):
        env_file = self.top / "session-env.sh"
        for _ in range(2):
            self.assertEqual(self.cli("stats", "--hook", env={"CLAUDE_ENV_FILE": str(env_file)}).returncode, 0)
        self.assertEqual(env_file.read_text().count("export PATH="), 1)
        r = self.cli("stats", "--hook", env={"CLAUDE_ENV_FILE": str(self.top / "no-such-dir" / "env.sh")})
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        r = subprocess.run(["sh", "-c", f". {shlex.quote(str(env_file))}; cd /; llm-wiki ref"], capture_output=True, text=True,
                           env=self.env)
        self.assertIn("page-formats", r.stdout, r.stderr)

    def test_7_template_override(self):
        d = self.root / ".llm-wiki" / "templates"
        d.mkdir()
        (d / "entity.md").write_text("---\ntitle: {{title}}\ntype: entity\nsummary: {{summary}}\ncreated: {{date}}\n"
                                     "updated: {{date}}\n---\n# {{h1}}\n\n## Custom section\n")
        self.cli("new", "entity", "Vannevar Bush")
        self.assertIn("## Custom section", (self.root / "wiki/entities/vannevar-bush.md").read_text())

    def test_a_slug_stays_in_the_wiki(self):
        r = self.cli("new", "concept", "Escape", "--slug", "../../../escaped")
        self.assertEqual(r.stdout.strip(), "wiki/concepts/escaped.md", r.stderr)
        r = self.cli("new", "concept", "Absolute", "--slug", str(self.top / "abs"))
        self.assertEqual((r.returncode, Path(r.stdout.strip()).parent.as_posix()), (0, "wiki/concepts"), r.stderr)
        self.assertEqual([p for p in (self.top / "escaped.md", self.top / "abs.md") if p.exists()], [])
        r = self.cli("new", "concept", "No slug", "--slug", "../..")
        self.assertEqual(r.returncode, 1)
        self.assertIn("slug is empty", r.stderr)
        for p in self.root.glob("wiki/concepts/*esc*.md"):
            p.unlink()
        next(self.root.glob("wiki/concepts/*abs.md")).unlink()
        self.cli("index")

    def test_b_no_write_through_a_symlink(self):
        victim = self.top / "victim.txt"
        victim.write_text("mine\n")
        outside = self.top / "outside"
        outside.mkdir()
        page = self.root / "wiki" / "concepts" / "linked.md"
        for name, cmds in (("wiki/index.md", [("index",), ("new", "concept", "Via the index")]),
                           ("wiki/log.md", [("log", "note", "x")])):
            kept = (self.root / name).read_text()
            (self.root / name).unlink()
            (self.root / name).symlink_to(victim)
            page.write_text(PAGE.format("Linked", TODAY))
            payload = {"tool_name": "Write", "tool_input": {"file_path": str(page)}, "cwd": str(self.root)}
            self.hook("post_edit.py", payload)
            for cmd in cmds:
                r = self.cli(*cmd)
                self.assertEqual(r.returncode, 1, cmd)
                self.assertIn(f"not written: {name}", r.stderr)
            self.assertEqual(victim.read_text(), "mine\n", name)
            page.unlink()
            (self.root / name).unlink()
            (self.root / name).write_text(kept)
        index, overview = self.root / "wiki" / "index.md", self.root / "wiki" / "overview.md"
        kept, page_text = index.read_text(), overview.read_text()
        index.unlink()
        index.symlink_to(overview)  # a link that stays in the wiki still points at another file
        self.assertEqual(self.cli("index").returncode, 1)
        self.assertEqual(overview.read_text(), page_text)
        index.unlink()
        index.write_text(kept)
        (self.root / "wiki" / "analyses").rename(self.root / "wiki" / "analyses.kept")
        (self.root / "wiki" / "analyses").symlink_to(outside, target_is_directory=True)
        r = self.cli("new", "analysis", "Through a linked directory")
        self.assertEqual((r.returncode, list(outside.iterdir())), (1, []), r.stderr)
        (self.root / "wiki" / "analyses").unlink()
        (self.root / "wiki" / "analyses.kept").rename(self.root / "wiki" / "analyses")
        (self.root / "wiki").rename(self.root / "wiki.kept")
        (self.root / "wiki").symlink_to(outside, target_is_directory=True)
        for cmd in (("index",), ("log", "note", "x"), ("new", "concept", "Through a linked wiki")):
            self.assertEqual(self.cli(*cmd).returncode, 1, cmd)
        self.assertEqual(list(outside.iterdir()), [])
        (self.root / "wiki").unlink()
        (self.root / "wiki.kept").rename(self.root / "wiki")
        self.assertEqual(self.cli("index").returncode, 0)
        ref = self.root / ".llm-wiki" / "references"
        ref.mkdir(exist_ok=True)
        (ref / "page-formats.md").symlink_to(victim)
        r = self.cli("ref", "page-formats")
        self.assertIn("# Page formats", r.stdout)
        self.assertNotIn("mine", r.stdout)
        (ref / "page-formats.md").unlink()
        (ref / "page-formats.md").write_text("the wiki's own\n")
        self.assertEqual(self.cli("ref", "page-formats").stdout, "the wiki's own\n")
        (ref / "page-formats.md").unlink()

    def test_c_hint_line_only_from_the_hook(self):
        self.assertIn("wiki-query skill", self.cli("stats", "--hook").stdout.splitlines()[-1])
        self.assertNotIn("wiki-query skill", self.cli("stats").stdout)



class Project(Base):
    """The wiki as a subfolder of a project; every command runs from the project root."""
    wiki, cwd = "proj/docs/wiki", "proj"

    def page(self, slug, root=None):
        path = (root or self.root) / "wiki" / "concepts" / f"{slug}.md"
        path.write_text(PAGE.format(slug.title(), TODAY))
        return path

    def test_1_found_from_the_project_root(self):
        r = self.cli("stats")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("wiki at docs/wiki (schema: docs/wiki/AGENTS.md)", r.stdout.splitlines()[0])
        self.assertIn("wiki at docs/wiki", self.cli("stats", "--hook").stdout)
        sub = self.here / "src" / "deep"
        sub.mkdir(parents=True)
        r = self.cli("stats", cwd=sub, env={"CLAUDE_PROJECT_DIR": str(self.here)})
        self.assertIn("wiki at ../../docs/wiki", r.stdout)

    def test_2_paths_open_from_the_project_root(self):
        (self.root / "raw" / "adr-1.md").write_text("We chose event sourcing for the ledger.\n")
        self.assertEqual(self.cli("pending").stdout.strip(), "docs/wiki/raw/adr-1.md")
        for i, raw in enumerate(("raw/adr-1.md", "docs/wiki/raw/adr-1.md")):
            r = self.cli("new", "source", f"ADR 1 take {i}", "--raw", raw, "--summary", "Event sourcing for the ledger")
            page = self.here / r.stdout.strip()
            self.assertTrue(page.is_file(), r.stdout + r.stderr)
            self.assertIn("raw: raw/adr-1.md", page.read_text())
        self.page("ledger")
        hit = self.cli("search", "ledger", "--type", "concept").stdout.split()[1]
        self.assertTrue((self.here / hit).is_file(), hit)
        self.assertIn("docs/wiki/wiki/concepts/ledger.md", self.cli("links", "ledger").stdout)
        r = self.cli("lint")
        self.assertIn("docs/wiki/wiki/concepts/ledger.md:", r.stdout)
        bad = self.root / "wiki" / "concepts" / "bad.md"
        bad.write_text("no frontmatter\n")
        for form in ("wiki/concepts/", "docs/wiki/wiki/concepts/"):
            self.assertEqual(self.cli("check", form + "ledger.md").returncode, 0)
            r = self.cli("check", form + "bad.md")
            self.assertEqual(r.returncode, 1, form)
            self.assertTrue(r.stdout.startswith("docs/wiki/wiki/concepts/bad.md:"), r.stdout)
        bad.unlink()
        (self.here / "raw").mkdir()
        (self.here / "raw" / "adr-1.md").write_text("the project's own file\n")
        r = self.cli("new", "source", "The wiki's file, not the project's", "--raw", "raw/adr-1.md")
        self.assertIn("raw: raw/adr-1.md", (self.here / r.stdout.strip()).read_text())
        (self.here / "raw" / "only-here.md").write_text("not in the wiki\n")
        r = self.cli("new", "source", "Not a wiki source", "--raw", "raw/only-here.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--raw must be a file in the wiki", r.stderr)
        shutil.rmtree(self.here / "raw")
        for raw in ("wiki/index.md", "docs/wiki/AGENTS.md"):
            r = self.cli("new", "source", "In the wiki, not under raw", "--raw", raw)
            self.assertEqual(r.returncode, 1, raw)
            self.assertIn("--raw must be a file in the wiki, under docs/wiki/raw/", r.stderr)
        r = self.cli("new", "source", "A file yet to come", "--raw", "raw/nope.md", cwd=self.root / "wiki" / "sources")
        self.assertIn("raw: raw/nope.md", (self.root / "wiki" / "sources" / r.stdout.strip()).read_text(), r.stderr)
        (self.root / "wiki" / "sources" / r.stdout.strip()).unlink()
        inner = self.root / "raw" / "raw"
        inner.mkdir()
        (inner / "adr-1.md").write_text("a file the current directory reaches first\n")
        r = self.cli("new", "source", "Current directory wins", "--raw", "raw/adr-1.md", cwd=self.root / "raw")
        self.assertIn("raw: raw/raw/adr-1.md", (self.root / "raw" / r.stdout.strip()).read_text())
        shutil.rmtree(inner)

    def test_3_guard_from_the_project_root(self):
        (self.root / "raw" / "spec.md").write_text("spec\n")
        (self.here / "main.py").write_text("print(1)\n")
        deny = [("Bash", {"command": "rm docs/wiki/raw/spec.md"}), ("Bash", {"command": "echo x > docs/wiki/raw/spec.md"}),
                ("Bash", {"command": "cd docs/wiki && rm raw/spec.md"}), ("Edit", {"file_path": "docs/wiki/wiki/index.md"}),
                ("Edit", {"file_path": "docs/wiki/raw/spec.md"})]
        deny += [("Bash", {"command": c}) for c in (
            "(cd docs/wiki && rm raw/spec.md)", "{ cd docs/wiki; rm raw/spec.md; }", "pushd docs/wiki; rm raw/spec.md",
            "git -C docs/wiki rm raw/spec.md", "git --no-pager -C docs -C wiki rm raw/spec.md",
            "cat main.py >| docs/wiki/raw/spec.md", "dd if=main.py of=docs/wiki/raw/spec.md",
            "(rm docs/wiki/raw/spec.md)", 'rm "docs/wiki/raw/spec (1).md"')]
        allow = [("Edit", {"file_path": "main.py"}), ("Bash", {"command": "rm main.py"}),
                 ("Write", {"file_path": "docs/wiki/raw/new.md"}), ("Edit", {"file_path": "docs/wiki/wiki/overview.md"})]
        allow += [("Bash", {"command": c}) for c in (
            "(cd docs/wiki && cat raw/spec.md)", "pushd docs/wiki; ls raw", "git -C docs/wiki status",
            "git -C docs/wiki add raw/spec.md", "cat main.py >| out.txt", "dd if=docs/wiki/raw/spec.md of=copy.md",
            "dd if=main.py of=docs/wiki/raw/new.bin", "cat docs/wiki/raw/spec.md | wc -l")]
        for tool, inp in deny:
            r = self.hook("guard.py", {"tool_name": tool, "tool_input": inp, "cwd": str(self.here)})
            self.assertEqual(r.returncode, 2, (tool, inp))
        for tool, inp in allow:
            r = self.hook("guard.py", {"tool_name": tool, "tool_input": inp, "cwd": str(self.here)})
            self.assertEqual(r.returncode, 0, (tool, inp, r.stderr))

    def test_4_post_edit_from_the_project_root(self):
        page = self.root / "wiki" / "concepts" / "bad.md"
        page.write_text("no frontmatter\n")
        payload = {"tool_name": "Write", "tool_input": {"file_path": "docs/wiki/wiki/concepts/bad.md"}, "cwd": str(self.here)}
        r = self.hook("post_edit.py", payload)
        self.assertEqual(r.returncode, 2)
        self.assertIn("docs/wiki/wiki/concepts/bad.md", r.stderr)
        page.unlink()
        self.cli("index")

    def test_8_init_names_what_the_session_needs(self):
        r = self.cli("init", "notes/wiki")
        self.assertIn("next: drop sources into notes/wiki/raw/, then /wiki-ingest", r.stdout)
        self.assertIn('a session started here reads its own .claude/settings.json', r.stdout)
        self.assertNotIn("a session started here", self.cli("init", cwd=self.here / "notes/wiki").stdout)
        shutil.rmtree(self.here / "notes")

    def test_5_search_limits(self):
        for rel in ("a/b/c/d/too-deep", "node_modules/pkg", ".hidden/w"):
            d = self.top / "limits" / rel
            self.assertEqual(self.run_cli("init", str(d)).returncode, 0)
        r = self.cli("stats", "--hook", cwd=self.top / "limits")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.run_cli("init", str(self.top / "limits/a/b/c/ok")).returncode, 0)
        self.assertIn("wiki at a/b/c/ok", self.cli("stats", cwd=self.top / "limits").stdout)

    def test_6_two_wikis(self):
        two = self.top / "two"
        for name in ("docs/wiki", "notes"):
            self.assertEqual(self.run_cli("init", str(two / name)).returncode, 0)
        r = self.cli("lint", cwd=two)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/wiki", r.stderr)
        self.assertIn("notes", r.stderr)
        r = self.cli("stats", "--hook", cwd=two)
        self.assertEqual(r.returncode, 0)
        self.assertIn("several wikis", r.stdout)
        self.assertEqual(self.cli("lint", cwd=two, env={"LLM_WIKI_ROOT": str(two / "notes")}).returncode, 0)
        self.assertIn("several wikis", self.cli("pdf", "x.pdf", cwd=two).stderr)
        for name in ("docs/wiki", "notes"):
            (two / name / "raw" / "s.md").write_text("s\n")
            r = self.hook("guard.py", {"tool_name": "Bash", "tool_input": {"command": f"rm {name}/raw/s.md"}, "cwd": str(two)})
            self.assertEqual(r.returncode, 2, name)

    def test_7_large_tree(self):
        big = self.top / "big"
        for i in range(20):
            for j in range(20):
                for k in range(25):
                    d = big / f"pkg{i:02d}" / f"mod{j:02d}" / f"dir{k:02d}"
                    d.mkdir(parents=True)
                    (d / "f.py").touch()
        spec = importlib.util.spec_from_file_location("wikiroot_under_test", self.kit / "scripts" / "wikiroot.py")
        wikiroot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wikiroot)
        with mock.patch.dict(os.environ, dict(self.env, CLAUDE_PROJECT_DIR=str(big)), clear=True):
            for start in (big, big / "pkg00"):
                took = []
                for _ in range(5):
                    t = time.perf_counter()
                    self.assertEqual(wikiroot.find_roots(start), ([], True))
                    took.append(time.perf_counter() - t)
                self.assertLess(min(took), 0.05)
        self.assertEqual(wikiroot.find_roots(big / "pkg00"), ([], False))

        # a wiki the search does not reach: say the search was cut short, never "no wiki"
        far = big / "pkg19" / "mod19" / "wiki"
        self.assertEqual(self.run_cli("init", str(far)).returncode, 0)
        (far / "raw" / "s.md").write_text("s\n")
        r = self.cli("stats", cwd=big)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stopped after 2,000 directories", r.stderr)
        self.assertIn("LLM_WIKI_ROOT", r.stderr)
        r = self.cli("stats", "--hook", cwd=big)
        self.assertEqual(r.returncode, 0)
        self.assertIn("stopped after 2,000 directories", r.stdout)
        self.assertIn("stopped after 2,000 directories", self.cli("pdf", "x.pdf", cwd=big).stderr)
        rm = {"tool_name": "Bash", "tool_input": {"command": "rm pkg19/mod19/wiki/raw/s.md"}, "cwd": str(big)}
        self.assertEqual(self.hook("guard.py", rm, cwd=big).returncode, 2)
        self.assertIn("wiki at pkg19/mod19/wiki", self.cli("stats", cwd=big, env={"LLM_WIKI_ROOT": str(far)}).stdout)

        # a wiki it does reach is not taken for the only one
        near = big / "docs" / "wiki"
        self.assertEqual(self.run_cli("init", str(near)).returncode, 0)
        (near / "raw" / "s.md").write_text("s\n")
        r = self.cli("stats", cwd=big)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("stopped after 2,000 directories", r.stderr)
        self.assertIn("  docs/wiki", r.stderr)
        (near / "raw" / "x.pdf").touch()
        self.assertIn("stopped after 2,000 directories", self.cli("pdf", "docs/wiki/raw/x.pdf", cwd=big).stderr)
        r = self.cli("stats", "--hook", cwd=big)
        self.assertEqual(r.returncode, 0)
        self.assertIn("  docs/wiki", r.stdout)
        self.assertNotIn("wiki at", r.stdout)
        page = near / "wiki" / "concepts" / "bad.md"
        page.write_text("no frontmatter\n")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(page)}, "cwd": str(big)}
        self.assertEqual(self.hook("post_edit.py", payload, cwd=big).returncode, 2)
        for name in ("docs/wiki", "pkg19/mod19/wiki"):
            rm["tool_input"]["command"] = f"rm {name}/raw/s.md"
            self.assertEqual(self.hook("guard.py", rm, cwd=big).returncode, 2, name)
        rm["tool_input"]["command"] = "rm pkg00/mod00/dir00/f.py"
        self.assertEqual(self.hook("guard.py", rm, cwd=big).returncode, 0)
        self.assertIn("wiki at docs/wiki", self.cli("stats", cwd=big, env={"LLM_WIKI_ROOT": str(near)}).stdout)

    @unittest.skipUnless(shutil.which("pdftotext"), "needs poppler-utils")
    def test_9_pdf_from_the_project_root(self):
        (self.root / "raw" / "x.pdf").write_bytes(pdf_bytes())
        r = self.cli("pdf", "raw/x.pdf")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("-> docs/wiki/raw/assets/x/text.md;", r.stdout)
        self.assertIn("event sourced", (self.here / "docs/wiki/raw/assets/x/text.md").read_text())
        self.assertIn('llm-wiki pdf "docs/wiki/raw/x.pdf" --chunk 1', r.stdout)
        for form in ("raw/x.pdf", "docs/wiki/raw/x.pdf"):
            self.assertIn("docs/wiki/raw/x.pdf: 1 pages", self.cli("pdf", form, "--plan").stdout, form)
            lines = self.cli("pdf", form, "--chunk", "1").stdout.splitlines()
            self.assertIn("text:   Read docs/wiki/raw/assets/x/text.md", lines[1])
            images = [l.split()[0] for l in lines[3:-1]]
            self.assertTrue(images and all((self.here / i).is_file() for i in images), lines)
            self.assertTrue(lines[-1].split()[-1].startswith("docs/wiki/raw/assets/x/notes/"), lines[-1])
        shutil.rmtree(self.root / "raw" / "assets" / "x")
        (self.root / "raw" / "x.pdf").unlink()


class LooseSmoke(Smoke):
    loose = True

    def test_registered_hooks_exist(self):
        cfg = json.loads((self.kit / "settings.json").read_text())
        self.assertIn("Bash(llm-wiki:*)", cfg["permissions"]["allow"])
        plugin = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
        self.assertEqual(sorted(cfg["hooks"]), sorted(plugin))
        for event, groups in cfg["hooks"].items():
            self.assertEqual(groups[0].get("matcher"), plugin[event][0].get("matcher"))
            for h in groups[0]["hooks"]:
                script = shlex.split(h["command"].replace("${CLAUDE_PROJECT_DIR}", str(self.here)))[1]
                self.assertTrue(Path(script).is_file(), script)

    def test_session_start_command_runs(self):
        cmd = json.loads((self.kit / "settings.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=self.here,
                           env=dict(self.env, CLAUDE_PROJECT_DIR=str(self.here)))
        self.assertIn("wiki at .", r.stdout, r.stderr)


class LooseProject(Project):
    loose = True


if __name__ == "__main__":
    unittest.main()
