---
name: ingest
description: Ingest a raw source into the wiki - write its source page and integrate it into entity, concept and overview pages. Use when the user adds a file to raw/, pastes or links something to file, or says ingest/process/add this.
disable-model-invocation: true
argument-hint: "[raw/<file> | URL] [unattended]"
---

# Ingest

Page conventions: `llm-wiki ref page-formats` - read it before the first ingest of a session.

Ingest one source at a time. For a batch, run this whole sequence per source.

## Dispatch (main session)

The main session selects, dispatches and talks to the user; the reading and writing happen in `llm-wiki:ingester` subagents, each in a fresh context. A subagent given one of the assignments below goes straight to Steps.

1. **Select** (step 1). For a PDF, run `llm-wiki pdf raw/<file>.pdf` and note the number of chunks. A text source over about 3,000 lines counts as multi-chunk.
2. **Read.** Dispatch `llm-wiki:ingester` with `read raw/<file>`. Multi-chunk PDF: one `read chunk N of raw/<file>.pdf` per chunk, up to 4 at a time (they write separate notes files). Done when `llm-wiki pdf raw/<file>.pdf --plan` shows every chunk `done`; re-dispatch any that is `todo`.
3. **Discuss** (step 3), from the readers' reports. For more detail read the notes files' Summary sections, leaving the source itself to the subagents.
4. **Integrate.** Dispatch one `llm-wiki:ingester` with `integrate raw/<file>` and the user's steer.
   - **More than 3 notes files: integrate in passes**, so no context holds the whole document. Group the notes files in order, 2-3 per pass along clause boundaries, and dispatch `integrate raw/<file> - pass K of N: notes <files>` one pass at a time (passes edit the same pages). Every prompt carries the user's steer and what earlier passes created or left open. Pass 1 creates the source page with a `[!todo]` integration-status marker and a stub per part not yet integrated, and its sibling pages; each pass fills its part and ends at `llm-wiki lint` 0 errors; the last pass removes the marker and every other staging trace, revises the overview and writes the one log entry for the whole ingest.
   - **A pass reads sections, not pages**, so its context does not grow with the passes before it. From the source page it reads the status marker, the structure table and Open questions (`grep -n '^## '` for the line numbers, then `Read` with `offset` and `limit`). To a sibling page it appends after reading only the page's last lines.
5. **Report** (step 10) from its report - for a staged integration, from all the passes' reports. If it ended with lint errors, dispatch `integrate` again with those errors.

Unattended or batch ingest of a single-chunk source: one dispatch, `ingest raw/<file>`, replaces 2-4. Several sources: dispatch them one after another, since integrations edit the same pages.

## Steps

1. **Select.** Use the source the user named; otherwise `llm-wiki pending` and take the oldest. A URL or pasted text is first saved verbatim as a new file `raw/<YYYY-MM-DD>-<slug>.md`.
2. **Read** the whole source, then every image it references in `raw/assets/`. Done when you can state its argument without looking.
   - **PDF:** follow `llm-wiki ref pdf-ingest` instead - extract, read all the text, read every image, chunk by chunk.
   - **Standalone image:** read it; the source page describes what it shows.
3. **Discuss.** Give the user 3-7 takeaways, what looks new or contradicts the wiki, and what you plan to emphasize. Wait for their steer. Skip the wait only when they asked for unattended or batch ingest.
4. **Map.** List every entity and concept the source says something substantive about. For each, run `llm-wiki search "<name>"` and classify it: *update* (page exists), *create* (no page, and it matters beyond this one source or the user cares), or *mention only*. Done when every item is classified.
5. **Source page.** `llm-wiki new source "<Title>" --raw raw/<file> --summary "<claim>" --tags a,b`, then fill it: summary, key claims, links to every mapped entity/concept. A multi-chunk source puts claims, figures and errata on sibling pages from the start (`llm-wiki new source "<Title> - figures" --slug <slug>-figures --raw raw/<file>`; page-formats.md, Page size and sibling pages).
6. **Integrate.** For each *update* page: read it, merge the new material where it belongs (rewrite, don't append a dated blob), cite `[[source-slug]]`, add the slug to `sources:`, set `updated`. For each *create*: `llm-wiki new entity|concept "<Name>" --sources <source-slug>` and write it. Where the source disagrees with a page, add a `[!contradiction]` callout on both pages. Done when every mapped item is handled.
7. **Overview.** Revise `wiki/overview.md` if the source changes the thesis, adds a thread, or closes an open question.
8. **Verify.** `llm-wiki lint` - fix until 0 errors and no `orphan`, `stale` or `unlinked-mention` findings involving pages you touched.
9. **Log.** `llm-wiki log ingest "<Title>" -m "created: …; updated: …; contradictions: …"`.
10. **Report** pages created and updated, contradictions found, and 2-3 follow-up questions or sources worth finding.
