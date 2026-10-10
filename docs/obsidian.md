# Obsidian setup

## Open the vault

**Open folder as vault** and choose **this folder** (the one containing `raw/` and `wiki/`), not `wiki/` itself. Wiki pages embed images that live in `raw/assets/`, and those only resolve when both folders are inside the vault. `.claude/` and `.llm-wiki/` start with a dot, so Obsidian does not show them.

## Settings

**Settings → Files and links**

| setting | value | why |
|---|---|---|
| Use [[Wikilinks]] | on | the wiki links pages as `[[page-name]]` |
| New link format | Shortest path when possible | page filenames are unique across the wiki |
| Default location for new attachments | In the folder specified below → `raw/assets` | clipped images land with the sources |
| Default location for new notes | In the folder specified below → `raw` | notes you write are sources, not wiki pages |
| Automatically update internal links | on | renames keep links intact |
| Detect all file extensions | on | PDFs and JSON manifests show up in the file list |

**Settings → Editor**

- Default view for new tabs: **Reading view** - you are reading, not editing.
- Properties in document: **Visible** - shows each page's type, summary, tags and sources.

## Graph view

Open the graph and set the filter to:

```
path:wiki -file:index -file:log
```

This shows only wiki pages and drops the two files that link to everything. Under **Groups**, colour by folder: `path:wiki/sources`, `path:wiki/entities`, `path:wiki/concepts`, `path:wiki/analyses`. Hubs are your main threads; isolated dots are orphans for the next lint.

## Getting sources in

- **Obsidian Web Clipper** (browser extension): set the note location to `raw`. Clip an article, then run `/llm-wiki:ingest`.
- **Download images locally**: Settings → Hotkeys → search "Download attachments for current file" and bind it (e.g. Ctrl+Shift+D). After clipping, press it so the images are saved into `raw/assets/` and the agent can read them.
- PDFs: drop them into `raw/`.

## Optional plugins

- **Dataview** - query the page frontmatter. Example, concepts by number of backing sources:

  ````
  ```dataview
  TABLE summary, length(sources) AS src, updated
  FROM "wiki/concepts"
  SORT length(sources) DESC
  ```
  ````

- **Marp Slides** - preview the slide decks the agent produces.

## Contradiction callouts

The agent marks disagreements between sources as `> [!contradiction]` and settled ones as `> [!resolved]`. To make them stand out, save this as `.obsidian/snippets/wiki.css` and enable it under Settings → Appearance → CSS snippets:

```css
.callout[data-callout="contradiction"] { --callout-color: 233, 49, 71; --callout-icon: lucide-swords; }
.callout[data-callout="resolved"]      { --callout-color: 8, 185, 78;  --callout-icon: lucide-check-circle; }
```

Find all open ones by searching Obsidian for `[!contradiction]`.
