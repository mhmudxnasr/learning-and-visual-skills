# Learning & Visual Agent Skills

Custom agent skills for Obsidian vault learning workflows and interactive visual HTML artifact generation.

## Included Skills

### 1. `learning-notes-extractor`
- **Description:** Extracts text and handwritten annotations from PDFs, HTML, or study guides into bilingual (English/Egyptian Arabic) Obsidian notes.
- **Features:** Auto-routes notes to `07 - 🎓 Learning` via Taste Map, embeds source attachments, updates `00 - Table of Contents.md`, links canvas nodes in `Taste Map/Map.canvas`, auto-syncs `Recommendations  — Mahmood.md`, maintains bi-directional `_index.md` maps, and appends `## Related` backlinks.
- **Triggers:** `"make notes"`, `"take notes"`, `"extract notes"`, `/learning-notes-extractor`.

### 2. `lite-visual`
- **Description:** Transforms dense articles, papers, or reports into single-file, offline-first interactive HTML comprehension engines.
- **Features:** Pedagogical reordering by prerequisite, interactive visual widgets, plain-language B2 English with clickable glossary, zero AI design tells, offline system font fallbacks.
- **Triggers:** When `"visual"` and `"lite"` are said together.

## Installation

Copy the skill directories to your agent skills folder (`~/.hermes/skills/` or `~/.agents/skills/`):

```bash
cp -r skills/* ~/.hermes/skills/
```
