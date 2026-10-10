#!/usr/bin/env python3
"""llm-wiki init - scaffold a new, empty LLM wiki, or adopt an existing folder.

  llm-wiki init                       the current directory
  llm-wiki init ~/wikis/research --name "Research" --git

Creates raw/, wiki/, AGENTS.md (the schema), .llm-wiki/ (the marker), .gitignore and
.claude/settings.json (lets the agent run the llm-wiki CLI without a prompt).
Existing files are never overwritten: whatever is already there is kept and listed.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from wikiroot import MARKER, PLUGIN

TEMPLATES = PLUGIN / "templates"
DIRS = ["raw/assets", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/analyses"]
LEGACY = [".claude/scripts/wiki.py", ".claude/hooks/guard.py", ".claude/skills/wiki-ingest"]


def main():
    ap = argparse.ArgumentParser(prog="llm-wiki init", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default=".", help="directory of the wiki (default: current; created if missing)")
    ap.add_argument("--name", help="wiki name for the AGENTS.md heading (default: from the directory name)")
    ap.add_argument("--git", action="store_true", help="git init the wiki")
    a = ap.parse_args()

    target = Path(a.target).expanduser().resolve()
    if target == PLUGIN or PLUGIN in target.parents:
        sys.exit("target must be outside the plugin")
    name = a.name or target.name.replace("-", " ").replace("_", " ").title()
    today = datetime.date.today().isoformat()
    made, kept = [], []

    def write(rel, text):
        dst = target / rel
        if dst.exists():
            kept.append(rel)
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
        made.append(rel)

    tpl = lambda f: (TEMPLATES / f).read_text(encoding="utf-8")
    fresh = not (target / "wiki").exists()
    for d in DIRS:
        if not (target / d).is_dir():
            (target / d).mkdir(parents=True)
            (target / d / ".gitkeep").touch()
    write(f"{MARKER}/config.json", json.dumps({"name": name, "schema": 1, "created": today}, indent=1) + "\n")
    write("AGENTS.md", tpl("AGENTS.md").replace("{{name}}", name))
    write(".gitignore", tpl("gitignore"))
    write(".claude/settings.json", tpl("settings.json"))
    write("wiki/overview.md", tpl("overview.md").replace("{{date}}", today))

    env = dict(os.environ, LLM_WIKI_ROOT=str(target), PYTHONDONTWRITEBYTECODE="1")
    cli = [sys.executable, str(PLUGIN / "scripts" / "wiki.py")]
    subprocess.run(cli + ["index", "-q"], check=True, env=env)
    subprocess.run(cli + ["log", "schema", "Scaffold created" if fresh else "Adopted by the llm-wiki plugin"],
                   check=True, capture_output=True, env=env)
    if a.git and not (target / ".git").exists():
        subprocess.run(["git", "init", "-q", str(target)], check=True)

    print(f"{'created' if fresh else 'adopted'} {target}")
    if made:
        print("  wrote: " + ", ".join(made))
    if kept:
        print("  kept (already there): " + ", ".join(kept))
    if ".claude/settings.json" in kept:
        print('  add to .claude/settings.json to skip permission prompts: "permissions": {"allow": ["Bash(llm-wiki:*)"]}')
    if any((target / p).exists() for p in LEGACY):
        print("  legacy in-repo tooling found: remove .claude/{skills,agents,hooks,scripts,references} and the hooks in\n"
              "  .claude/settings.json, or both copies will run. AGENTS.md was kept - compare it with "
              f"{TEMPLATES / 'AGENTS.md'}")
    print(f"  next: cd {target} && claude   # drop sources into raw/, then /llm-wiki:ingest")
    if not shutil.which("pdftotext"):
        print("  note: PDF ingest needs poppler-utils (pdfinfo, pdftotext, pdfimages, pdftoppm)")


if __name__ == "__main__":
    main()
