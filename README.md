# Learning & Visual Agent Skills

Custom agent skills for Learning Compass notes and source-faithful reading companions.

## Included Skills

### 1. `learning-notes-extractor`
- **Description:** Extracts text and handwritten annotations from PDFs, HTML, or study guides into bilingual (English/Egyptian Arabic) Obsidian notes.
- **Features:** Auto-routes notes to `07 - 🎓 Learning` via Taste Map, embeds source attachments, updates `00 - Table of Contents.md`, links canvas nodes in `Taste Map/Map.canvas`, auto-syncs `Recommendations  — Mahmood.md`, maintains bi-directional `_index.md` maps, and appends `## Related` backlinks.
- **Triggers:** `"make notes"`, `"take notes"`, `"extract notes"`, `/learning-notes-extractor`.

### 2. `lite-visual`
- **Description:** Turns a source (or one book chapter) into one complete Arabic reading companion: a single code-only HTML article. No PDF is rendered.
- **How it works:** `extract_source.py` acquires the whole source (YouTube captions through yt-dlp, NotebookLM for audio, scans and caption-less video). The agent writes the teaching as natural Egyptian Arabic in `companion.md`, and `build_companion.py` renders it into one fixed design (embedded IBM Plex Sans Arabic, SIL OFL). `run_workflow.py` and `seal.py` seal it with an HMAC `lite-visual-html-integrity/v1` receipt that attests source/target binding and file hashes and states that quality checks were not run; `upload_pair.py` publishes it to Learning Compass.
- **Triggers:** Requests to make, remake or publish an Arabic HTML companion (Read / Visual Lite / study guide) for a source or book chapter.
- **Requirements:** Python 3, yt-dlp, and a Learning Compass checkout at `~/recommendations-worker` with `node_modules` for the article extractor; NotebookLM access for audio and scans; a receipt signing key in `LITE_VISUAL_RECEIPT_SIGNING_KEY` or `~/.hermes/secrets/lite-visual-receipt-signing-key` for sealing.

## Installation

Copy the skill directories to your agent skills folder (`~/.hermes/skills/` or `~/.agents/skills/`):

```bash
cp -r skills/* ~/.hermes/skills/
```
