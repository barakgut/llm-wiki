"""Locate the wiki a command applies to. A wiki is a folder holding a `.llm-wiki/` directory."""
import os
from pathlib import Path

MARKER = ".llm-wiki"
PLUGIN = Path(__file__).resolve().parents[1]
DEPTH = 4  # levels searched below the start directory
LIMIT = 2000  # directories one search looks at, so a hook stays quick in a large tree
SKIP = {"node_modules", "vendor", "venv", "dist", "build", "target", "__pycache__"}


def below(base, done=()):
    """Wikis under `base`, at most DEPTH levels down and LIMIT directories looked at, nearest first.
    Hidden, SKIP and `done` directories are passed over; a wiki is not searched."""
    found, level, seen = [], [str(base)], 0
    for _ in range(DEPTH):
        deeper = []
        for d in level:
            try:
                subs = sorted(e.path for e in os.scandir(d)
                              if e.is_dir(follow_symlinks=False) and not e.name.startswith(".") and e.name not in SKIP
                              and e.path not in done)
            except OSError:
                continue
            for s in subs:
                if seen == LIMIT:
                    return found
                seen += 1
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
    done = []
    for p in dict.fromkeys(bases):
        found = below(p, done)
        if found:
            return found
        done.append(str(p))
    return []


def find_root(start=None):
    """The one wiki `find_roots` settles on, else None."""
    roots = find_roots(start)
    return roots[0] if len(roots) == 1 else None


def shown(root, rel):
    """A wiki-relative path as printed: relative to the current directory, so it can be opened as is."""
    return Path(os.path.relpath(Path(root) / rel)).as_posix()


def given(root, path):
    """A path argument: relative to the current directory, or to the wiki root when nothing is there
    or what is there lies outside the wiki."""
    p = Path(path).expanduser()
    here, there = p.resolve(), (Path(root) / p).resolve()
    if not p.is_absolute() and there.exists() and not (here.exists() and Path(root) in here.parents):
        return there
    return here


def several(roots):
    """The error for more than one wiki in reach."""
    return ("several wikis below this directory - cd into one, or set LLM_WIKI_ROOT:\n"
            + "\n".join(f"  {shown(r, '.')}" for r in roots))


def kit(kind, name, root=None):
    """A template or reference: the wiki's own copy in .llm-wiki/<kind>/ wins over the plugin's."""
    if root and (root / MARKER / kind / name).is_file():
        return root / MARKER / kind / name
    return PLUGIN / kind / name
