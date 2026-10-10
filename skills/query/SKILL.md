---
name: query
description: Answer a question from the wiki with citations and file valuable answers back as analysis pages. Use when the user asks what the wiki/their notes/sources say, asks to compare, summarize, trace or explain something covered by the wiki, or asks for a table, deck or chart built from it.
---

# Query

The wiki is the first stop; raw sources are the fallback; your own knowledge is labelled as such.

Main session: a lookup one search line or one page settles, answer directly. Anything wider goes to the `llm-wiki:querier` subagent - give it the question and the wanted format; independent questions go to separate queriers in parallel. Relay its answer, then do step 6 when it reports `File-worthy: yes`. A subagent runs steps 1-5.

1. **Split** the question into the sub-questions it needs answered.
2. **Search.** `llm-wiki search "<terms>"` per sub-question, using the entity/concept names rather than the question's phrasing. Filters: `--type`, `--tag`, `-n`. The result line (title + summary + best line) is usually enough to decide whether to open a page. For broad "what's in here" questions read `wiki/index.md` or `wiki/overview.md` instead.
3. **Read** the top hits. Widen with `llm-wiki links <slug>` and read neighbours that bear on the question. Done when every sub-question has a page that answers it or is a confirmed gap.
4. **Fall back** for gaps: `llm-wiki search --raw "<terms>"` and read the raw file at the matching line. A gap that raw sources fill means the wiki is missing something - fix the page as part of answering.
5. **Answer.** Every wiki-backed claim carries its `[[slug]]`. Mark inference as inference and outside knowledge as not-from-the-wiki. Name the gaps. Choose the format from `llm-wiki ref output-formats` when the question wants a table, timeline, deck or chart.
6. **File back** when the answer is a synthesis the wiki did not already contain - a comparison, a connection across 3+ pages, a resolved contradiction - or the user asks to keep it:
   - `llm-wiki new analysis "<Title>" --summary "<the answer in one line>" --sources <slugs>`, fill it, set `question:`.
   - Add a `[[analysis-slug]]` link from each page it draws on, so it is reachable.
   - `llm-wiki lint --errors` clean, then `llm-wiki log query "<question>" -m "filed: <slug>"`.

   Lookups that restate one page are answered in chat and left unfiled.
