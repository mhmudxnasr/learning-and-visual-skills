# Efficient batches without shallow writing

Distinguish independent companions from explicit synthesis. “Visualize these sources” defaults to one companion per source; “combine/compare these sources in one companion” uses the synthesis section below. A collection of inputs alone does not authorize merging their identities.

## Independent companions

A request for 100 sources contains 100 individual teaching tasks. Resolve the ordered target set and keep one workspace per source or chapter, with stable source identity and chapter ownership. Use existing manifests and jobs; do not invent a second tracking system.

For more than one HTML/PDF item, fan out independent source-reading and authoring agents by default; Mahmood has given standing authorization, so do not ask again unless he explicitly requests sequential work or no delegation. Assign one item and isolated workspace per agent, using bounded parallel batches within the available agent limit. Pass exact source/target identities, accepted extraction paths, full-reading requirements, and required teaching/design skills to every agent. Each agent writes one source's connected explanation at a time. Read its complete accepted text and give its ending as much attention as its opening. Keep finished source bodies out of the active context. For a long source, read consecutive sections, preserve their boundaries and terminology, then continue from the real source and the previous authored transition.

The removed review paperwork and exhaustive quality audits are not batch prerequisites. Do not require per-120-word claims, four editorial passes, meaning-unit forms, a source appendix, a validator sweep, or a report per item. Revise actual defects as part of writing; do not manufacture revisions to prove effort. `audit_pair_set.py` binds the completed files to the ordered corpus manifest with an integrity-only receipt; it does not restore those quality stages.

Independent acquisition and rendering can overlap with authoring in separate workspaces. Keep at most two local extraction/render processes active unless measurements justify more. For finished articles, `node scripts/render_batch.mjs jobs.json [concurrency]` (jobs: `[{html,pdf,receipt}]`) renders them in one shared Chromium, two at a time by default, isolating each in its own context and reporting per-item pass or fail; it counts as one render process under this cap. Rendering is not a substitute for the per-item `finish` receipt. Await each result before treating its files as complete; never allow two writers in one workspace. Publication and corpus activation retain their existing ordered single-owner transaction rules: the parent coordinates rendering, publishes, and verifies every exact target. Authoring agents return actual file paths and source-reading coverage, not publication claims. Verify their artifacts before using them; never treat a child summary as proof of completion. The two-process local extraction/render cap does not limit the number of independent authoring agents.

Reuse the accepted extraction and an unchanged hash-matched pair. Extract a book once, then work from each exact chapter. Load common teaching/design guidance once per active context, and retrieve the next source when it is needed. Never draft dozens of unrelated explanations through a shared template loop.

At a real interruption, record the existing workspace, source boundary, terminology, unfinished section, and next action. Resume those files instead of rereading the entire completed batch. A budget or context limit changes the truthful completion count, not the required teaching depth.

Report the counts actually authored, rendered, staged, activated, and blocked when those states differ. Do not call integrity-only pairs quality-validated. The aggregate publication checks still bind each target's exact identity, hashes, job, and supersession lineage; they must not silently claim editorial or layout approval.

Use [publication-and-recovery.md](publication-and-recovery.md) for publication and [efficient-workflow.md](efficient-workflow.md) for measured bottlenecks.

## Explicit synthesis: local HTML and PDF

Read each accepted source completely, keeping its exact identity, extracted text, and complete hash-bound extraction receipt in a separate source workspace. Organize the explanation around the reader's stated question and shared themes. Preserve substantive reasoning and qualifications without imposing a compression target. Merge equivalent claims only when their subject, definition, period, and units match; keep complementary detail with its topic. Retain each contributing source's location beside the combined explanation or figure. No second content schema or mandatory concept ledger is needed.

For material disagreements, use a compact comparison showing the question, each source's position and location, and why they differ when the evidence explains it. Distinguish genuine disagreement from changes in population, measurement, or time. Newer publication alone does not settle a methodological or interpretive dispute. Resolve only what the sources support; label an editorial judgment and leave unresolved differences visible. The ordinary restrictions on independently authenticating religious material still apply.

The current `finish`/`publish` contract binds one source target and one extraction receipt. Do not concatenate inputs into a pretend single-source receipt, attribute the synthesis to one recommendation, or pass it through the signed pair/corpus publication path. Author the combined canonical article in a separate output directory and render it with the existing renderer:

```bash
node /home/mahmud/.hermes/skills/lite-visual/scripts/render_pdf.mjs \
  /abs/synthesis/companion.html /abs/synthesis/companion.pdf \
  /abs/synthesis/render-receipt.json
```

Keep every accepted source body and extraction receipt with the synthesis workspace. Apply the usual Arabic teaching, static-media rules, and focused HTML/PDF layout check. The renderer's `lite-visual-render/v1` receipt binds the HTML and PDF hashes; it is not a signed source/target integrity receipt or evidence that every claim was verified. Return both local files and state that combined-source publication is unsupported by the current pair contract. A request for publication does not justify inventing source IDs or weakening that contract; preserve the completed local files and identify the limitation.
