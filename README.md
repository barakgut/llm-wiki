# LLM Wiki

LLM Wiki is a [Claude Code](https://claude.com/claude-code) plugin that turns a folder into a personal knowledge base Claude writes and maintains for you.

You collect sources and ask questions. The agent reads each source once, files what it learned into interlinked markdown pages, and keeps those pages current as more sources arrive. Later questions are answered from the wiki, so the agent does not have to work everything out again from the raw documents.

You read the wiki in [Obsidian](https://obsidian.md) or any markdown viewer. The agent edits it from Claude Code.

What you get:

- Cited claims. Entity and concept pages cite the source page each fact came from. When two sources disagree, both pages carry a contradiction flag and both versions are kept.
- PDFs read in full: the text, every embedded image and a render of every page. A 300-page standard is cut into chunks and each chunk goes to a subagent with a fresh context, so page 290 gets the same attention as page 5.
- Protected sources. A hook blocks the agent from changing or deleting anything in `raw/`.
- A lint pass that finds broken links, orphans, stale pages, duplicates, undescribed figures and coverage gaps.
- Plain files in a folder you own: markdown, wikilinks and YAML frontmatter. The tooling uses the Python standard library only, with no database, embeddings or server.

## Install

In Claude Code:

```
/plugin marketplace add barakgut/llm-wiki
/plugin install llm-wiki@llm-wiki
```

Requirements:

- Claude Code, on macOS, Linux or WSL
- Python 3.9+ as `python3`
- `poppler-utils` for PDFs: `sudo apt install poppler-utils` / `brew install poppler`

## Quick start

```
mkdir ~/wikis/research && cd ~/wikis/research && claude
```

1. Run `/llm-wiki:init`. It scaffolds the wiki in the current folder. To put it elsewhere, use `/llm-wiki:init ~/some/dir --name "Research" --git`. Then restart `claude` in the wiki folder so the session picks up its schema and settings.
2. Put a source into `raw/`: a markdown or text file, a PDF, an image.
3. Run `/llm-wiki:ingest`, or `/llm-wiki:ingest raw/<file>` to pick the source yourself.
4. Ask questions.

Each session starts with a status line for the agent: page counts, sources waiting to be ingested, recent log entries.

## Using it with an existing code project

The wiki works well as the place where a codebase gets explained: what each module does, why it was built that way, where the documents and the code disagree. Ingest reads what is in `raw/`. It does not crawl your repository, so you decide what goes in.

Keep the wiki in its own subfolder, for example `docs/wiki`. Init writes `AGENTS.md`, `.gitignore` and `.claude/settings.json` and keeps any file that already exists, so at the repository root your project's own `AGENTS.md` would stay and the wiki would have no schema. In a subfolder nothing collides, and the hooks only act on files inside the wiki, so your code is not affected.

1. From the repository root, in Claude Code:

   ```
   /llm-wiki:init docs/wiki --name "My Project"
   ```

   Leave out `--git`. The wiki is committed with the rest of the repository.

2. Start a session in the wiki folder. A wiki needs its own session.

   ```
   cd docs/wiki && claude
   ```

3. Copy in the documents the project already has: the README, design docs, ADRs, specs, PDFs of the standards you implement. Copy them; `raw/` holds snapshots the agent can read and never change.

   ```
   cp ../../README.md raw/project-readme.md
   cp ../architecture.md raw/
   ```

4. Add code as snapshots, one module per file. From the repository root:

   ```
   { for f in $(git ls-files src/auth); do printf '\n===== %s =====\n' "$f"; cat "$f"; done; } > docs/wiki/raw/$(date +%F)-src-auth.txt
   ```

   This joins every tracked file under `src/auth` into one text file with a header line per file. The date in the name tells snapshots of the same module apart.

5. Ingest one file at a time with `/llm-wiki:ingest raw/<file>`. The agent shows its takeaways and waits for your steer. For code, say what you want kept, for example "how a request flows through this module and why, skip the line-by-line detail". If you want modules and services as entity pages and design decisions as concept pages, tell the agent to record that in `AGENTS.md` so later sessions do the same.

6. Ask questions in the wiki session: "how does login work", "which modules touch the billing tables", "compare what the ADR says about caching with what the code does". Answers cite the pages they came from, and a comparison like the last one is filed into `wiki/analyses/`.

7. When a module changes enough to matter, take a new dated snapshot and ingest it. The agent merges it into the existing pages and flags where it contradicts what they say.

8. Commit `docs/wiki` along with your code.

To use the wiki from a coding session at the repository root, start Claude Code with `LLM_WIKI_ROOT` set to the wiki's absolute path. The `llm-wiki` CLI and the hooks then act on that wiki.

```
LLM_WIKI_ROOT="$PWD/docs/wiki" claude
```

## What is where

```
├── raw/            your sources. You add files here; the agent never changes them.
│   └── assets/     images, and what gets extracted from PDFs
├── wiki/           the knowledge base. The agent writes it; you read it.
│   ├── sources/    one page per source: what it says (a long source adds -claims, -figures, -errata pages)
│   ├── entities/   people, organisations, products, places, works
│   ├── concepts/   ideas, methods, themes
│   ├── analyses/   answers to your questions that were worth keeping
│   ├── overview.md the running synthesis: thesis, threads, open questions
│   ├── index.md    catalog of every page (generated)
│   └── log.md      timeline of ingests, queries and lint passes (append-only)
├── AGENTS.md       the schema: the rules the agent follows in this wiki
├── .llm-wiki/      marks the folder as a wiki; holds your overrides, if any
└── .claude/        settings.json: lets the agent run the llm-wiki CLI without asking
```

`raw/` and `wiki/` are your data. The skills, subagents, hooks and CLI that operate on them live in the plugin and update with it.

## Commands

You run `/llm-wiki:init`, `/llm-wiki:ingest` and `/llm-wiki:lint` yourself. `/llm-wiki:query` runs on its own whenever you ask something the wiki might answer.

### Ingest

1. The agent reads the whole source.
2. It gives you the key takeaways, what is new, and what contradicts the wiki, then waits for your steer on what to emphasize. Say "ingest unattended" or "batch ingest everything pending" to skip the wait.
3. It writes a source page, updates every entity and concept page the source touches, creates the missing ones, flags contradictions, and revises the overview.
4. It runs the lint check, appends to the log, and reports what it changed plus follow-up questions.

One source typically touches 5-15 pages. You can also paste text or give a URL, and the agent saves it into `raw/` first.

PDFs are ingested as full text plus every image. The agent extracts the text layer, every embedded image, and a render of every page into `raw/assets/<pdf-name>/`, reads all of them, and writes a description of each image. Scanned pages are transcribed. Lint fails until every extracted image has an entry, so no image goes unread. Images under 48px (icons, bullets) and exact repeats are left out and listed in `manifest.json`.

Large PDFs are cut into chunks of at most 15 pages and 30 images. A separate subagent with a fresh context reads each chunk and writes reading notes to `raw/assets/<pdf-name>/notes/`. A final subagent writes the wiki pages from those notes. For a PDF of more than 3 chunks, a sequence of subagents does that, each taking 2-3 notes files. An interrupted ingest resumes at the first chunk without notes. Expect it to take a while and to use many tokens, because every page is looked at as an image.

### Query

The agent searches the wiki, reads the relevant pages, follows their links, and answers with citations like `[[page-name]]`. It tells you what is its own inference and what the wiki does not cover.

Ask for a shape when you want one: "as a table", "as a timeline", "as a slide deck", "chart it".

When an answer is new synthesis, such as a comparison or a connection across several pages, the agent files it into `wiki/analyses/` so it is not lost in chat history. Say "file that" to keep any answer, or "don't file" to skip.

### Lint

Lint has two passes. The mechanical pass looks for broken links, orphan pages, stale pages, stubs, oversized pages, duplicates, unlinked mentions and PDFs with undescribed images. The reading pass looks for contradictions, superseded claims, concepts that deserve a page, and gaps. The agent fixes what the sources settle and reports the rest, with suggested questions and sources to look for. Run it every 5-10 ingests.

### Subagents

The session you talk to stays light. It dispatches two specialised subagents and relays their results.

| subagent | job | writes? |
|---|---|---|
| `llm-wiki:ingester` | reads one source (or one chunk of a large one) and files it into the wiki | yes |
| `llm-wiki:querier` | searches and reads the wiki, returns a cited answer | no |

Each runs in its own context, reads only what its task needs, and returns a short report. You do not call them yourself.

## Guard rails

Three hooks run automatically, and only inside a wiki folder:

- The agent cannot modify or delete existing files in `raw/` (its own reading notes excepted), and cannot hand-edit `index.md` or `log.md`.
- After every wiki edit the page's frontmatter is validated and `index.md` is regenerated.
- On session start the agent is shown the wiki's status.

The hooks catch slips. They are not a security boundary.

## Good habits

- Ingest one source at a time and read the summary. Your steer is what shapes the wiki.
- Edit the wiki through the agent. If you edit a page by hand, tell the agent so it can reconcile.
- To change or remove a source in `raw/`, do it yourself, since the agent is blocked from it, then ask it to re-ingest.
- When you settle on a convention ("always tag by project", "track people's roles"), tell the agent to record it in `AGENTS.md`. That file is how the next session knows.
- Commit to git after each ingest. The history is your undo.

## Obsidian

Open the wiki folder (the one containing `raw/` and `wiki/`) as a vault. Recommended settings, graph filter, web clipper and callout styling are in [docs/obsidian.md](docs/obsidian.md).

## The CLI

The plugin puts `llm-wiki` on the agent's PATH. To use it in your own shell, symlink it: `ln -s <plugin dir>/bin/llm-wiki ~/.local/bin/` (the plugin dir is under `~/.claude/plugins/`). It acts on the wiki containing the current directory.

```
llm-wiki init [dir] [--name "Name"] [--git]   scaffold a wiki, or adopt an existing folder
llm-wiki search "<terms>"                     ranked search over wiki pages (--raw for sources)
llm-wiki links <page>                         what a page links to and what links to it
llm-wiki pending                              sources not yet ingested
llm-wiki lint                                 health check
llm-wiki stats                                status
llm-wiki log                                  recent activity
llm-wiki pdf raw/<file>.pdf                   extract a PDF's text and images
llm-wiki ref [name]                           print a reference document
```

## Customising

Each wiki carries its own conventions in three places:

- `AGENTS.md` holds the rules. Change them by telling the agent, or edit the file directly.
- `.llm-wiki/templates/<type>.md` is your own layout for `source`, `entity`, `concept` or `analysis` pages. Start from [templates/](templates/).
- `.llm-wiki/references/<name>.md` is your own version of `page-formats`, `pdf-ingest` or `output-formats`. Start from `llm-wiki ref <name>`.

## Adopting an existing folder

`llm-wiki init` in a folder that already has `raw/` and `wiki/` adds only what is missing and overwrites nothing. Pages need the frontmatter described in `llm-wiki ref page-formats`. Run `/llm-wiki:lint` to find what does not conform.

## Development

```
claude --plugin-dir /path/to/llm-wiki      # run Claude Code with a local checkout
python3 -m unittest discover -s tests -v   # smoke tests
claude plugin validate .
```

## Credits

The pattern follows Andrej Karpathy's "LLM wiki" idea: immutable raw sources, an LLM-maintained wiki with an index and a log, and ingest, query and lint workflows governed by a schema file.

## License

MIT
