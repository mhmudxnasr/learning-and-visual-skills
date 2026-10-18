# Publishing, jobs and recovery

## Target

Bind `--recommendation-id`, `--source-url` and `--source-title` to the record's `item.id`, `item.video_url` and `item.video_title` exactly as saved, even when the saved title is a generic host label (the Arabic `title:` is separate). The first `finish`/`publish` writes `work-item.json`; later runs must use the same target. To correct the title, fix `work-item.json` and rerun; never edit a receipt. `--upload-basename` is an ASCII slug of the title (plus chapter), e.g. `the-negotiators-dilemma`.

## What the runner does

`finish` seals the workdir: it writes the two placeholder provenance files the Worker still hashes (`source-scope.json`, `coverage-ledger.json`) and a signed `lite-visual-html-integrity/v1` receipt (`verification_scope=integrity-only`, `quality_checks=not_run`). The receipt binds bytes to the source; it is not a quality check. An unchanged workdir reuses its receipt.

`publish` also reads `/artifacts/pair-contract`, then sends the HTML and receipt in one `POST /artifacts/pairs` (`companion_format: "html"`, no PDF) and reads the source record back. The Worker checks the signature, hashes, target and inert HTML and stores everything atomically. If the Worker doesn't list the receipt schema, keep the local HTML and report it.

After an ambiguous upload (5xx, timeout) the uploader reconciles through reads without repeating the POST; if it reports `mutation_outcome_unknown`, read the source and pair state before one deliberate retry. 4xx errors are final.

## Jobs

`publish --job-id … --worker-identity …` claims the job, heartbeats and advances its checkpoints (the API keeps the v4 stage names; `render_pdf` renders nothing). An expired lease returns to `retry` after two minutes. A busy workdir fails immediately: find the other runner instead of starting a duplicate.

## Queue

To put a companion's source in the Queue: `POST /capture/:id/triage` with `action:queue` through the site operator, verify `item.learning_state=queued`, respect the 20-item cap. Publish a still-local companion with `publish`; reuse a ready one. Report the Queue and companion outcomes separately.

## Old companions

Historical HTML/PDF pairs stay readable and retirable. Thread batch replacement (corpus) accepts only HTML/PDF pairs and this runner has no corpus mode; report that limitation instead of restoring PDFs. The old PDF toolchain is in `~/archive/lite-visual-pdf/`.
