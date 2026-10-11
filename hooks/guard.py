#!/usr/bin/env python3
"""PreToolUse guard. raw/ is immutable (new files only); wiki/index.md and wiki/log.md
change only through the llm-wiki CLI. Does nothing outside a wiki. A guard rail against slips, not a security boundary."""
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from wikiroot import above, find_roots  # noqa: E402

ROOTS = []  # the wikis in reach: one in the normal case
CUT = False  # the search for them was cut short, so a path is also asked for the wiki above it

MSG = {
    "raw": "raw/ is immutable: read sources, add new files, never change or remove existing ones. "
           "If a source really must change, ask the user to do it.",
    "index": "wiki/index.md is generated. Edit the page's frontmatter (title/summary), "
             "then run: llm-wiki index",
    "log": "wiki/log.md is append-only. Run: llm-wiki log <op> \"<title>\" -m \"<note>\"",
}
DESTRUCT = {"rm", "rmdir", "unlink", "truncate", "shred", "chmod", "chown"}
COPIERS = {"cp", "mv", "install", "ln", "rsync"}
PREFIX = {"sudo", "command", "env", "time", "nohup", "xargs"}
REDIR = re.compile(r">[>|]?\s*(?!&)([^\s;&|<>()]+)")


def resolve(p, cwd):
    return os.path.realpath(os.path.join(cwd, os.path.expanduser(p)))


def kind(path):
    up = above(path) if CUT else None
    for root in ROOTS + ([str(up)] if up else []):
        raw = os.path.join(root, "raw")
        if path == os.path.join(root, "wiki", "index.md"):
            return "index"
        if path == os.path.join(root, "wiki", "log.md"):
            return "log"
        if path == raw or path.startswith(raw + os.sep):
            # reading notes written during ingest are working files, not sources
            if re.match(r"assets/[^/]+/notes(/|$)", os.path.relpath(path, raw).replace(os.sep, "/")):
                return None
            return "raw"
    return None


def deny(k, what):
    sys.stderr.write(f"BLOCKED ({what}): {MSG[k]}\n")
    sys.exit(2)


def check_file(tool, path):
    k = kind(path)
    if not k:
        return
    if k == "raw" and tool == "Write" and not os.path.exists(path):
        return  # adding a new source is fine
    deny(k, f"{tool} {os.path.relpath(path)}")


def overwrites(dst, srcs, cwd):
    """Kind of protected path a copy/move/write to dst would clobber, else None."""
    p = resolve(dst, cwd)
    k = kind(p)
    if k in ("index", "log"):
        return k
    if k == "raw":
        if os.path.isdir(p):
            if any(os.path.exists(os.path.join(p, os.path.basename(s.rstrip("/")))) for s in srcs):
                return k
        elif os.path.exists(p):
            return k
    return None


def check_bash(command, cwd):
    for seg in re.split(r"&&|\|\||;|\n|(?<!>)\|", command):
        for target in REDIR.findall(seg):
            k = overwrites(target.strip("\"'"), [], cwd)
            if k:
                deny(k, f"redirect to {target}")
        seg = re.sub(r"^[\s({]+|[\s)]+$", "", REDIR.sub(" ", seg))  # ( cd dir && cmd )
        try:
            toks = shlex.split(seg)
        except ValueError:
            toks = seg.split()
        while toks and (toks[0] in PREFIX or re.match(r"^\w+=", toks[0])):
            toks.pop(0)
        if not toks:
            continue
        cmd, rest, at = os.path.basename(toks[0]), toks[1:], cwd
        while cmd == "git" and "-C" in rest[:-1]:
            i = rest.index("-C")
            at = resolve(rest[i + 1], at)
            del rest[i:i + 2]
        args = [t for t in rest if not t.startswith("-")]
        kinds = [kind(resolve(a, at)) for a in args]
        hit = next((k for k in kinds if k), None)
        what = " ".join(toks)[:80]

        if cmd in ("cd", "pushd") and args:
            cwd = resolve(args[0], cwd)
        elif cmd in DESTRUCT and hit:
            deny(hit, what)
        elif cmd in ("sed", "perl") and hit and any(re.match(r"^(-[a-zA-Z]*i|--in-place)", t) for t in rest):
            deny(hit, what)
        elif cmd in ("tee", "dd"):
            for a in args if cmd == "tee" else [t[3:] for t in rest if t.startswith("of=")]:
                k = overwrites(a, [], cwd)
                if k:
                    deny(k, what)
        elif cmd in COPIERS and len(args) >= 2:
            srcs, dst = args[:-1], args[-1]
            if cmd == "mv" and any(kinds[:-1]):
                deny(next(k for k in kinds[:-1] if k), what)
            k = overwrites(dst, srcs, cwd)
            if k:
                deny(k, what)
        elif cmd == "git" and args and args[0] in ("rm", "mv", "clean", "checkout", "restore") and "raw" in kinds[1:]:
            deny("raw", what)
        elif cmd == "find" and "raw" in kinds and {"-delete", "-exec", "-execdir"} & set(rest):
            deny("raw", what)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    global ROOTS, CUT
    path = inp.get("file_path") or inp.get("notebook_path")
    if tool != "Bash" and not path:
        return
    roots, CUT = find_roots(cwd if tool == "Bash" else os.path.dirname(resolve(path, cwd)))
    ROOTS = [str(r) for r in roots]
    if tool != "Bash":
        check_file(tool, resolve(path, cwd))
    elif ROOTS or CUT:
        check_bash(inp.get("command", ""), cwd)


if __name__ == "__main__":
    main()
