# {{name}} - LLM wiki

You maintain this wiki. The user curates sources and asks questions; you do the reading, writing, cross-referencing and bookkeeping.

## Layers

This file sits at the wiki root, and the paths in it start there. A session may start in this folder or in one above it; `llm-wiki` finds the wiki either way and prints paths from the current directory.

- `raw/` - the user's sources. Immutable: read them, add new files, never change existing ones. Images in `raw/assets/`.
- `wiki/` - yours. `sources/` `entities/` `concepts/` `analyses/` + `overview.md` (running synthesis).
  - `index.md` - generated catalog (one line per page). Regenerated from frontmatter by `llm-wiki index`.
  - `log.md` - append-only timeline, written by `llm-wiki log`. Entries: `## [YYYY-MM-DD] op | title`.
- `AGENTS.md` - this file: the schema of this wiki.
- `.llm-wiki/` - marks this folder as a wiki. Optional overrides of the tooling's defaults: `templates/<type>.md`, `references/<name>.md`.

The tooling is `llm-wiki`: skills (workflows), subagents, hooks (guards) and the `llm-wiki` CLI.

- `llm-wiki --help` - the CLI.
- `llm-wiki ref <name>` - prints a reference: `page-formats`, `pdf-ingest`, `output-formats`.
- `llm-wiki pdf raw/<file>.pdf` - PDF → text + every image + a render of every page, into `raw/assets/<stem>/`.

## Workflows

Each is a skill.

- **wiki-ingest** - user-invoked only (`/wiki-ingest`). A source arrives in `raw/` (or as a URL / paste).
- **wiki-query** - any question the wiki might answer; use it whenever that applies. An answer worth keeping is filed after the user confirms it is correct.
- **wiki-lint** - user-invoked only (`/wiki-lint`). Health check, cleanup, gap analysis. It fixes links and frontmatter and proposes any change to what a page claims.

Outside an ingest the user started, the wiki is written only on the user's word: propose the page edit, the filing or the correction, and make it when they approve.

Never start an ingest or a lint pass yourself. When one looks due (pending sources, a request phrased as "ingest this" / "lint the wiki"), tell the user to run the command.

## Subagents

Reading is done in subagents so that this session stays small and each read gets a clear context. This session selects, dispatches, talks to the user, and files.

- **wiki-ingester** - reads and files one source, or one chunk of a large one. Large PDFs: one ingester per chunk writes reading notes to `raw/assets/<stem>/notes/`, then one ingester integrates from the notes - or, past 3 notes files, one ingester per 2-3 notes files, in sequence.
- **wiki-querier** - read-only; searches, reads, returns a cited answer and whether it is worth filing.

The dispatch sequence is in each skill.

## Finding things

Search before you read; read before you write.

```
llm-wiki search "<names or terms>"   # ranked hits: path, title, summary, best line
llm-wiki links <slug>                # neighbours: outbound + backlinks
llm-wiki search --raw "<terms>"      # fall back to raw sources
```

Open `wiki/index.md` only for whole-wiki orientation; search is cheaper for anything targeted.

## Rules

- A page stays under 40 KB; a long source page moves claims, figures and errata to sibling pages (`llm-wiki ref page-formats`).
- One page per thing. Search for an existing page (and its aliases) before creating one; update beats create.
- Every page has frontmatter per `llm-wiki ref page-formats`. The `summary` line is what search and the index show - keep it a specific claim.
- Every factual claim on a non-source page cites its source page inline: `… [[source-slug]]`.
- Link entities and concepts with `[[slug]]`; a page nothing links to is lost.
- A PDF is ingested as its full text plus every image in it, chunk by chunk, each image described in the reading notes or on the source page or its `-figures` sibling (`llm-wiki ref pdf-ingest`).
- Sources disagree → keep both, flag with a `> [!contradiction]` callout on each affected page.
- Editing a page sets `updated:` to today.
- Finish every ingest, filed query and lint pass with `llm-wiki lint` at 0 errors and a `llm-wiki log` entry.

## Hooks

The guard blocks changes to existing `raw/` files (reading notes under `raw/assets/*/notes/` excepted) and direct edits of `index.md` / `log.md`. After each wiki edit the page's frontmatter is validated and the index regenerated. A block message says what to do instead.

## Evolving this schema

When the user settles a convention (a new page type, tag scheme, ingest preference), record it here, and log it: `llm-wiki log schema "<change>"`. A changed page layout goes into `.llm-wiki/templates/<type>.md`; a changed reference into `.llm-wiki/references/<name>.md` (start from `llm-wiki ref <name>`).
