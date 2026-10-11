# LLM Wiki

LLM Wiki is a [Claude Code](https://claude.com/claude-code) plugin that turns a folder into a personal knowledge base Claude writes and maintains for you.

You collect sources and ask questions. The agent reads each source once, files what it learned into interlinked markdown pages, and keeps those pages current as more sources arrive. Later questions are answered from the wiki, so the agent does not have to work everything out again from the raw documents.

The wiki can be a folder of its own, such as a second brain, or a subfolder of a project, where it holds what the code cannot tell you. It works the same way in both.

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

Version 0.2.0 renamed the commands: `/llm-wiki:ingest` is now `/llm-wiki:wiki-ingest`, and the same for `init`, `query` and `lint`. This README writes them in the short form, `/wiki-ingest`.

Requirements:

- Claude Code, on macOS, Linux or WSL
- Python 3.9+ as `python3`
- `poppler-utils` for PDFs: `sudo apt install poppler-utils` / `brew install poppler`

## Quick start

```
mkdir ~/wikis/research && cd ~/wikis/research && claude
```

1. Run `/wiki-init`. It scaffolds the wiki in the current folder. To put it elsewhere, use `/wiki-init ~/some/dir --name "Research" --git`.
2. Put a source into `raw/`: a markdown or text file, a PDF, an image.
3. Run `/wiki-ingest`, or `/wiki-ingest raw/<file>` to pick the source yourself.
4. Ask questions.

Each session starts with a status line for the agent: where the wiki is, page counts, sources waiting to be ingested, recent log entries.

## Using it as a project's knowledge base

Put the wiki in a subfolder of the project and work from the project root, in the same session you code in. The tooling finds a wiki in the current folder, above it, or up to four levels below it (in a very large tree, among the 2,000 folders nearest the top), so there is no second session and nothing to configure.

The wiki is for what the code cannot tell you: architecture decision records, design documents, specifications, the standards you implement, meeting notes, the reasons behind a choice. Leave the code out of it. The agent reads code directly, and a copy in the wiki would only go stale.

1. From the project root, in Claude Code:

   ```
   /wiki-init docs/wiki --name "My Project"
   ```

   Leave out `--git`. The wiki is committed with the rest of the repository. Keep it in a subfolder: init writes `AGENTS.md` and `.gitignore`, and at the project root those would collide with the project's own.

2. Copy documents into `docs/wiki/raw/`. Copy them; `raw/` holds snapshots the agent can read and never change.

3. Ingest one at a time with `/wiki-ingest raw/<file>`. The agent shows its takeaways and waits for your steer.

4. Ask. "Why did we choose event sourcing for the ledger", "what does the standard require for retries", "which decisions touch billing". Answers cite the pages they came from.

5. Commit `docs/wiki` along with your code.

Add these lines to the project's own `CLAUDE.md`, so the agent knows the wiki is there and what to do when it and the code disagree:

```
Project knowledge that is not in the code (decisions, rationale, specs, standards) is in the wiki at docs/wiki. Query it for such questions.
If a wiki page contradicts the code, propose a correction to the page and wait for approval.
```

When one folder holds several wikis, the tooling asks which one you mean. `cd` into one, or start Claude Code with `LLM_WIKI_ROOT` set to its path.

### The tooling inside the project

The tooling can also live in the project itself, so that a clone works with no plugin installed. The same files go under the project's `.claude/`:

```
.claude/skills/       wiki-init, wiki-ingest, wiki-query, wiki-lint
.claude/agents/       wiki-ingester.md, wiki-querier.md
.claude/hooks/        guard.py, post_edit.py
.claude/scripts/      the CLI's code
.claude/bin/llm-wiki  the CLI
.claude/references/   .claude/templates/
.claude/settings.json the hooks and the permission to run the CLI
```

`templates/project-settings.json` is that `settings.json`. The commands are then `/wiki-init`, `/wiki-ingest`, `/wiki-query` and `/wiki-lint`, and the session start hook puts `llm-wiki` on the agent's PATH. Use the plugin or the project copy, not both, or each hook runs twice.

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
└── .claude/        settings.json: lets a session started in the wiki run the llm-wiki CLI without asking
```

`raw/` and `wiki/` are your data. The skills, subagents, hooks and CLI that operate on them are the tooling: the plugin, or the copy under a project's `.claude/`.

## Commands

You run `/wiki-init`, `/wiki-ingest` and `/wiki-lint` yourself. `/wiki-query` runs on its own whenever you ask something the wiki might answer. With the plugin the full names are `/llm-wiki:wiki-init` and so on.

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

When an answer is new synthesis, such as a comparison or a connection across several pages, the agent asks whether it is correct and whether to keep it. Accept it, or say what to change and it asks again. The accepted answer is filed into `wiki/analyses/` so it is not lost in chat history. Say "file that" to keep any other answer, or "don't file" to skip the question.

The agent does not change a page while answering. When it finds something in a raw source that a page is missing, it proposes the edit and makes it when you approve.

### Lint

Lint has two passes. The mechanical pass looks for broken links, orphan pages, stale pages, stubs, oversized pages, duplicates, unlinked mentions and PDFs with undescribed images. The reading pass looks for contradictions, superseded claims, concepts that deserve a page, and gaps. The agent fixes links, frontmatter and missing cross-references itself. Anything that changes what a page claims, such as resolving a contradiction, merging duplicates or removing an unsourced claim, it lists as a proposal and applies when you approve. The report ends with suggested questions and sources to look for. Run it every 5-10 ingests.

### Subagents

The session you talk to stays light. It dispatches two specialised subagents and relays their results.

| subagent | job | writes? |
|---|---|---|
| `wiki-ingester` | reads one source (or one chunk of a large one) and files it into the wiki | yes |
| `wiki-querier` | searches and reads the wiki, returns a cited answer | no |

Each runs in its own context, reads only what its task needs, and returns a short report. You do not call them yourself.

## Guard rails

Three hooks run automatically, and act only on files inside a wiki:

- The agent cannot modify or delete existing files in `raw/` (its own reading notes excepted), and cannot hand-edit `index.md` or `log.md`.
- After every wiki edit the page's frontmatter is validated and `index.md` is regenerated.
- On session start the agent is shown where the wiki is and its status.

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

The plugin puts `llm-wiki` on the agent's PATH. To use it in your own shell, symlink it: `ln -s <plugin dir>/bin/llm-wiki ~/.local/bin/` (the plugin dir is under `~/.claude/plugins/`). It acts on the wiki containing the current directory, or the one below it. It prints paths relative to the current directory, and takes path arguments relative to it or to the wiki root.

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

`llm-wiki init` in a folder that already has `raw/` and `wiki/` adds only what is missing and overwrites nothing. Pages need the frontmatter described in `llm-wiki ref page-formats`. Run `/wiki-lint` to find what does not conform.

## Development

```
claude --plugin-dir /path/to/llm-wiki      # run Claude Code with a local checkout
python3 -m unittest discover -s tests -v   # smoke tests, as a plugin and as loose files under .claude/
claude plugin validate .
```

## Credits

The pattern follows Andrej Karpathy's "LLM wiki" idea: immutable raw sources, an LLM-maintained wiki with an index and a log, and ingest, query and lint workflows governed by a schema file.

## License

MIT
