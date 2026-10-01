# Direct companion runbook

## Acquire the complete source

Resolve the exact source record and requested publication target. For a combined recommendation-and-Visual-Lite request, let [taste-rec](../../personal/taste-rec/SKILL.md) select the verified winner first. Bind extraction and authoring to that returned source ID and URL, not a preliminary candidate that may be rejected as already known. Then use:

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/run_workflow.py prepare \
  '<URL-or-local-file>' --workdir /abs/work
```

For the accepted Riyadh transcript receipt lane, use the explicit arguments documented in [source-extraction.md](source-extraction.md). Preserve its complete extraction receipt and source bytes. Do not author from a snippet or failed acquisition.

## Write the article

Read [arabic-teaching.md](arabic-teaching.md) and [reading-companion-design.md](reading-companion-design.md). Write `companion.html` as a complete source-specific Egyptian-Arabic explanation. Use one `article[data-canonical-content=true]`, an Arabic RTL root, embedded dependencies, and top-level `@page { size: A4; }`.

There is no manual source-scope or coverage ledger to fill. The runner writes small provenance records under those existing filenames for durable API compatibility. There is no forced source appendix, four-pass editorial review, or exhaustive quality check.

## Finish locally

Before the first render, reuse the successful exact dossier read and bind `recommendation_id`, `source_url` and `source_title` to `item.id`, `item.video_url` and `item.video_title`. Keep the source's independently verified display title in the article, not in place of a different saved title in `work-item.json`. A generic saved host label is not permission to rename the record through an import endpoint. Preserve exact chapter/job ownership. The publisher's live identity guard still applies; recovery belongs to [publication-and-recovery.md](publication-and-recovery.md).

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/run_workflow.py finish \
  --workdir /abs/work \
  --recommendation-id cap_example \
  --source-url 'https://source.example/item' \
  --source-title 'Exact source title'
```

For a chapter, also pass its stable `--chapter-key`. This command makes no publication request. It runs the targeted 820 × 1180 portrait-tablet HTML and print-readability preflight, renders once, seals the pair's exact bytes and source identity, and returns the HTML/PDF paths. The HTML preflight rejects body type below 24px, substantive text below 20px, supporting text below 17px, or cramped leading. The PDF preflight rejects body type below about 18pt, tightly led running text, or supporting text below about 13pt. These are not broad editorial, contrast, accessibility, pagination, or layout audits. An unchanged signed pair is reused. The integrity receipt still explicitly says quality checks were not run.

## Publish when authorized

Use the same target arguments with `publish`; add `--job-id`, `--worker-identity`, chapter metadata, `--supersedes-pair-id`, and `--corpus-id` when applicable. The target in an existing `work-item.json` must match. Preserve every exact audited hash when resuming a staged corpus.

Let `publish --job-id ... --worker-identity ...` claim the pending exact job after authoring and focused layout inspection; the runner owns its subsequent heartbeats and checkpoints. If a job was claimed earlier, heartbeat within its five-minute lease throughout authoring. An expired lease becomes `retry` with a two-minute delay in the current jobs handler; `replay` accepts only failed jobs, not retry jobs. Read the exact state and health, honor eligibility rather than probing repeatedly, and reuse the signed pair when publication resumes.

Read [publication-and-recovery.md](publication-and-recovery.md). The receiving Worker must support `lite-visual-integrity/v1`; older servers reject it. Keep local files and report that contract mismatch. Never forge a v6 receipt or restore removed quality checks just to make an older server accept a pair.

The API retains the v4 checkpoint names for compatibility. Direct `author_html` and `render_pdf` evidence declares `authoring_mode=direct` and zero reviewed scopes/claims. `validate_pair` now records the pair hashes; it is not an instruction to run the historical validator.

Stage progress and time limits go to stderr; results remain JSON on stdout. A busy workspace fails immediately. Diagnose the named failure; do not launch duplicate runners or blindly retry an ambiguous publication.

## Hand a finished companion to the study Queue

Resolve a follow-up such as “push it to the Queue” from the just-delivered source and pair. Use [Learning Compass Site Operator](../../workflow/learning-compass-site-operator/SKILL.md) at its installed path for live state and guarded writes; do not create another recommendation or rerun extraction.

- Read the exact source and current Queue, preserving its verified branch/domain and open Thread association. For an explicit Queue commitment, use the advertised `POST /capture/:id/triage` with `action:queue` and verify `item.learning_state=queued`. An explicit study Start uses the separate pick/session contract; adding to Queue does not by itself mean studying has begun. Respect the existing Queue cap.
- When the request refers to putting the finished companion there, publish its unchanged signed HTML/PDF pair to the same source ID using `publish`. Existing authority in the conversation is sufficient. A request only to queue a video does not independently authorize publishing unrelated local files.
- Reuse an already-ready matching pair. Do not call `/visualise` to regenerate it. Verify Queue state through the guarded client and pair readiness through the publisher's canonical readback; do not repeat successful verification reads.
- Report Queue and companion outcomes separately if one fails. Keep the successful state and local files so the remaining step can resume without repeating the completed mutation.

## Finish, naming, and publication rules

Moved from `SKILL.md` steps 5–8 (unchanged rules):

- Before `finish` or `publish`, rename the final local files from generic names such as `companion.html` and `companion.pdf` to clear, source-specific filenames derived from the verified source title (and chapter number/title when applicable), for example `the-negotiators-dilemma-mesos.html` and `the-negotiators-dilemma-mesos.pdf`. Use a filesystem-safe ASCII slug with stable hyphen separators, preserve the `.html`/`.pdf` extensions, avoid truncating away the identifying title, and add a short stable suffix only when needed to prevent a collision. Keep the HTML/PDF pair's matching basename and pass those renamed files to the publication workflow; never publish generic `companion.*` names when a verified source title is available.
- For single-source companions, use `run_workflow.py finish` for local HTML/PDF, or `publish` for the authorized publication path. For explicitly combined sources, follow the local synthesis path in [batch-authoring.md](references/batch-authoring.md). The single-source runner checks the portrait-tablet HTML and print typography floors, prints with Chromium once, and creates a signed `lite-visual-integrity/v1` receipt. It checks source/target binding, file hashes, a non-empty canonical body, and the render binding. It does not run broad editorial, responsive-layout, contrast, text-enlargement, PDF-pagination, or text-parity audits.
- Reuse an unchanged signed pair by exact hashes. After changing the HTML, render that version again. Never claim a skipped quality check passed: the direct receipt says `verification_scope=integrity-only` and `quality_checks=not_run`.
- Keep atomic HTML/PDF publication, exact-source readback, stable chapter metadata, durable job ownership, and guarded corpus activation. See the publication reference for compatibility and recovery.
