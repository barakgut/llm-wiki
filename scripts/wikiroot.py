"""Locate the wiki a command applies to. A wiki is a folder holding a `.llm-wiki/` directory."""
import os
from pathlib import Path

MARKER = ".llm-wiki"
PLUGIN = Path(__file__).resolve().parents[1]
DEPTH = 4  # levels searched below the start directory
LIMIT = 2000  # directories one search looks at, so a hook stays quick in a large tree
SKIP = {"node_modules", "vendor", "venv", "dist", "build", "target", "__pycache__"}


def above(path):
    """The nearest wiki at or above `path`, else None."""
    p = Path(path)
    return next((d for d in (p, *p.parents) if (d / MARKER).is_dir()), None)


def below(base, done=()):
    """Wikis under `base`, at most DEPTH levels down, nearest first, and whether LIMIT cut the search short.
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
                    return found, True
                seen += 1
                if os.path.isdir(os.path.join(s, MARKER)):
                    found.append(Path(s))
                else:
                    deeper.append(s)
        level = deeper
    return found, False


def find_roots(start=None):
    """$LLM_WIKI_ROOT, else the nearest ancestor of `start` (default: cwd), else of $CLAUDE_PROJECT_DIR,
    else the wikis below `start`, else below $CLAUDE_PROJECT_DIR. Returns them with whether the search below was
    cut short. More than one wiki, or a search cut short, means the choice is open."""
    env = os.environ.get("LLM_WIKI_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        return ([p] if (p / MARKER).is_dir() else []), False
    bases = [Path(b).expanduser().resolve() for b in (start or os.getcwd(), os.environ.get("CLAUDE_PROJECT_DIR")) if b]
    for p in bases:
        d = above(p)
        if d:
            return [d], False
    done, cut = [], False
    for p in dict.fromkeys(bases):
        found, short = below(p, done)
        cut = cut or short
        if found:
            return found, cut
        done.append(str(p))
    return [], cut


def find_root(start=None):
    """The one wiki `find_roots` settles on, else None."""
    roots, cut = find_roots(start)
    return roots[0] if len(roots) == 1 and not cut else None


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


def unsettled(roots, cut):
    """The error when `find_roots` settles on no single wiki."""
    found = "\n".join(f"  {shown(r, '.')}" for r in roots)
    if cut:
        return (f"the search for a wiki stopped after {LIMIT:,} directories - cd into the wiki, or set LLM_WIKI_ROOT"
                + (f"; found so far:\n{found}" if roots else ""))
    if roots:
        return "several wikis below this directory - cd into one, or set LLM_WIKI_ROOT:\n" + found
    return "no llm-wiki here, above or below (no .llm-wiki/) - cd into one, or run: llm-wiki init"


def kit(kind, name, root=None):
    """A template or reference: the wiki's own copy in .llm-wiki/<kind>/ wins over the plugin's.
    A copy that is a symlink out of .llm-wiki/ is not the wiki's own."""
    if root:
        own = root / MARKER / kind / name
        if own.is_file() and root / MARKER in own.resolve().parents:
            return own
    return PLUGIN / kind / name
