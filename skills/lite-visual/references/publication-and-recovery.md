# Pair integrity, publication, and recovery

## Render once

The canonical Arabic HTML is the only reading body. Use `scripts/render_pdf.mjs` through `run_workflow.py finish` or `publish`. Chromium waits for fonts, blocks external dependencies, and prints tagged A4 output with heading bookmarks. No second PDF body or forced complete-source appendix is created.

The direct path checks a complete extraction bound to `source.txt`, exact target identity, a non-empty canonical article, unchanged inputs during rendering, and the HTML/PDF hashes returned by the renderer. It signs `lite-visual-integrity/v1` with `verification_scope=integrity-only` and `quality_checks=not_run`. Signing proves which bytes and assertions belong together; it does not establish source coverage, literary quality, contrast, responsive layout, pagination, or PDF text parity.

The old `source-scope.json` and `coverage-ledger.json` filenames and hash columns remain for API/job compatibility. Direct records contain machine-written source/authoring provenance, empty reviewed-scope/claim arrays, and no required editorial evidence. Do not fill them manually.

## Publish the exact pair

Bind `--source-title` to the exact live dossier's `video_title`, even when capture saved a generic host label. An independently verified display title may appear in the article, but using it as publication identity fails target preflight. Correct local `work-item.json` to the observed canonical title and rerun the runner to generate a fresh signed binding; never edit a signed receipt or use an import endpoint as a partial title patch. Report a generic Queue label separately from companion readiness.

The Worker accepts the new integrity receipt alongside historical signed `lite-visual-validation/v6` receipts after the corresponding server release. Existing v6 files retain their original meaning. An older Worker rejects the new schema; preserve the finished local pair and report the deployment dependency instead of inventing passing checks.

The uploader sends both files and the original receipt bytes to `POST /artifacts/pairs` in one request. The Worker verifies the signature, uploaded hashes, source/chapter target, file types, inert code-only HTML, and pair identity; stores both R2 objects; verifies their heads; and commits the pair atomically. Generic single-file Lite Visual uploads remain invalid.

For the new schema, artifact `validation_status=passed` means the integrity/publication contract passed. Metadata explicitly records `verification_scope=integrity-only` and `quality_checks=not_run`; quality assurance remains `unverified`. Never describe this as a layout or editorial pass.

Replacement corpora retain their exact ordered target manifest, signed aggregate identity/hash binding, immutable workflow runs, jobs, R2 checks, and supersession lineage. Use `scripts/audit_pair_set.py MANIFEST --out /abs/registration.json` for a direct batch. It reads each current signed local pair and emits `lite-visual-corpus-integrity/v1`, explicitly without quality approval. No rendering or API mutation occurs. The older pinned `lite-visual-corpus-audit/v1` keeps its separate historical meaning.

The manifest has `thread_id` and an ordered `targets` array. Each target gives `recording_number`, `recommendation_id`, exact `source_url`/`source_title`, absolute `workdir`, `job_id`, `workflow_run_id`, optional `chapter_key`, and current `supersedes_pair_id`. Resolve these from canonical state; never invent IDs. The generated registration body binds the exact manifest and every current file/receipt hash. Submit that body through the normal guarded corpus registration route. Use its exact target hashes when staging; changed files require a fresh binding.

Each replacement stays hidden and its job becomes lease-free `awaiting_activation` until one guarded activation transaction exposes all expected pairs and completes those exact jobs. Do not bypass a corpus mismatch or narrow a target set to force activation. This integrity binding is not an editorial review, layout check, or invitation to rerun the removed quality stages.

A book gets one pair per exact chapter with stable chapter key/title/number. Explicit early Riyadh publication may cover only the user's authorized exact ordered prefix, reported as partial.

## Resume and report

A checksum-matched signed pair is immutable and reusable. A changed input invalidates reuse. Keep the accepted extraction, latest authored HTML, PDF, receipt, and failed-stage output. After an ambiguous upload, read the exact source/pair/job state before retrying the same identity.

The uploader reconciles HTTP 5xx, transport timeouts, and malformed responses through canonical reads without repeating the POST. Standalone recovery requires the exact complete pair, both artifact identities and hashes, matching receipt/chapter ownership, and ready source readback. Corpus recovery retains its staged pair/job/run/hash checks. If readback is absent, unavailable, or mismatched, it reports `mutation_outcome_unknown` with `retry:false` and preserves the original error/request ID. A missing ready pair alone does not prove a delayed request cannot commit; resolve the exact pair/job state before a deliberate same-identity retry. Deterministic 4xx errors are not retried or treated as successful publication.

Local rendering, hidden staging, and live activation are different outcomes. Verify the canonical source exposes the exact activated HTML/PDF pair and the bound job is completed before reporting publication.

The historical exhaustive validator is optional and runs only when explicitly requested. Its [coverage-contract.md](coverage-contract.md) applies only to that audit. It must never become a hidden prerequisite for ordinary direct production.
