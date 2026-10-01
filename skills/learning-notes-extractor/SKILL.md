---
name: learning-notes-extractor
description: Use when extracting study notes/ink.
---

# Learning Notes Extractor

Explicit bilingual links, named note versions, source-edition continuity and reader-highlight reconciliation use the site operator's [learning-work contract](../workflow/learning-compass-site-operator/references/learning-work.md). Links are optional exact selections, not mandatory scope paperwork. Native `compass_pdf_evidence` retains annotation IDs and modification dates for previewed import; ink and OCR never become verified handwriting through that importer. Highlight acceptance creates a source annotation only. Note extraction, learner-authored Units/cards and companion publication remain separate explicit workflows. A named-note restore preserves current text and canonical ownership; never reconstruct deleted notes through this path.

Preserve precise English claims, quotations, and verbatim handwriting; do not add a separate prose audit.

## Specialist receipt

Keep `intent → target → before → mutation/job → after → evidence → blocker` in the existing operation receipt for every run. Reply naturally with the verified result and any blocker. Use `not_present` or `not_applicable` when the source does not support a section; never invent content to satisfy the schema.

## Site control

Discover note, artifact, session, and job operations from `/agent/capabilities`; execute JSON operations through `/agent/request` with `x-agent-name: learning-notes-extractor`. Keep D1-first ordering, idempotent extraction, no automated recall generation, and HTML-only Lite Visual processing. Binary artifact uploads use canonical multipart `/artifacts` directly.

Create durable learning notes for Learning Compass only after `learning-compass-operating-system` routes an explicit extraction/reprocess request or leases an `extract_notes` job. D1 is canonical; Obsidian is an archive copy only for non-book sources.

## Inputs

- PDF, including stylus-annotated pages
- HTML or web artifact
- Video or podcast transcript
- Direct text
- Hermes `extract_notes` job with `recommendation_id`, `artifact_id`, `r2_key`, or source URL
- Lite Visual HTML artifact with `pair_id`, `artifact_role=html`, and an HTML+PDF companion

## Job workflow

For a leased extraction/reprocess job, read [job completion and payloads](references/jobs.md) before claiming or submitting it. Preserve source/target binding, handwriting separation, anchored Units, idempotent D1 completion, and failure receipts. Process Lite Visual HTML once; its PDF is not a second source. Never create recall drafts or cards.

## Note shape

Default to a simple, scan-friendly retrieval note, not a replay of the HTML. Preserve all distinct hadith and Qur'anic quotations verbatim, add a very short Egyptian-Arabic explanation per quotation, and retain only the essential remaining takeaways; the existing HTML remains the detailed reference. For Arabic religious sources use Arabic only unless requested otherwise. This explicit concise-note preference overrides the longer editorial/bilingual defaults below; never pad the note or start a completeness-gated job solely to satisfy length ratios. Hadith authentication remains opt-in as specified below.

Do not force every source into a five-part template. The default output is one coherent source note with a single primary `body` section containing the complete, readable extraction in source order. Use additional sections only when they materially improve navigation for a long or genuinely multi-part source; never create sections just to satisfy a schema.

Do not manufacture `reaction`, `foundation`, `case_studies`, `exploitation`, or `defense` sections. If the source does not contain a distinct idea, example, vulnerability, or defense, omit that structure instead of writing `not_present`, filler, or generic summary prose. Preserve the source's real hierarchy when it has one, but do not impose an Influence-style outline on unrelated material.

The note should read like a finished editorial article: a precise title, a short orienting opening when supported, a complete evidence-grounded body, useful headings only where the source earns them, and a concise closing synthesis only when supported by the source. Do not split one idea across artificial cards or repeat the thesis in every section. Keep exact numbers, qualifications, anchors, and uncertainty.

Write bilingual source notes: preserve precise English source claims, terminology, names, numbers, and study details, then add a concise natural Egyptian-Arabic explanation of each major idea. Keep technical terms in English when translation would reduce precision. Generated Egyptian interpretation explains the source but is never Mahmood's reflection or personal evidence. Preserve source-original Arabic quotations exactly with their anchors and `rtl` direction.

When the source supports them, include these explicit parts inside the coherent note body:

- **Misconception vs. Truth:** pair each consequential common belief or delusion with the source-supported psychological or scientific reality. Never invent a misconception merely to fill the outline.
- **Case Studies & Experiments:** include every key study or experiment in the source, preserving researchers, year, methodology, sample or conditions, exact findings, qualifications, and limitations when available. State `not specified in the source` rather than guessing a missing researcher or year.

Use Learning Compass-native Markdown only: headings, paragraphs, lists, and ordinary blockquotes. Do not emit YAML frontmatter, Obsidian `[!NOTE]` callouts, wiki links, embeds, `==highlight==` markers, or attachment syntax.

## Writing rules

- Apply the four-year retrieval test: someone reopening only this note years later should recover the source's most useful mechanisms, decision rules, strongest evidence, boundaries, and practical implications in the shortest form that remains informative.
- Optimize for durable retrieval, not chapter replay. Remove repetition, scene-setting, decorative anecdotes, and low-value detail; keep an example only when it explains a mechanism, establishes evidence, marks a boundary, or makes the idea memorable.
- Lead each major idea with the concise Egyptian-Arabic explanation Mahmood can absorb fastest, while retaining the exact English term, claim, study identity, number, or qualification needed for precision.
- Write source-proportional, high-density prose: start with the governing claim or mechanism, preserve exact anchors and qualifications, define necessary terms inline, and separate source evidence from interpretation and uncertainty. Do not force SCQA, evidence tables, or a fixed template when the source does not support them.
- Use precise English for source claims and evidence, paired with approachable Egyptian Arabic for explanation and interpretation. Keep each block in one language so the Scholar reader can place LTR and RTL content in the correct columns.
- Preserve exact numbers and qualifications; do not invent studies, quotes, citations, or handwriting.
- Link claims to the source recommendation and page/time anchor when available.
- For a Lite Visual derivative, distinguish original-source claims from editorial explanation added by the canonical HTML. Native tables, equations, and rare inline SVG are explanatory structure, never independent source evidence or personal thoughts. Anchor factual claims to the original source extraction and its page/timestamp/spine locators.
- Focus on why the idea matters, how it works, and what the source actually demonstrates. Cover failure modes, exploitation, or defenses only when the source supports them; never invent an applied angle to complete a template.
- Avoid generic summaries, repeated filler, and decorative prose.

Use an Influence-style structure only when the source itself supports it. Never force `THE FOUNDATION`, `KEY CASE STUDIES`, `HOW IT'S EXPLOITED`, or `DEFENSE & HOW TO SAY NO` onto unrelated material. Preserve useful source wording and terminology without turning it into decorative headings.

## Qur'an and hadith rule

When the source contains Qur'an or hadith, read [quotation preservation](references/religious-quotations.md). Preserve every distinct quotation and its source wording; verify Qur'anic wording and location. Hadith authentication and fresh lookup require an explicit request.

## Payloads and note replacement

Read [job completion and payloads](references/jobs.md) for `source_note_v2` submission or an explicit multi-lesson note merge. A merge saves and verifies the complete replacement before deleting only explicitly authorized old notes. Preserve personal reflections, source anchors and lesson progress.

## Learning Units

- Keep 1–16 source-worthy Units; every Unit has a stable ID and at least one exact source anchor.
- Never generate a flash card or recall draft from a Unit. Manual card creation is a separate learner action.

## Obsidian archive

This routine archive applies only to non-book sources. A separate explicit Thread download for Obsidian may include book and chapter notes, as Mahmood authorized on 2026-09-05. That download packages existing canonical notes and separate handwriting reflections; it does not authorize automatic book archiving during extraction or any Obsidian-to-D1 writeback. Continue transcribing handwritten annotations faithfully with page anchors and uncertain words.

Archive path:

```text
~/Documents/Obsidian Vault/07 - 🎓 Learning/<Category>/<Branch>/<Leaf>/<Title>.md
```

The archive may embed a copied source from `z - 📎 Attachments`, but it is never read as canonical product state and never drives bidirectional sync.

## Connected skills

- `lite-visual` creates and uploads the pair but never calls extraction automatically. This skill processes its HTML only after a separate explicit extraction/reprocess request.
- `recommendations-worker-ops` owns the API and deployment contract.
- `taste-mapper` processes the user's preserved reflection and every rating into reviewable proposals. It never rewrites the reflection; only evidence-qualified profile/map/scoring proposals may apply automatically.
- `taste-rec` is never invoked by extraction or feedback.

## NotebookLM corpus boundary

The NotebookLM Master Corpus is updated by Hermes during explicit recommendation-feedback handling, not by every extraction or D1 mutation. Source-note English interpretations generated by this skill are not Mahmood's thoughts and must not be uploaded as personal reflections. Only the original source material and clearly marked Mahmood-authored reflection/handwriting/feedback may be used as his personal evidence. Lite Visual HTML/PDF output is never the NotebookLM source; use the original source URL and clean raw extraction.


## Compatibility boundary

Use only capabilities returned by the live registry. New work uses `output_contract=source_note_v2`, source-note dossier reads, and anchored Units without generated recall. Accept `learning_units_v1` only for an already-leased legacy job; never create new v1 work or call an unregistered compatibility endpoint.
