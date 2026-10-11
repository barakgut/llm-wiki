# Ingesting a PDF

A PDF is ingested as its full text plus every image in it. This replaces step 2 (Read) of the ingest skill.

## 1. Extract and plan

```
llm-wiki pdf raw/<file>.pdf          # once; prints the chunk plan
llm-wiki pdf raw/<file>.pdf --plan   # plan again, with done/todo per chunk
```

Output lands in `raw/assets/<stem>/`: `text.md`, every embedded image, a render of every page, `manifest.json`.

The plan cuts the PDF into **chunks**: page ranges of at most 15 pages and 30 images. A chunk is what one context reads well; a second chunk read on top of the first starts crowding it out. So:

- **1 chunk** - read it in the context that will also write the wiki pages.
- **2+ chunks** - one fresh context per chunk, each leaving reading notes on disk; then one fresh context integrates from the notes. The main session dispatches a `wiki-ingester` subagent per chunk (see the ingest skill).
- **4+ chunks** - integration is chunked too: one fresh context per 2-3 notes files, in document order, one pass after another. The source page carries a `[!todo]` integration-status marker until the last pass removes it.

## 2. Read a chunk

`llm-wiki pdf raw/<file>.pdf --chunk N` prints the work list: the exact `text.md` line range, the images, the notes path.

1. **Text.** Read that line range of `text.md` - the given `offset` and `limit`, nothing wider.
2. **Images.** Read every image on the list, in page order. For each, note what it shows and what it adds to the text: the data in a chart (axes, series, values, trend), the structure of a diagram, the content of a table, text in a screenshot.
   - `page render` entries show the whole page: vector charts and diagrams, tables, layout, scanned text. Where the render adds nothing beyond the text layer, its entry is `text only`.
   - An entry noted as lacking a text layer is a scan: transcribe the text it shows - it exists nowhere else.
   - Decorative images (logo, divider, stock photo) get `decorative - <what>`.
3. **Notes.** Write the notes file while the chunk is fresh. In a multi-chunk PDF this is the chunk's only output; in a single-chunk PDF the notes may be skipped and the entries written straight to the source page.

Done when every image on the work list has a Figures entry.

### Notes file

`raw/assets/<stem>/notes/pAAA-BBB.md`. Written for a reader who will never see the PDF: specific, with page numbers, numbers kept exact.

```markdown
# Notes: <file>.pdf pages 31-45

## Summary
5-10 lines: what these pages argue or establish.

## Claims
- <claim, with figures and names exact> (p.33)

## Entities and concepts
- <Name> - what these pages say about it (p.31, p.40)

## Figures
- ![[<stem>-p033-01.png]] p.33 - Bar chart of X by Y, 2019-2024. X rises from 12 to 31; the 2021 dip is not explained in the text.
- ![[<stem>-page034.png]] p.34 - Architecture diagram (vector): A feeds B and C; C writes back to A.
- ![[<stem>-page035.png]] p.35 - text only.

## Transcription
Text of scanned pages, by page. Omit when there are none.

## Open questions
Unclear points, internal inconsistencies, forward/back references to other parts of the document.
```

## 3. Write the source page

From the notes files when they exist (read all of them, in order - in a staged integration, the ones your pass names; open the PDF text or an image again only to settle a specific doubt).

- `## Figures` holds the figures that carry information, with their descriptions. `text only` and `decorative` entries stay in the notes. For a multi-chunk source the entries go on the `<slug>-figures` sibling page (page-formats, Page size and sibling pages).
- Add a line `Reading notes: raw/assets/<stem>/notes/` under the summary of a multi-chunk source.
- Findings that only an image carries go into Key claims and into entity/concept pages like any other claim, cited to the source page.
- Transcriptions of scanned pages stay in the notes; the source page summarises them.

Done when `llm-wiki lint` reports no `pdf-extract`, `pdf-chunk` or `pdf-figure` errors: every chunk has notes and every extracted image is named in the notes, on the source page or on a sibling of it.

## Options

`--no-page-renders` renders only flagged pages (very long text-only PDFs, with the user's agreement); `--min-size 0` keeps images under 48px; `--force` re-extracts and keeps `notes/`.
