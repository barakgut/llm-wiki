# Page formats

`llm-wiki new <type> "<Title>"` creates a page from the type's template. A wiki overrides a template with `.llm-wiki/templates/<type>.md`.

## Types

| type | dir | one page per | holds |
|---|---|---|---|
| source | `wiki/sources/` | raw file, plus sibling pages when it grows long | what the source says: summary, key claims, entities/concepts it touches |
| entity | `wiki/entities/` | person, org, product, place, work, dataset | facts and relations, merged across sources |
| concept | `wiki/concepts/` | idea, method, theme, claim cluster | definition, current understanding, evidence for/against |
| analysis | `wiki/analyses/` | question answered | filed query answers: comparisons, syntheses, timelines |
| overview | `wiki/overview.md` | (single) | thesis, threads linking to hub pages, open questions |

Entity vs concept: an entity has a proper name and exists in the world; a concept is an abstraction you could define.

## Frontmatter

```yaml
---
title: Human Readable Title        # required
type: concept                      # required
summary: One line, under 200 chars # required; this is what index.md and search results show
aliases: [Alt Name, Abbrev]        # other names; search boosts them, lint finds unlinked mentions
tags: [topic-a, topic-b]           # lowercase kebab; reuse existing tags (see `llm-wiki stats`)
sources: [source-slug-1]           # source pages backing this page (all types except source/overview)
raw: raw/file.md                   # source pages only: the raw file
created: 2026-01-31                # required
updated: 2026-01-31                # required; set to today on every edit
---
```

Source pages may add `author`, `published`, `url`. Analysis pages add `question`.

The summary is the page's search snippet: write it so a reader can decide from it alone whether to open the page. State the page's claim, not its topic ("Argues X because Y", not "Notes about X").

## Filenames and links

- Filename = kebab-case slug, unique across the whole wiki: `wiki/entities/vannevar-bush.md`.
- Link with `[[slug]]` or `[[slug|display text]]`. Link the first mention of every entity/concept in each section.
- Source slugs: `<first-author-or-site>-<year>-<short-title>` where known, e.g. `bush-1945-as-we-may-think`.

## Citations

Every factual claim on a non-source page ends with the source page it came from: `Memex stored trails between documents [[bush-1945-as-we-may-think]].` Each cited source also appears in `sources:`.

Your own inference is marked as such: `Inference: …` with the pages it rests on.

## Contradictions

When sources disagree, keep both claims and flag them on every affected page:

```markdown
> [!contradiction] Launch year
> [[source-a]] says 2019; [[source-b]] says 2021. Unresolved - source-b is primary.
```

When resolved, rewrite the callout as `> [!resolved]` with the reasoning. `llm-wiki lint` lists open contradictions.

## Source errata

A misprint or internal inconsistency of one source is an erratum, not a contradiction (which is between sources). It goes in a table under `## Source errata` on the source page, or on its `-errata` sibling:

```markdown
| Page | As printed | Inferred correction / comment (inference) |
|---|---|---|
| p.167 | Table 34: maximum NPN for 32K = 69 | 68: NPN = LF, and table 8 (p.46) has 68. |
```

Record the text as printed. A correction is the reader's inference and is labelled as one, here and on every page that uses the corrected value.

## Superseded claims

Replace the stale claim in place and leave a trace: `~~Old claim~~ superseded by [[newer-source]]: new claim.`

## Images

Raw images live in `raw/assets/`. Embed with `![[file.png]]`. Read the source text first, then view the images it references.

PDF sources: `llm-wiki ref pdf-ingest`. Their source page, or its `-figures` sibling, carries a `## Figures` section with an entry per image that carries information.

## Page size and sibling pages

Every reader that opens a page pays for all of it, so a page stays under 40 KB (about 10k tokens); `llm-wiki lint` warns above that (`page-size`).

A source page that would pass 40 KB keeps the summary, identity, structure table, entities and concepts, and open questions, and moves its bulk to sibling pages. Each section that moved keeps its heading and one line linking the sibling.

| sibling | holds |
|---|---|
| `<slug>-claims` | Key claims by part of the document; the source page keeps one line per part saying which pages took it |
| `<slug>-figures` | the Figures entries |
| `<slug>-errata` | the Source errata table |

- A sibling is a `source` page: same `raw:` as the source page, title `<source title> - <part>`, first line `Part of [[<slug>]].`
- A sibling that would itself pass 40 KB is split along the document's parts: `<slug>-figures-clauses-4-8`, `<slug>-figures-clauses-9-17`.
- Lint reads a source page and its siblings as one page for `pdf-figure` and `unlinked-mention`.
- Claims are still cited to the source page, `[[<slug>]]`. Link a sibling only to point a reader at it.
- A multi-chunk source gets its siblings when the source page is created; a single-chunk source keeps everything on its page.
- A check of one source against another is an `analysis` page, linked from both source pages.

Any other page over 40 KB: move a sub-topic out to a page of its own and link it.
