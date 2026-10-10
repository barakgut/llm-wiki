---
name: lint
description: Health-check and analyze the wiki - broken links, orphans, stale or contradictory pages, missing pages, coverage gaps - then fix and report. Use when the user asks to lint, audit, clean up, analyze or health-check the wiki, or asks what is missing or what to read next.
disable-model-invocation: true
---

# Lint

Two passes: mechanical (the script finds it), then semantic (you find it).

## 1. Mechanical

`llm-wiki lint` and work the list top-down:

| code | fix |
|---|---|
| `frontmatter` `type` `location` `slug` `date` `raw` | repair the page per `llm-wiki ref page-formats` |
| `pdf-extract` `pdf-figure` | finish the PDF ingest per `llm-wiki ref pdf-ingest`: extract, read the named image, add its `## Figures` entry |
| `broken-link` / `missing-page` | create the page if 2+ pages want it or it is a real entity/concept; otherwise unlink |
| `bad-source` `unsourced` `uncited` | find the backing source page (`llm-wiki search`), cite it; unverifiable claims are removed or marked `Unsourced:` |
| `duplicate` | merge into one page, move the other name to `aliases:`, repoint links |
| `orphan` | link it from the pages that should mention it (`llm-wiki search "<title>"`), or merge it away |
| `stale` | re-read the newer source page and integrate it |
| `page-size` | move a section or sub-topic to a page of its own per `llm-wiki ref page-formats` (Page size and sibling pages) |
| `stub` | expand from its sources, or merge into a parent page |
| `unlinked-mention` | link the first mention per section |
| `contradiction` | resolvable from the sources? rewrite as `[!resolved]`. Otherwise keep and list it in the report |
| `pending` | list in the report; ingest only if the user asks |

Done when `llm-wiki lint` shows 0 errors and every remaining warning is one you chose to keep, with a reason.

## 2. Semantic

`llm-wiki stats` for hubs and tags. Read `wiki/overview.md`, then the hub pages and every page updated since the last `lint` entry in `llm-wiki log`. Look for:

- **Contradictions** between pages that the callouts miss: same entity, different facts.
- **Superseded claims**: a page asserting what a later source revised.
- **Missing pages**: a concept three pages explain in passing and none defines.
- **Missing cross-references**: pages on related things that never link.
- **Thin synthesis**: `overview.md` threads that no longer match the pages under them.
- **Gaps**: questions the wiki raises and cannot answer.

Fix what the wiki's own sources settle. For gaps, propose - a web search may fill them, but new material enters through `raw/` and `/llm-wiki:ingest`, with the user's go-ahead.

## 3. Report and log

Report: fixed (counts by code), open contradictions, kept warnings, 3-5 questions worth investigating, 3-5 sources worth finding.

`llm-wiki log lint "<N> fixed, <M> open" -m "<the report's key lines>"`
