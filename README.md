# Learning & Visual Agent Skills

Custom agent skills for Learning Compass notes and source-faithful reading companions.

## Included Skills

### 1. `learning-notes-extractor`
- **Description:** Extracts text and handwritten annotations from PDFs, HTML, or study guides into bilingual (English/Egyptian Arabic) Obsidian notes.
- **Features:** Auto-routes notes to `07 - 🎓 Learning` via Taste Map, embeds source attachments, updates `00 - Table of Contents.md`, links canvas nodes in `Taste Map/Map.canvas`, auto-syncs `Recommendations  — Mahmood.md`, maintains bi-directional `_index.md` maps, and appends `## Related` backlinks.
- **Triggers:** `"make notes"`, `"take notes"`, `"extract notes"`, `/learning-notes-extractor`.

### 2. `lite-visual`
- **Description:** Turns a source into one complete Arabic reading companion rendered as a linked HTML/PDF pair; books use one pair per chapter.
- **Features:** Source-faithful explanation, concept-fit visuals, two to four Arabic retrieval/self-explanation pauses, answer-before-feedback HTML, matching PDF writing space with later answers, and deterministic source/render validation. It does not create scores, streaks, XP, or a second mastery system.
- **Triggers:** Explicit requests for Lite Visual or a source-based HTML/PDF reading companion.

## Installation

Copy the skill directories to your agent skills folder (`~/.hermes/skills/` or `~/.agents/skills/`):

```bash
cp -r skills/* ~/.hermes/skills/
```
