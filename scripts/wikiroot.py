"""Locate the wiki a command applies to. A wiki is a folder holding a `.llm-wiki/` directory."""
import os
from pathlib import Path

MARKER = ".llm-wiki"
PLUGIN = Path(__file__).resolve().parents[1]


def find_root(start=None):
    """$LLM_WIKI_ROOT, else the nearest ancestor of `start` (default: cwd), else of $CLAUDE_PROJECT_DIR."""
    env = os.environ.get("LLM_WIKI_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        return p if (p / MARKER).is_dir() else None
    for base in (start or os.getcwd(), os.environ.get("CLAUDE_PROJECT_DIR")):
        if not base:
            continue
        p = Path(base).expanduser().resolve()
        for d in (p, *p.parents):
            if (d / MARKER).is_dir():
                return d
    return None


def kit(kind, name, root=None):
    """A template or reference: the wiki's own copy in .llm-wiki/<kind>/ wins over the plugin's."""
    if root and (root / MARKER / kind / name).is_file():
        return root / MARKER / kind / name
    return PLUGIN / kind / name
