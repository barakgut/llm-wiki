# Query output formats

Pick by the shape of the question. Anything filed lives in `wiki/analyses/` as an analysis page; binary artifacts go beside it in `wiki/analyses/assets/` and are embedded with `![[file]]`.

| question shape | format |
|---|---|
| lookup, single fact | 1-3 sentences in chat with `[[citations]]`; not filed |
| compare X vs Y (vs Z) | markdown table, one row per dimension, one cited cell per claim |
| how did X evolve | dated timeline list, oldest first |
| what do we know about X | prose synthesis with headed sections |
| quantitative trend | matplotlib chart saved as PNG + the data table it was drawn from |
| present this | Marp deck: frontmatter `marp: true`, slides separated by `---`, one claim per slide |
| relationships between many pages | Obsidian canvas (`.canvas` JSON) or a mermaid graph |

Charts: write the script to `/tmp`, save the PNG to `wiki/analyses/assets/<analysis-slug>.png`, embed it in the analysis page with the data table below it.
