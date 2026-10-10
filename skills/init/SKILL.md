---
name: init
description: Scaffold a new, empty LLM wiki in a folder, or adopt an existing folder as one.
disable-model-invocation: true
argument-hint: "[dir] [--name \"Name\"] [--git]"
---

# Init

1. Run `llm-wiki init $ARGUMENTS`. No directory given means the current one; ask before scaffolding into a folder that holds an unrelated project.
2. Relay what it wrote and what it kept. Act on any `legacy` or `settings.json` line it printed, with the user's go-ahead.
3. Tell the user the next step: put a source into `raw/`, then `/llm-wiki:ingest`. A wiki outside the current directory needs its own session: `cd <dir> && claude`.

`AGENTS.md` is the wiki's schema. The user may ask for conventions up front (tag scheme, what to track, language); record them there and log with `llm-wiki log schema "<change>"`.
