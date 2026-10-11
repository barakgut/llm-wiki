---
name: wiki-init
description: Scaffold a new, empty LLM wiki in a folder, or adopt an existing folder as one.
disable-model-invocation: true
argument-hint: "[dir] [--name \"Name\"] [--git]"
---

# Init

1. Run `llm-wiki init $ARGUMENTS`. No directory given means the current one; when that folder holds other work, ask for a subfolder first (for example `docs/wiki`).
2. Relay what it wrote and what it kept. Act on any `settings.json` line it printed, with the user's go-ahead.
3. Tell the user the next step: put a source into the wiki's `raw/`, then `/wiki-ingest`. The session stays where it is: a wiki in or below the current folder is found from here.

`AGENTS.md` is the wiki's schema. The user may ask for conventions up front (tag scheme, what to track, language); record them there and log with `llm-wiki log schema "<change>"`.
