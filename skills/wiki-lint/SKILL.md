---
name: wiki-lint
description: Health-check and analyze the wiki - broken links, orphans, stale or contradictory pages, missing pages, coverage gaps - then fix the mechanics, propose the changes to claims, and report. Use when the user asks to lint, audit, clean up, analyze or health-check the wiki, or asks what is missing or what to read next.
disable-model-invocation: true
---

# Lint

Two passes: mechanical (the script finds it), then semantic (you find it).

Links, frontmatter, the index and new cross-references you fix yourself. A fix that changes, merges or removes what a page claims is a proposal: list it with the pages and the source that settles it, and make it when the user approves.

Paths written here (`raw/…`, `wiki/…`, `AGENTS.md`) are from the wiki root; the first line of `llm-wiki stats` says where that is. The CLI takes them as written and prints paths from the current directory: open, write and edit files by the printed form.

## 1. Mechanical

`llm-wiki lint` and work the list top-down:

| code | fix |
|---|---|
| `frontmatter` `type` `location` `slug` `date` `raw` | repair the page per `llm-wiki ref page-formats` |
| `pdf-extract` `pdf-figure` | finish the PDF ingest per `llm-wiki ref pdf-ingest`: extract, read the named image, add its `## Figures` entry |
| `broken-link` / `missing-page` | create the page if 2+ pages want it or it is a real entity/concept; otherwise unlink |
| `bad-source` `unsourced` `uncited` | find the backing source page (`llm-wiki search`), cite it; an unverifiable claim is marked `Unsourced:`, and its removal is a proposal |
| `duplicate` | propose the merge: one page, the other name in `aliases:`, links repointed |
| `orphan` | link it from the pages that should mention it (`llm-wiki search "<title>"`), or merge it away |
| `stale` | re-read the newer source page and propose what it changes on the page |
| `page-size` | move a section or sub-topic to a page of its own per `llm-wiki ref page-formats` (Page size and sibling pages) |
| `stub` | propose: expand from its sources, or merge into a parent page |
| `unlinked-mention` | link the first mention per section |
| `contradiction` | resolvable from the sources? propose the `[!resolved]` rewrite. Otherwise keep and list it in the report |
| `pending` | list in the report; ingest only if the user asks |

Done when `llm-wiki lint` shows 0 errors and every remaining warning is one you chose to keep, with a reason, or one that waits on a proposal.

## 2. Semantic

`llm-wiki stats` for hubs and tags. Read `wiki/overview.md`, then the hub pages and every page updated since the last `lint` entry in `llm-wiki log`. Look for:

- **Contradictions** between pages that the callouts miss: same entity, different facts.
- **Superseded claims**: a page asserting what a later source revised.
- **Missing pages**: a concept three pages explain in passing and none defines.
- **Missing cross-references**: pages on related things that never link.
- **Thin synthesis**: `overview.md` threads that no longer match the pages under them.
- **Gaps**: questions the wiki raises and cannot answer.

Add the missing cross-references. Everything else found here is a proposal, each with the source pages that settle it. For gaps, propose too - a web search may fill them, but new material enters through `raw/` and `/wiki-ingest`, with the user's go-ahead.

## 3. Report and log

Report: fixed (counts by code), proposals waiting for the user's word, open contradictions, kept warnings, 3-5 questions worth investigating, 3-5 sources worth finding.

Apply the proposals the user approves, then `llm-wiki lint` again.

`llm-wiki log lint "<N> fixed, <M> open" -m "<the report's key lines>"`
