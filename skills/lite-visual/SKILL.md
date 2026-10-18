---
name: lite-visual
description: Use when making, remaking or publishing an Arabic HTML companion (Read / Visual Lite / study guide) for a Compass source or book chapter. HTML only, no PDF.
---

# Visual Lite

One Arabic companion per source (or book chapter): you read the whole source and write an editorial explanation in Egyptian Arabic; the scripts make it a page and publish it to Compass, where **Read** opens it. A companion request for a Compass source means publish; keep it local only when Mahmood says draft, local or preview. Never make a PDF.

You write only `companion.md` ([references/writing.md](references/writing.md) and [references/format.md](references/format.md)). `scripts/build_companion.py` owns the whole design; never write HTML or CSS. The page is code-only: one `article[data-canonical-content=true]`, no scripts, no external resources.

## Steps

Paths are under `/home/mahmud/.hermes/skills/lite-visual/`; one workdir per source, e.g. `~/.hermes/cache/scratch/lv-<item.id>`. Run Python with `$HOME/.local/share/learning-compass/lite-visual-venv/bin/python` (it has `httpx` and `bs4`; recreate with `uv venv` + `uv pip install httpx beautifulsoup4` if missing).

1. **Source.** `GET /capture/:id/record` (`field=item.id,video_title,video_url,creator,content_type`). If `companion.status == "ready"` and no remake was asked, say so and stop.
2. **Extract.** `run_workflow.py prepare '<item.video_url>' --workdir <workdir>` writes `source.txt` and a `lite-visual-source-extraction/v1` receipt via `scripts/extract_source.py` (YouTube captions via yt-dlp; audio, PDFs and caption-less videos via NotebookLM; never local transcription or OCR). If it says `skip this source`, report that and stop. Details: [references/source-extraction.md](references/source-extraction.md).
3. **Read all of `source.txt`**, in chunks if long, before writing.
4. **Write** `<workdir>/companion.md`.
5. **Build.** `build_companion.py <workdir>`. On `"ok": false`, fix the reported line and rebuild.
6. **Publish.**
   ```bash
   run_workflow.py publish --workdir <workdir> --recommendation-id <item.id> --source-url '<item.video_url>' --source-title '<item.video_title>' --upload-basename <ascii-slug-of-title>
   ```
   Draft/local: `finish` with the same arguments minus `--upload-basename` (no network). Chapters add `--chapter-key` (and `--chapter-title`, `--chapter-number`); a claimed job adds `--job-id` and `--worker-identity`; a remake adds `--supersedes-pair-id`. The runner seals the files with the integrity receipt the Worker requires (`lite-visual-linear/v4` contract, `quality_checks=not_run`), sends them in one `POST /artifacts/pairs`, and reads the record back. Rebuild after any edit to `companion.md`.
7. **Report** the Read link (or local file), units and word count.

## Several sources

Resolve the targets, skip ready ones, then `python3 scripts/batch_companions.py start <id> <id> ...`; it runs them one after another. `batch_companions.py status` reports progress; rerun only failures. Never write several companions in one turn or fan out parallel agents.

## Jobs from the app

- **`visualise_source`** may carry `payload.user_instructions` (≤500 chars): use it to choose emphasis and examples only. Publish with `--job-id`/`--worker-identity`; a failed attempt ends with `/fail` and its real error.
- **`fetch_transcript`** (YouTube): claim the job, run `extract_source.py '<payload.source_url>' --output <workdir>/source.txt --manifest <workdir>/source-extraction.json`, and continue only when the receipt is `complete`. Upload it: `curl -sS -F "file=@<workdir>/source.txt;filename=<payload.output.filename>;type=text/plain" -F 'metadata={"role":"transcript","recommendation_id":"<payload.recommendation_id>","source_url":"<payload.source_url>","extraction_method":"<receipt.method>","content_sha256":"<receipt.content_sha256>"}' https://recommendations-worker.mhmudnasr30.workers.dev/artifacts`, then `POST /agent/jobs/:id/complete` with `{ "worker": "<same worker>", "artifact_id": "<id>" }`. If extraction says `skip this source`, `/fail` once with that reason. Write nothing else from a transcript.

Queueing a finished companion, retries and publication errors: [references/publishing.md](references/publishing.md). Interactive Explore pages belong to `explorable-companion`.

## Rules

- One companion per source unless Mahmood asks for a synthesis.
- Only the runner and builder produce and publish the HTML; never hand-edit `companion.html` or a receipt.
- On failure, report the exact stage and error; never fake completion.
