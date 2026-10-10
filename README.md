# LLM Wiki

A personal knowledge base that Claude writes and maintains for you - as a [Claude Code](https://claude.com/claude-code) plugin.

You collect sources and ask questions. The agent reads each source once, files what it learned into a set of interlinked markdown pages, and keeps those pages current as more sources arrive. Knowledge accumulates in the wiki instead of being re-derived from the raw documents on every question.

You read the wiki in [Obsidian](https://obsidian.md) (or any markdown viewer). The agent edits it from Claude Code.

- **Every claim is cited.** Entity and concept pages cite the source page each fact came from; contradictions between sources are flagged on both pages, not silently resolved.
- **PDFs are read whole.** Full text, every embedded image and a render of every page. A 300-page standard is cut into chunks, each read by a subagent with a fresh context, so page 290 gets the same attention as page 5.
- **Your sources are safe.** A hook blocks the agent from changing or deleting anything in `raw/`.
- **It stays healthy.** A lint pass finds broken links, orphans, stale pages, duplicates, undescribed figures and coverage gaps.
- **Plain files.** Markdown, wikilinks and YAML frontmatter in a folder you own. Python standard library only; no database, no embeddings, no server.

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

1. `/llm-wiki:init` - scaffolds the wiki in the current folder (`/llm-wiki:init ~/some/dir --name "Research" --git` for elsewhere). Restart `claude` in the wiki folder so the session picks up its schema and settings.
2. Put a source into `raw/` - a markdown or text file, a PDF, an image.
3. `/llm-wiki:ingest` (or `/llm-wiki:ingest raw/<file>`).
4. Ask questions.

On session start the agent gets a status line: page counts, sources waiting to be ingested, recent log entries.

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

`raw/` and `wiki/` are your data. Everything that operates on them - skills, subagents, hooks, the CLI - lives in the plugin and updates with it.

## Workflows

| command | runs |
|---|---|
| `/llm-wiki:init` | when you call it |
| `/llm-wiki:ingest` | when you call it |
| `/llm-wiki:lint` | when you call it |
| `/llm-wiki:query` | on its own, whenever you ask something the wiki might answer |

### Ingest

1. The agent reads the whole source.
2. It gives you the key takeaways, what is new, and what contradicts the wiki, then waits for your steer on what to emphasize. Say "ingest unattended" or "batch ingest everything pending" to skip the wait.
3. It writes a source page, updates every entity and concept page the source touches, creates the missing ones, flags contradictions, and revises the overview.
4. It runs the lint check, appends to the log, and reports what it changed plus follow-up questions.

One source typically touches 5-15 pages. You can also paste text or give a URL; the agent saves it into `raw/` first.

**PDFs** are ingested as full text plus every image. The agent extracts the text layer, every embedded image, and a render of every page into `raw/assets/<pdf-name>/`, reads all of them, and writes a description of each image. Scanned pages are transcribed. Lint fails until every extracted image has an entry, so nothing is silently skipped. Images under 48px (icons, bullets) and exact repeats are left out and listed in `manifest.json`.

**Large PDFs** are cut into chunks of at most 15 pages and 30 images. Each chunk is read by a separate subagent with a fresh context, which writes reading notes to `raw/assets/<pdf-name>/notes/`; a final subagent writes the wiki pages from those notes - for a PDF of more than 3 chunks, a sequence of them, each taking 2-3 notes files. An interrupted ingest resumes at the first chunk without notes. Expect it to take a while and to use many tokens: every page is looked at as an image.

### Query

The agent searches the wiki, reads the relevant pages, follows their links, and answers with citations like `[[page-name]]`. It tells you what is its own inference and what the wiki does not cover.

Ask for a shape when you want one: "as a table", "as a timeline", "as a slide deck", "chart it".

Answers that are new synthesis - a comparison, a connection across several pages - are filed into `wiki/analyses/` so they are not lost in chat history. Say "file that" to keep any answer, or "don't file" to skip.

### Lint

A mechanical pass (broken links, orphan pages, stale pages, stubs, oversized pages, duplicates, unlinked mentions, PDFs with undescribed images) followed by a reading pass (contradictions, superseded claims, concepts that deserve a page, gaps). The agent fixes what the sources settle and reports the rest, with suggested questions and sources to look for. Run it every 5-10 ingests.

### Subagents

The session you talk to stays light: it dispatches two specialised subagents and relays their results.

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

They catch slips; they are not a security boundary.

## Good habits

- Ingest one source at a time and read the summary; your steer is what shapes the wiki.
- Edit the wiki through the agent. If you edit a page by hand, tell the agent so it can reconcile.
- To change or remove a source in `raw/`, do it yourself - the agent is blocked from it - then ask it to re-ingest.
- When you settle on a convention ("always tag by project", "track people's roles"), tell the agent to record it in `AGENTS.md`. That file is how the next session knows.
- Commit to git after each ingest; the history is your undo.

## Obsidian

Open the wiki folder (the one containing `raw/` and `wiki/`) as a vault. Recommended settings, graph filter, web clipper and callout styling: [docs/obsidian.md](docs/obsidian.md).

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

Each wiki carries its own conventions:

- `AGENTS.md` - the rules. Change them by telling the agent, or edit directly.
- `.llm-wiki/templates/<type>.md` - your own layout for `source`, `entity`, `concept` or `analysis` pages. Start from [templates/](templates/).
- `.llm-wiki/references/<name>.md` - your own version of `page-formats`, `pdf-ingest` or `output-formats`. Start from `llm-wiki ref <name>`.

## Adopting an existing folder

`llm-wiki init` in a folder that already has `raw/` and `wiki/` adds only what is missing and overwrites nothing. Pages need the frontmatter described in `llm-wiki ref page-formats`; run `/llm-wiki:lint` to find what does not conform.

## Development

```
claude --plugin-dir /path/to/llm-wiki      # run Claude Code with a local checkout
python3 -m unittest discover -s tests -v   # smoke tests
claude plugin validate .
```

## Credits

The pattern - immutable raw sources, an LLM-maintained wiki with an index and a log, and ingest / query / lint workflows governed by a schema file - follows Andrej Karpathy's "LLM wiki" idea.

## License

MIT
