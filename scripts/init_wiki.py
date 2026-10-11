#!/usr/bin/env python3
"""llm-wiki init - scaffold a new, empty LLM wiki, or adopt an existing folder.

  llm-wiki init                       the current directory
  llm-wiki init ~/wikis/research --name "Research" --git

Creates raw/, wiki/, AGENTS.md (the schema), .llm-wiki/ (the marker), .gitignore and
.claude/settings.json (lets a session started in the wiki run the llm-wiki CLI without a prompt).
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

from wikiroot import MARKER, PLUGIN, shown

TEMPLATES = PLUGIN / "templates"
DIRS = ["raw/assets", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/analyses"]


def main():
    ap = argparse.ArgumentParser(prog="llm-wiki init", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?", default=".", help="directory of the wiki (default: current; created if missing)")
    ap.add_argument("--name", help="wiki name for the AGENTS.md heading (default: from the directory name)")
    ap.add_argument("--git", action="store_true", help="git init the wiki")
    a = ap.parse_args()

    target = Path(a.target).expanduser().resolve()
    if target == PLUGIN or PLUGIN in target.parents:
        sys.exit("target must be outside the tooling")
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
    subprocess.run(cli + ["log", "schema", "Scaffold created" if fresh else "Adopted as an llm-wiki"],
                   check=True, capture_output=True, env=env)
    if a.git and not (target / ".git").exists():
        subprocess.run(["git", "init", "-q", str(target)], check=True)

    print(f"{'created' if fresh else 'adopted'} {target}")
    if made:
        print("  wrote: " + ", ".join(made))
    if kept:
        print("  kept (already there): " + ", ".join(kept))
    allow = '"permissions": {"allow": ["Bash(llm-wiki:*)"]}'
    if ".claude/settings.json" in kept:
        print(f"  add to {shown(target, '.claude/settings.json')} to skip permission prompts: {allow}")
    if target != Path.cwd().resolve():
        print(f"  a session started here reads its own .claude/settings.json; to skip permission prompts add: {allow}")
    print(f"  next: drop sources into {shown(target, 'raw')}/, then /wiki-ingest")
    if not shutil.which("pdftotext"):
        print("  note: PDF ingest needs poppler-utils (pdfinfo, pdftotext, pdfimages, pdftoppm)")


if __name__ == "__main__":
    main()
