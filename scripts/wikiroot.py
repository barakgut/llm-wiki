"""Locate the wiki a command applies to. A wiki is a folder holding a `.llm-wiki/` directory."""
import os
from pathlib import Path

MARKER = ".llm-wiki"
PLUGIN = Path(__file__).resolve().parents[1]
DEPTH = 4  # levels searched below the start directory
SKIP = {"node_modules", "vendor", "venv", "dist", "build", "target", "__pycache__"}


def below(base):
    """Wikis under `base`, at most DEPTH levels down. Hidden and SKIP directories are passed over; a wiki is not searched."""
    found, level = [], [str(base)]
    for _ in range(DEPTH):
        deeper = []
        for d in level:
            try:
                subs = sorted(e.path for e in os.scandir(d)
                              if e.is_dir(follow_symlinks=False) and not e.name.startswith(".") and e.name not in SKIP)
            except OSError:
                continue
            for s in subs:
                if os.path.isdir(os.path.join(s, MARKER)):
                    found.append(Path(s))
                else:
                    deeper.append(s)
        level = deeper
    return found


def find_roots(start=None):
    """$LLM_WIKI_ROOT, else the nearest ancestor of `start` (default: cwd), else of $CLAUDE_PROJECT_DIR,
    else the wikis below `start`, else below $CLAUDE_PROJECT_DIR. More than one entry means the choice is open."""
    env = os.environ.get("LLM_WIKI_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        return [p] if (p / MARKER).is_dir() else []
    bases = [Path(b).expanduser().resolve() for b in (start or os.getcwd(), os.environ.get("CLAUDE_PROJECT_DIR")) if b]
    for p in bases:
        for d in (p, *p.parents):
            if (d / MARKER).is_dir():
                return [d]
    for p in dict.fromkeys(bases):
        found = below(p)
        if found:
            return found
    return []


def find_root(start=None):
    """The one wiki `find_roots` settles on, else None."""
    roots = find_roots(start)
    return roots[0] if len(roots) == 1 else None


def shown(root, rel):
    """A wiki-relative path as printed: relative to the current directory, so it can be opened as is."""
    return Path(os.path.relpath(Path(root) / rel)).as_posix()


def given(root, path):
    """A path argument: relative to the current directory, or to the wiki root when nothing is there."""
    p = Path(path).expanduser()
    if not p.is_absolute() and not p.exists() and (Path(root) / p).exists():
        p = Path(root) / p
    return p.resolve()


def kit(kind, name, root=None):
    """A template or reference: the wiki's own copy in .llm-wiki/<kind>/ wins over the plugin's."""
    if root and (root / MARKER / kind / name).is_file():
        return root / MARKER / kind / name
    return PLUGIN / kind / name
