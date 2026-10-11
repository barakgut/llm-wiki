#!/usr/bin/env python3
"""llm-wiki pdf - turn a PDF in raw/ into text plus every image, ready for ingest.

  llm-wiki pdf raw/paper.pdf            extract (once)
  llm-wiki pdf raw/paper.pdf --plan     chunk plan and which chunks have notes
  llm-wiki pdf raw/paper.pdf --chunk 3  work list of one chunk

Writes raw/assets/<pdf-stem>/:
  text.md        text layer, one `## Page N` section per page
  <stem>-pNNN-MM.png    each embedded raster image
  <stem>-pageNNN.png    full-page render of every page, so vector figures, scans and layout
                        are never missed (--no-page-renders limits this to pages that need it)
  manifest.json  what was extracted, and the chunk plan; `llm-wiki lint` checks against it
  notes/         reading notes, one file per chunk, written during ingest (kept on --force)

A chunk is a page range small enough to read in one context without losing the start of it.

Needs poppler-utils (pdfinfo, pdftotext, pdfimages, pdftoppm).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from wikiroot import find_roots, given, shown, unsettled

ROOTS, CUT = find_roots()
ROOT = ROOTS[0] if len(ROOTS) == 1 and not CUT else Path.cwd()
RAW = ROOT / "raw"
TOOLS = ["pdfinfo", "pdftotext", "pdfimages", "pdftoppm"]
CAPTION = re.compile(r"^\s*(Figure|Fig\.|Chart|Diagram|Scheme|Plate|Graph|Illustration)\s*\d", re.I | re.M)
LOW_TEXT = 100      # chars; below this a page is treated as scanned / visual-only
FRAGMENTED = 12     # more images than this on one page = one figure cut into strips
CHUNK_PAGES = 15    # chunk budget: at most this many pages ...
CHUNK_IMAGES = 30   # ... and this many images (page renders included)


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode:
        sys.exit(f"{cmd[0]} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def slugify(s):
    return re.sub(r"[\W_]+", "-", s.lower()).strip("-")


def show(rel):
    return shown(ROOT, rel)


def list_images(pdf):
    """Rows of `pdfimages -list`: page, num, type, width, height, object id."""
    rows = []
    for line in run("pdfimages", "-list", str(pdf)).splitlines()[2:]:
        c = line.split()
        if len(c) >= 11 and c[0].isdigit():
            rows.append({"page": int(c[0]), "num": int(c[1]), "type": c[2],
                         "width": int(c[3]), "height": int(c[4]), "object": c[10]})
    return rows


def describe(i):
    extra = f"{i['width']}x{i['height']}" if i["kind"] == "image" else "page render"
    return f"  {show(i['file'])}  (p.{i['page']}, {extra}{' - ' + i['note'] if i.get('note') else ''})"


def show_plan(man):
    chunks = man["chunks"]
    done = sum((ROOT / c["notes"]).exists() for c in chunks)
    print(f"{show(man['pdf'])}: {man['pages']} pages, {len(man['images'])} images, "
          f"{len(chunks)} chunk{'s' if len(chunks) != 1 else ''}, {done} with notes")
    for c in chunks:
        state = "done" if (ROOT / c["notes"]).exists() else "todo"
        print(f"  chunk {c['id']:>3}  pages {c['pages'][0]}-{c['pages'][1]}  {c['images']:>3} images  {state}  {show(c['notes'])}")


def show_chunk(man, n):
    c = next((c for c in man["chunks"] if c["id"] == n), None)
    if not c:
        sys.exit(f"no chunk {n}; chunks are 1-{len(man['chunks'])}")
    a, b = c["pages"]
    imgs = [i for i in man["images"] if a <= i["page"] <= b]
    print(f"chunk {n}/{len(man['chunks'])} of {show(man['pdf'])} - pages {a}-{b}")
    print(f"text:   Read {show(man['text'])} offset={c['text_lines'][0]} limit={c['text_lines'][1] - c['text_lines'][0] + 1}")
    print(f"images: {len(imgs)} - Read every one")
    for i in imgs:
        print(describe(i))
    print(f"notes:  write {show(c['notes'])}")


def main():
    ap = argparse.ArgumentParser(prog="llm-wiki pdf", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--plan", action="store_true", help="show the chunk plan of an extracted PDF")
    ap.add_argument("--chunk", type=int, metavar="N", help="show the work list of chunk N")
    ap.add_argument("--min-size", type=int, default=48,
                    help="skip images narrower or shorter than this many px (default 48; 0 keeps all)")
    ap.add_argument("--no-page-renders", action="store_true",
                    help="render only pages that need it (scans, vector figures, fragmented images) instead of every page")
    ap.add_argument("--dpi", type=int, default=110, help="page render resolution (default 110)")
    ap.add_argument("--force", action="store_true", help="re-extract over an existing extraction (notes/ is kept)")
    a = ap.parse_args()

    if len(ROOTS) != 1 or CUT:
        sys.exit(unsettled(ROOTS, CUT))
    pdf = given(ROOT, a.pdf)
    if not pdf.is_file():
        sys.exit(f"not a file: {a.pdf}")
    if RAW not in pdf.parents:
        sys.exit("the PDF must live under raw/ - copy it there first")
    stem = slugify(pdf.stem)
    out = RAW / "assets" / stem
    man_path = out / "manifest.json"
    rel = lambda p: p.relative_to(ROOT).as_posix()

    if a.plan or a.chunk is not None:
        if not man_path.exists():
            sys.exit(f"not extracted yet - run: llm-wiki pdf {show(rel(pdf))}")
        man = json.loads(man_path.read_text(encoding="utf-8"))
        show_chunk(man, a.chunk) if a.chunk is not None else show_plan(man)
        return
    if man_path.exists() and not a.force:
        print(f"already extracted (use --force to redo):")
        show_plan(json.loads(man_path.read_text(encoding="utf-8")))
        return
    missing = [t for t in TOOLS if not shutil.which(t)]
    if missing:
        sys.exit(f"missing {', '.join(missing)} - install poppler-utils")
    if out.exists():
        for child in out.iterdir():
            if child.name != "notes":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    out.mkdir(parents=True, exist_ok=True)

    m = re.search(r"^Pages:\s+(\d+)", run("pdfinfo", str(pdf)), re.M)
    n_pages = int(m.group(1)) if m else 0

    # text layer
    pages = run("pdftotext", "-layout", str(pdf), "-").split("\f")[:n_pages]
    pages += [""] * (n_pages - len(pages))
    text = [f"# {pdf.name}", "", f"<!-- Extracted from {rel(pdf)} by llm-wiki pdf. Do not edit. -->", ""]
    page_line = {}
    for i, t in enumerate(pages, 1):
        page_line[i] = len(text) + 1
        text += [f"## Page {i}", ""] + (t.strip("\n") or "_(no text layer on this page)_").split("\n") + [""]
    (out / "text.md").write_text("\n".join(text), encoding="utf-8")
    low_text = [i for i, t in enumerate(pages, 1) if len(t.strip()) < LOW_TEXT]

    # embedded images
    images, skipped, render = [], [], {}
    with tempfile.TemporaryDirectory() as tmp:
        run("pdfimages", "-png", "-p", str(pdf), str(Path(tmp) / "im"))
        files = {}
        for f in Path(tmp).iterdir():
            fm = re.match(r"im-(\d+)-(\d+)\.", f.name)
            if fm:
                files[(int(fm.group(1)), int(fm.group(2)))] = f
        seen_obj, seen_hash, per_page = set(), set(), {}
        for r in list_images(pdf):
            why = None
            f = files.get((r["page"], r["num"]))
            if r["type"] in ("smask", "mask"):
                why = "transparency mask"
            elif r["object"] in seen_obj:
                why = "repeat of an earlier image"
            elif a.min_size and (r["width"] < a.min_size or r["height"] < a.min_size):
                why = f"tiny ({r['width']}x{r['height']})"
            elif not f:
                render[r["page"]] = "image could not be extracted"
                continue
            else:
                h = hashlib.sha1(f.read_bytes()).hexdigest()
                if h in seen_hash:
                    why = "repeat of an earlier image"
                seen_hash.add(h)
            seen_obj.add(r["object"])
            if why:
                skipped.append({"page": r["page"], "width": r["width"], "height": r["height"], "reason": why})
            else:
                per_page.setdefault(r["page"], []).append((r, f))
        for page, items in sorted(per_page.items()):
            if len(items) > FRAGMENTED:
                render[page] = f"{len(items)} image fragments"
                continue
            for k, (r, f) in enumerate(items, 1):
                dst = out / f"{stem}-p{page:03d}-{k:02d}.png"
                shutil.copyfile(f, dst)
                images.append({"file": rel(dst), "page": page, "kind": "image",
                               "width": r["width"], "height": r["height"]})

    # page renders
    with_images = {i["page"] for i in images}
    for i in low_text:
        if i not in with_images:
            render.setdefault(i, "scanned or visual-only page: transcribe its text")
    for im in images:
        if im["page"] in low_text:
            im["note"] = "page has little or no text layer: transcribe any text in this image"
    for i, t in enumerate(pages, 1):
        if CAPTION.search(t) and i not in with_images:
            render.setdefault(i, "figure caption without an embedded image (vector figure)")
    if not a.no_page_renders:
        for i in range(1, n_pages + 1):
            render.setdefault(i, "")
    for page, why in sorted(render.items()):
        dst = out / f"{stem}-page{page:03d}"
        run("pdftoppm", "-r", str(a.dpi), "-png", "-f", str(page), "-l", str(page), "-singlefile", str(pdf), str(dst))
        entry = {"file": rel(dst) + ".png", "page": page, "kind": "page"}
        if why:
            entry["note"] = why
        images.append(entry)
    images.sort(key=lambda i: (i["page"], i["kind"], i["file"]))

    # chunk plan: consecutive pages within the page and image budget
    per_page_n = {}
    for i in images:
        per_page_n[i["page"]] = per_page_n.get(i["page"], 0) + 1
    chunks, start, np, ni = [], 1, 0, 0

    def close(first, last):
        end = page_line[last + 1] - 1 if last < n_pages else len(text)
        chunks.append({"id": len(chunks) + 1, "pages": [first, last], "text_lines": [page_line[first], end],
                       "images": sum(per_page_n.get(p, 0) for p in range(first, last + 1)),
                       "notes": f"{rel(out)}/notes/p{first:03d}-{last:03d}.md"})

    for pg in range(1, n_pages + 1):
        k = per_page_n.get(pg, 0)
        if np and (np + 1 > CHUNK_PAGES or ni + k > CHUNK_IMAGES):
            close(start, pg - 1)
            start, np, ni = pg, 0, 0
        np, ni = np + 1, ni + k
    if n_pages:
        close(start, n_pages)

    manifest = {"pdf": rel(pdf), "pages": n_pages, "text": rel(out / "text.md"),
                "text_chars": sum(len(t) for t in pages), "low_text_pages": low_text,
                "chunks": chunks, "images": images, "skipped": skipped}
    man_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    print(f"extracted: {manifest['text_chars']} chars of text -> {show(manifest['text'])}; "
          f"{len(skipped)} images skipped as masks/repeats/tiny")
    show_plan(manifest)
    if not manifest["text_chars"]:
        print("no text layer: this PDF is scanned - all text must be transcribed from the images")
    if len(chunks) > 1:
        print("LARGE: read it chunk by chunk, one context per chunk (`llm-wiki ref pdf-ingest`)")
    else:
        print("work list: llm-wiki pdf " + json.dumps(show(rel(pdf))) + " --chunk 1")


if __name__ == "__main__":
    main()
