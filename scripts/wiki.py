#!/usr/bin/env python3
"""llm-wiki - CLI for the LLM wiki. Stdlib only.

  init     scaffold a new wiki, or adopt an existing folder

  search   ranked full-text search over wiki pages (or raw sources with --raw)
  links    outbound links and backlinks of a page
  new      create a page from a template
  index    regenerate wiki/index.md from page frontmatter
  log      append to / tail wiki/log.md
  pending  raw sources with no source page yet
  check    validate single pages (used by the PostToolUse hook)
  lint     whole-wiki health check
  stats    one-screen status (used by the SessionStart hook)
  pdf      PDF -> text + every image + page renders, with a chunk plan (llm-wiki pdf --help)
  ref      print a reference: page formats, PDF ingest, output formats, the workflows

Runs on the wiki that contains the current directory (the folder holding `.llm-wiki/`), else on the
one wiki below it, or on $LLM_WIKI_ROOT. Paths are printed relative to the current directory; a path
argument may be relative to it or to the wiki root.
"""
import argparse
import datetime
import json
import math
import os
import re
import shlex
import sys
from collections import Counter, defaultdict
from pathlib import Path

from wikiroot import PLUGIN, find_roots, given, kit, shown, unsettled

ROOTS, CUT = find_roots()
ROOT = ROOTS[0] if len(ROOTS) == 1 and not CUT else None
NO_WIKI = ROOT is None
ROOT = ROOT or Path.cwd()
WIKI = ROOT / "wiki"
RAW = ROOT / "raw"
INDEX = WIKI / "index.md"
LOG = WIKI / "log.md"

# page type -> directory under wiki/ ("" = wiki root)
TYPE_DIR = {"source": "sources", "entity": "entities", "concept": "concepts",
            "analysis": "analyses", "overview": ""}
REQUIRED = ["title", "type", "summary", "created", "updated"]
MAX_PAGE_BYTES = 40_000  # lint warns above this; a page this long costs ~10k tokens to open
LOG_OPS = ["ingest", "query", "lint", "schema", "note"]
RAW_TEXT = {".md", ".markdown", ".txt", ".org", ".rst", ".csv", ".tsv", ".json", ".html", ".htm", ""}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FM_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
LINK_RE = re.compile(r"(!?)\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
STOP = set("a an and are as at be by for from has have how in is it its of on or that the this to "
           "was were what when where which who why will with".split())


def today():
    return datetime.date.today().isoformat()


def slugify(s):
    return re.sub(r"[\W_]+", "-", s.lower()).strip("-")


def show(rel):
    return shown(ROOT, rel)


def own(path):
    """Stop before a write unless `path` is the wiki's own file: no symlink, and under wiki/ once links are followed."""
    if path.is_symlink() or WIKI not in path.resolve().parents:
        sys.exit(f"not written: {show(path.relative_to(ROOT))} is a symlink or leads outside {show('wiki')}/")


# ---------- frontmatter ----------

def unq(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_fm(text):
    """Minimal YAML subset: `key: value`, `key: [a, b]`, and `- item` block lists."""
    m = FM_RE.match(text)
    if not m:
        return None, text
    meta, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"\s*-\s+(.*)", line)
        if item and key:
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(unq(item.group(1)))
            continue
        kv = re.match(r"([A-Za-z_][\w-]*):\s*(.*)", line)
        if kv:
            key, v = kv.group(1), kv.group(2).strip()
            if v.startswith("[") and v.endswith("]"):
                meta[key] = [unq(x) for x in v[1:-1].split(",") if x.strip()]
            else:
                meta[key] = unq(v)
    return meta, text[m.end():]


def yaml_str(v):
    return json.dumps(v, ensure_ascii=False) if re.search(r"[:#\[\]{}\"'|>]|^[-?!&*@%`]", v) else v


def extract_links(body):
    out = []
    for embed, target in LINK_RE.findall(CODE_RE.sub("", body)):
        name = Path(target.strip()).name
        if name.endswith(".md"):
            name = name[:-3]
        elif embed and Path(name).suffix:
            continue  # ![[image.png]]
        out.append(name)
    return out


class Page:
    def __init__(self, path):
        self.path = path
        self.rel = path.relative_to(ROOT).as_posix()
        self.slug = path.stem
        self.text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        meta, self.body = parse_fm(self.text)
        self.has_fm = meta is not None
        self.meta = meta or {}
        self.links = extract_links(self.body)

    def get(self, k):
        v = self.meta.get(k, "")
        return ", ".join(v) if isinstance(v, list) else v

    def lst(self, k):
        v = self.meta.get(k, [])
        v = v if isinstance(v, list) else ([v] if v else [])
        return [x.strip().removeprefix("[[").removesuffix("]]") for x in v if x.strip()]

    @property
    def title(self):
        return self.get("title") or self.slug

    @property
    def type(self):
        return self.get("type")


def load_pages():
    if not WIKI.is_dir():
        return []
    return [Page(p) for p in sorted(WIKI.rglob("*.md")) if p not in (INDEX, LOG)]


# ---------- search ----------

def tok(s):
    out = []
    for w in re.findall(r"\w+", s.lower()):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


FIELD_W = {"title": 5, "aliases": 5, "slug": 4, "tags": 3, "summary": 3, "headings": 2, "body": 1}


def wiki_docs(pages):
    docs = []
    for p in pages:
        heads = " ".join(l.lstrip("#") for l in p.body.splitlines() if l.startswith("#"))
        docs.append({
            "rel": p.rel, "slug": p.slug, "title": p.title, "type": p.type, "summary": p.get("summary"),
            "tags": p.lst("tags"), "names": [p.title] + p.lst("aliases"), "text": p.text,
            "skip": p.text.count("\n", 0, len(p.text) - len(p.body)),
            "fields": {"title": p.title, "aliases": " ".join(p.lst("aliases")), "slug": p.slug,
                       "tags": " ".join(p.lst("tags")), "summary": p.get("summary"),
                       "headings": heads, "body": p.body},
        })
    return docs


def raw_docs():
    docs = []
    if not RAW.is_dir():
        return docs
    for f in sorted(RAW.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in RAW_TEXT:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        docs.append({"rel": f.relative_to(ROOT).as_posix(), "slug": f.stem, "title": f.name, "type": "raw",
                     "summary": "", "tags": [], "names": [f.stem], "text": text, "skip": 0,
                     "fields": {"title": f.stem, "body": text}})
    return docs


def snippet(doc, qset):
    best, best_n, best_line = 0, 0, ""
    for i, line in enumerate(doc["text"].splitlines()):
        if i < doc["skip"]:
            continue
        hits = len(qset & set(tok(line)))
        if hits > best:
            best, best_n, best_line = hits, i + 1, line.strip()
    if not best:
        return None
    return best_n, (best_line[:200] + "…") if len(best_line) > 200 else best_line


def search(docs, query, limit):
    for d in docs:
        d["wtf"] = Counter()
        for f, s in d["fields"].items():
            for t in tok(s):
                d["wtf"][t] += FIELD_W[f]
        d["dl"] = len(tok(d["fields"]["body"])) + 1
    n = len(docs)
    if not n:
        return []
    avgdl = sum(d["dl"] for d in docs) / n
    df = Counter(t for d in docs for t in d["wtf"])
    # query terms; unknown terms fall back to prefix matches at reduced weight
    terms = []
    for q in dict.fromkeys(tok(query)):
        if q in df:
            terms.append((q, 1.0))
        elif len(q) >= 4:
            terms += [(v, 0.7) for v in df if v.startswith(q)]
    qset = {t for t, _ in terms}
    phrase = query.lower().strip()
    k1, b = 1.5, 0.75
    hits = []
    for d in docs:
        score = 0.0
        for t, w in terms:
            tf = d["wtf"].get(t, 0)
            if tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += w * idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * d["dl"] / avgdl))
        if score and (phrase == d["slug"] or any(phrase in x.lower() for x in d["names"])):
            score = score * 1.5 + 2
        if score:
            hits.append((score, d))
    hits.sort(key=lambda h: (-h[0], h[1]["rel"]))
    return [{"score": round(s, 2), "path": d["rel"], "type": d["type"], "title": d["title"],
             "summary": d["summary"], "snippet": snippet(d, qset)} for s, d in hits[:limit]]


def cmd_search(a):
    query = " ".join(a.query)
    docs = raw_docs() if a.raw else wiki_docs(load_pages())
    if a.type:
        docs = [d for d in docs if d["type"] == a.type]
    if a.tag:
        docs = [d for d in docs if a.tag in d["tags"]]
    hits = search(docs, query, a.n)
    for h in hits:
        h["path"] = show(h["path"])
    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        return 0
    if not hits:
        print("no hits" + ("" if a.raw else " - try other terms, or --raw to search raw sources"))
        return 0
    for h in hits:
        head = f"{h['score']:6.2f}  {h['path']}  [{h['type']}] {h['title']}"
        print(head + (f" — {h['summary']}" if h["summary"] else ""))
        if h["snippet"]:
            print(f"        L{h['snippet'][0]}: {h['snippet'][1]}")
    return 0


# ---------- links ----------

def find_page(pages, name):
    name = Path(name).stem
    for p in pages:
        if p.slug == name:
            return p
    low = name.lower()
    for p in pages:
        if low in [x.lower() for x in [p.title] + p.lst("aliases")]:
            return p
    return None


def cmd_links(a):
    pages = load_pages()
    p = find_page(pages, a.page)
    if not p:
        print(f"no page '{a.page}'", file=sys.stderr)
        return 1
    by_slug = {q.slug: q for q in pages}
    print(f"{show(p.rel)}  [{p.type}] {p.title}")
    print("out:")
    for s in dict.fromkeys(p.links + p.lst("sources")):
        q = by_slug.get(s)
        print(f"  {show(q.rel)} — {q.get('summary')}" if q else f"  [[{s}]] (missing)")
    print("in:")
    for q in pages:
        if q is not p and (p.slug in q.links or p.slug in q.lst("sources")):
            print(f"  {show(q.rel)} — {q.get('summary')}")
    return 0


# ---------- new ----------

def raw_rel(arg):
    """The `raw:` value of a source page: the file's path from the wiki root, or the argument as given
    for a file that does not exist. None for a file outside raw/."""
    p = given(ROOT, arg)
    if not p.exists():
        return arg
    return p.relative_to(ROOT).as_posix() if RAW in p.parents else None


def cmd_new(a):
    if a.type not in TYPE_DIR or a.type == "overview":
        print(f"type must be one of: {', '.join(t for t in TYPE_DIR if t != 'overview')}", file=sys.stderr)
        return 1
    raw = raw_rel(a.raw) if a.raw else ""
    if raw is None:
        print(f"--raw must be a file in the wiki, under {show('raw')}/: {a.raw}", file=sys.stderr)
        return 1
    slug = slugify(a.slug or a.title)
    if not slug:
        print("the slug is empty: give a title or --slug with a letter or digit in it", file=sys.stderr)
        return 1
    for p in load_pages():
        if p.slug == slug:
            print(f"exists: {show(p.rel)} - update it instead", file=sys.stderr)
            return 1
    tpl = kit("templates", f"{a.type}.md", ROOT).read_text(encoding="utf-8")
    fill = {"title": yaml_str(a.title), "h1": a.title, "summary": yaml_str(a.summary or ""),
            "raw": raw, "tags": ", ".join(t.strip() for t in (a.tags or "").split(",") if t.strip()),
            "sources": ", ".join(s.strip() for s in (a.sources or "").split(",") if s.strip()),
            "date": today()}
    for k, v in fill.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    path = WIKI / TYPE_DIR[a.type] / f"{slug}.md"
    own(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tpl, encoding="utf-8")
    write_index(load_pages())
    print(show(path.relative_to(ROOT)))
    return 0


# ---------- index ----------

def render_index(pages):
    groups = [("Overview", "overview"), ("Sources", "source"), ("Entities", "entity"),
              ("Concepts", "concept"), ("Analyses", "analysis")]
    out = ["# Index", "",
           "<!-- GENERATED from page frontmatter by `llm-wiki index`. Do not edit. -->", ""]
    known = {t for _, t in groups}
    groups.append(("Uncategorized", None))
    for label, t in groups:
        sel = [p for p in pages if (p.type == t if t else p.type not in known)]
        if not sel:
            continue
        sel.sort(key=(lambda p: (p.get("created"), p.slug)) if t == "source" else (lambda p: p.title.lower()),
                 reverse=(t == "source"))
        out.append(f"## {label} ({len(sel)})")
        out.append("")
        for p in sel:
            if t == "source":
                tail = f" · {p.get('created')}"
            elif t == "overview" or not t:
                tail = ""
            else:
                tail = f" · {len(p.lst('sources'))} src · {p.get('updated')}"
            out.append(f"- [[{p.slug}|{p.title}]] — {p.get('summary')}{tail}")
        out.append("")
    return "\n".join(out)


def write_index(pages):
    new = render_index(pages)
    if not INDEX.exists() or INDEX.read_text(encoding="utf-8") != new:
        own(INDEX)
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        INDEX.write_text(new, encoding="utf-8")
        return True
    return False


def cmd_index(a):
    pages = load_pages()
    changed = write_index(pages)
    if not a.quiet:
        print(f"{show('wiki/index.md')}: {len(pages)} pages, {'updated' if changed else 'unchanged'}")
    return 0


# ---------- log ----------

def log_heads():
    if not LOG.exists():
        return []
    return [l for l in LOG.read_text(encoding="utf-8").splitlines() if l.startswith("## [")]


def cmd_log(a):
    if not a.op:
        print("\n".join(log_heads()[-a.n:]) or "(log empty)")
        return 0
    if not a.title:
        print("usage: llm-wiki log <op> \"<title>\" [-m note]", file=sys.stderr)
        return 1
    own(LOG)
    if not LOG.exists():
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text("# Log\n\n<!-- Append-only. Add entries with `llm-wiki log`. -->\n",
                       encoding="utf-8")
    entry = f"\n## [{today()}] {a.op} | {a.title}\n"
    if a.m:
        entry += f"\n{a.m.strip()}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(entry.strip().splitlines()[0])
    return 0


# ---------- pending ----------

def raw_files():
    if not RAW.is_dir():
        return []
    return [f for f in sorted(RAW.rglob("*"))
            if f.is_file() and not f.name.startswith(".") and (RAW / "assets") not in f.parents]


def pending(pages):
    done = {(ROOT / p.get("raw")).resolve() for p in pages if p.type == "source" and p.get("raw")}
    return [f.relative_to(ROOT).as_posix() for f in raw_files() if f.resolve() not in done]


def cmd_pending(a):
    print("\n".join(show(r) for r in pending(load_pages())) or "(nothing pending)")
    return 0


# ---------- check / lint ----------

def validate_page(p, strict_today=False):
    """Per-page problems as (severity, code, message)."""
    out = []
    if not p.has_fm:
        return [("error", "frontmatter", "missing YAML frontmatter (see `llm-wiki ref page-formats`)")]
    for k in REQUIRED:
        if not p.get(k):
            out.append(("error", "frontmatter", f"missing `{k}`"))
    t = p.type
    if t and t not in TYPE_DIR:
        out.append(("error", "type", f"type `{t}` not in {sorted(TYPE_DIR)}"))
    elif t:
        want = WIKI / TYPE_DIR[t]
        if p.path.parent != want:
            out.append(("error", "location", f"type `{t}` belongs in {want.relative_to(ROOT).as_posix() or 'wiki'}/"))
        if t == "overview" and p.slug != "overview":
            out.append(("error", "type", "only wiki/overview.md may have type overview"))
    if p.slug != slugify(p.slug):
        out.append(("error", "slug", f"filename should be kebab-case: {slugify(p.slug)}.md"))
    for k in ("created", "updated"):
        if p.get(k) and not DATE_RE.match(p.get(k)):
            out.append(("error", "date", f"`{k}` must be YYYY-MM-DD"))
    if strict_today and DATE_RE.match(p.get("updated")) and p.get("updated") != today():
        out.append(("error", "date", f"page was edited: set `updated: {today()}`"))
    if len(p.get("summary")) > 200:
        out.append(("warn", "summary", "summary over 200 chars; keep it one line"))
    if t == "source":
        r = p.get("raw")
        if not r:
            out.append(("error", "raw", "source page needs `raw: raw/<file>`"))
        elif not (ROOT / r).exists():
            out.append(("error", "raw", f"raw file not found: {r}"))
    elif t in ("entity", "concept", "analysis") and not p.lst("sources"):
        out.append(("warn", "unsourced", "no `sources:` - every claim needs a source page"))
    return out


def cmd_check(a):
    bad = 0
    for f in a.paths:
        path = given(ROOT, f)
        if not path.exists() or WIKI not in path.parents or path in (INDEX, LOG):
            continue
        p = Page(path)
        for sev, code, msg in validate_page(p, strict_today=True):
            if sev == "error":
                bad += 1
                print(f"{show(p.rel)}: {msg}")
    return 1 if bad else 0


def lint(pages):
    issues = []  # (severity, code, path, message)
    add = lambda sev, code, path, msg: issues.append((sev, code, path, msg))
    by_slug = defaultdict(list)
    for p in pages:
        by_slug[p.slug].append(p)
    inbound = defaultdict(set)
    missing = Counter()

    for p in pages:
        for sev, code, msg in validate_page(p):
            add(sev, code, p.rel, msg)
        for s in set(p.links):
            if s in by_slug:
                inbound[s].add(p.slug)
            elif s not in ("index", "log"):
                missing[s] += 1
                add("error", "broken-link", p.rel, f"[[{s}]] has no page - create it or unlink")
        for s in p.lst("sources"):
            q = by_slug.get(s)
            if not q:
                add("error", "bad-source", p.rel, f"`sources:` lists unknown page `{s}`")
            elif q[0].type != "source":
                add("warn", "bad-source", p.rel, f"`sources:` entry `{s}` is a {q[0].type} page, not a source")
            else:
                inbound[s].add(p.slug)
                if s not in p.links:
                    add("info", "uncited", p.rel, f"lists source `{s}` but never cites [[{s}]] inline")
        if len(p.body.split()) < 30 and p.has_fm:
            add("warn", "stub", p.rel, "under 30 words")
        size = len(p.text.encode("utf-8"))
        if size > MAX_PAGE_BYTES:
            add("warn", "page-size", p.rel, f"{size // 1000} KB, over {MAX_PAGE_BYTES // 1000} KB - move a section to a "
                "sibling page (`llm-wiki ref page-formats`)")
        for i, line in enumerate(p.text.splitlines(), 1):
            if "[!contradiction]" in line:
                add("info", "contradiction", f"{p.rel}:{i}", line.strip("> ").strip())

    for slug, ps in by_slug.items():
        if len(ps) > 1:
            add("error", "duplicate", ps[0].rel, "same filename as " + ", ".join(show(q.rel) for q in ps[1:]))
    names = defaultdict(set)
    for p in pages:
        for nm in [p.title] + p.lst("aliases"):
            names[nm.lower()].add(p.rel)
    for nm, rels in names.items():
        if len(rels) > 1:
            add("warn", "duplicate", sorted(rels)[0], f"title/alias '{nm}' shared with {', '.join(show(r) for r in sorted(rels)[1:])} - merge?")

    for p in pages:
        if p.type != "overview" and not (inbound[p.slug] - {p.slug}):
            add("warn", "orphan", p.rel, "no inbound links")

    # stale: a newer source touches this page but the page was not updated since
    sources = [p for p in pages if p.type == "source"]
    for p in pages:
        if p.type == "source" or not DATE_RE.match(p.get("updated")):
            continue
        newer = [s.slug for s in sources
                 if (p.slug in s.links or s.slug in p.lst("sources")) and s.get("created") > p.get("updated")]
        if newer:
            add("warn", "stale", p.rel, f"not updated since newer source(s): {', '.join(newer)}")

    for s, n in missing.items():
        if n >= 2:
            add("info", "missing-page", "wiki", f"[[{s}]] wanted by {n} pages - create it")

    # a source page and its siblings (same `raw:`) are read as one page
    by_raw = defaultdict(list)
    for p in sources:
        by_raw[p.get("raw")].append(p)
    linked = {p.slug: set(p.links) for p in pages}
    for sibs in by_raw.values():
        for p in sibs:
            linked[p.slug] = {s for q in sibs for s in q.links}

    # plain-text mentions of a page that are not linked
    stripped = {p.slug: LINK_RE.sub(" ", CODE_RE.sub(" ", p.body)) for p in pages}
    for p in pages:
        if p.type in ("overview", "source"):
            continue
        for nm in dict.fromkeys([p.title] + p.lst("aliases")):
            if len(nm) < 4:
                continue
            rx = re.compile(r"(?<!\w)" + re.escape(nm) + r"(?!\w)", re.I)
            for q in pages:
                if q is not p and p.slug not in linked[q.slug] and rx.search(stripped[q.slug]):
                    add("info", "unlinked-mention", q.rel, f"mentions '{nm}' without [[{p.slug}]]")

    # PDF sources: extraction done, and every extracted image described on the source page or a sibling of it
    for r, sibs in by_raw.items():
        if not r.lower().endswith(".pdf"):
            continue
        p = min(sibs, key=lambda q: q.slug)  # the source page itself: siblings are <slug>-<part>
        man = RAW / "assets" / slugify(Path(r).stem) / "manifest.json"
        if not man.exists():
            add("error", "pdf-extract", p.rel, f"PDF not extracted - run: llm-wiki pdf {show(r)}")
            continue
        # an image counts as read when a source page of this PDF or a reading-notes file names it
        seen = "".join(q.text for q in sibs) + "".join(n.read_text(encoding="utf-8", errors="replace")
                                for n in sorted((man.parent / "notes").glob("*.md")))
        data = json.loads(man.read_text(encoding="utf-8"))
        for c in data.get("chunks", []):
            if len(data["chunks"]) > 1 and not (ROOT / c["notes"]).exists():
                add("error", "pdf-chunk", p.rel, f"chunk {c['id']} (pages {c['pages'][0]}-{c['pages'][1]}) has no reading notes: {show(c['notes'])}")
        unread = [i for i in data.get("images", []) if Path(i["file"]).name not in seen]
        for img in unread[:5]:
            add("error", "pdf-figure", p.rel, f"image has no Figures entry: {show(img['file'])} (p.{img['page']})")
        if len(unread) > 5:
            add("error", "pdf-figure", p.rel, f"... and {len(unread) - 5} more images without a Figures entry")

    for r in pending(pages):
        add("info", "pending", r, "raw source not ingested")
    if not INDEX.exists() or INDEX.read_text(encoding="utf-8") != render_index(pages):
        add("error", "index", "wiki/index.md", "out of date - run: llm-wiki index")
    return issues


def cmd_lint(a):
    issues = lint(load_pages())
    order = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda i: (order[i[0]], i[1], i[2]))
    counts = Counter(i[0] for i in issues)
    issues = [(sev, code, show(path), msg) for sev, code, path, msg in issues]
    if a.json:
        print(json.dumps([dict(zip(("severity", "code", "path", "message"), i)) for i in issues],
                         ensure_ascii=False, indent=1))
    else:
        for sev, code, path, msg in issues:
            if sev == "info" and a.errors:
                continue
            print(f"{sev:5} {code:16} {path}: {msg}")
        print(f"{counts['error']} errors, {counts['warn']} warnings, {counts['info']} info")
    return 1 if counts["error"] else 0


# ---------- stats ----------

def cmd_stats(a):
    pages = load_pages()
    by_type = Counter(p.type or "?" for p in pages)
    pend = pending(pages)
    kinds = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items())) or "empty"
    print(f"wiki at {show('.')} (schema: {show('AGENTS.md')})")
    print(f"wiki: {len(pages)} pages ({kinds}) · raw: {len(raw_files())} files, {len(pend)} pending ingest")
    if pend:
        print("pending: " + ", ".join(show(r) for r in pend[:8]) + (" …" if len(pend) > 8 else ""))
    slugs = {p.slug for p in pages}
    inbound = Counter(s for p in pages for s in set(p.links) if s != p.slug and s in slugs)
    if inbound:
        print("hubs: " + ", ".join(f"{s}({n})" for s, n in inbound.most_common(8)))
    tags = Counter(t for p in pages for t in p.lst("tags"))
    if tags:
        print("tags: " + ", ".join(f"{t}({n})" for t, n in tags.most_common(12)))
    heads = log_heads()[-5:]
    if heads:
        print("recent log:")
        for h in heads:
            print("  " + h[3:])
    if a.hook:
        print("a question this wiki may answer: use the wiki-query skill, cite pages as [[slug]], "
              "and write to the wiki only on the user's word")
    return 0


def on_path():
    """SessionStart: put the CLI on the Bash tool's PATH for the session, wherever the tooling sits."""
    env = os.environ.get("CLAUDE_ENV_FILE")
    if not env:
        return
    line = f"export PATH={shlex.quote(str(PLUGIN / 'bin'))}:\"$PATH\"\n"
    f = Path(env)
    try:
        if not f.exists() or line not in f.read_text(encoding="utf-8"):
            with f.open("a", encoding="utf-8") as out:
                out.write(line)
    except OSError:
        pass  # the status still prints; the CLI is then reached by its path


# ---------- ref ----------

REFS = {"page-formats": "page types, frontmatter, links, citations, contradictions, page size",
        "pdf-ingest": "extracting and reading a PDF chunk by chunk; the notes file",
        "output-formats": "answer shapes for queries: table, timeline, deck, chart",
        "ingest": "the ingest workflow", "query": "the query workflow", "lint": "the lint workflow"}


def cmd_ref(a):
    if not a.name:
        for k, v in REFS.items():
            print(f"{k:15} {v}")
        return 0
    if a.name in ("ingest", "query", "lint"):
        path = PLUGIN / "skills" / f"wiki-{a.name}" / "SKILL.md"
    else:
        path = kit("references", f"{a.name}.md", None if NO_WIKI else ROOT)
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="ranked search; prints path, title, summary, best-matching line")
    s.add_argument("query", nargs="+")
    s.add_argument("-n", type=int, default=8, help="max hits (default 8)")
    s.add_argument("--type", choices=sorted(TYPE_DIR))
    s.add_argument("--tag")
    s.add_argument("--raw", action="store_true", help="search raw/ sources instead of wiki pages")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("links", help="outbound links and backlinks of a page (slug, title or alias)")
    s.add_argument("page")
    s.set_defaults(fn=cmd_links)

    s = sub.add_parser("new", help="create a page from a template; prints its path")
    s.add_argument("type", help="source | entity | concept | analysis")
    s.add_argument("title")
    s.add_argument("--slug")
    s.add_argument("--summary", help="one line; shown in index and search results")
    s.add_argument("--raw", help="source pages: path of the raw file, e.g. raw/paper.md")
    s.add_argument("--tags", help="comma-separated")
    s.add_argument("--sources", help="comma-separated source-page slugs")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("index", help="regenerate wiki/index.md")
    s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("log", help="no args: last entries; with op+title: append an entry")
    s.add_argument("op", nargs="?", choices=LOG_OPS)
    s.add_argument("title", nargs="?")
    s.add_argument("-m", help="entry body: pages created/updated, contradictions, follow-ups")
    s.add_argument("-n", type=int, default=10, help="entries to show (default 10)")
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("pending", help="raw sources with no source page")
    s.set_defaults(fn=cmd_pending)

    s = sub.add_parser("check", help="validate given pages; exit 1 on errors")
    s.add_argument("paths", nargs="+")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("lint", help="whole-wiki health check; exit 1 on errors")
    s.add_argument("--errors", action="store_true", help="hide info-level findings")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("stats", help="one-screen status")
    s.add_argument("--hook", action="store_true", help="SessionStart: put the CLI on PATH; print nothing outside a wiki")
    s.set_defaults(fn=cmd_stats)

    s = sub.add_parser("ref", help="print a reference document; no name lists them")
    s.add_argument("name", nargs="?", choices=sorted(REFS))
    s.set_defaults(fn=cmd_ref)

    a = ap.parse_args()
    if getattr(a, "hook", False):
        on_path()
    if NO_WIKI and a.cmd != "ref":
        msg = unsettled(ROOTS, CUT)
        if not getattr(a, "hook", False):
            sys.exit(msg)
        if ROOTS or CUT:
            print(msg)
        sys.exit(0)
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
