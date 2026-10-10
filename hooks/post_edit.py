#!/usr/bin/env python3
"""PostToolUse: validate the frontmatter of an edited wiki page and keep wiki/index.md current."""
import json
import os
import subprocess
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
from wikiroot import find_root  # noqa: E402

CLI = os.path.join(PLUGIN, "scripts", "wiki.py")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    path = (data.get("tool_input") or {}).get("file_path")
    if not path:
        return
    path = os.path.realpath(os.path.join(data.get("cwd") or os.getcwd(), path))
    root = find_root(os.path.dirname(path))
    if not root:
        return
    wiki = os.path.join(str(root), "wiki")
    if not path.startswith(wiki + os.sep) or not path.endswith(".md"):
        return
    if os.path.basename(path) in ("index.md", "log.md") and os.path.dirname(path) == wiki:
        return
    env = dict(os.environ, LLM_WIKI_ROOT=str(root), PYTHONDONTWRITEBYTECODE="1")
    check = subprocess.run([sys.executable, CLI, "check", path], capture_output=True, text=True, env=env)
    subprocess.run([sys.executable, CLI, "index", "-q"], capture_output=True, env=env)
    if check.returncode:
        sys.stderr.write("wiki page needs fixing:\n" + check.stdout + check.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
