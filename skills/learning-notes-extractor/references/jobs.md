## Job workflow

1. Claim work through `POST /agent/jobs/:id/claim`.
2. Resolve the recommendation, artifact metadata, source, pair ID, and proposed map branch from D1.
3. Extract native text first. Use `compass_extract` for the canonical source body and `compass_pdf_evidence` for page-anchored PDF text, native highlights, comments, and ink coordinates when the native plugin is available. Its OCR is uncertain machine text; ink explicitly requires vision review and is never certified verbatim handwriting. Read the saved evidence file and inspect relevant page renders with the existing vision tools. For scans or stylus annotations, render and inspect every relevant page with vision/OCR. If the canonical extractor is blocked by an article-site HTTP 403 but Hermes `web_extract` returns the complete page, use the saved full extraction, isolate the article body from navigation/comments, record `adapter=web_extract`, and preserve the canonical URL; never downgrade to a secondary summary.
4. Treat Mahmood's handwriting as personal reflection, never as a printed source claim. Transcribe it faithfully with page anchors and list uncertain words instead of guessing. Render it as a native note block headed `ملاحظة بخط اليد - صفحة <n>`; do not use Obsidian callout syntax.
5. Build a complete structured source note with `kind: "guide"` or another non-reflection kind and `source_artifact_id`. Never overwrite or return the source note as `kind: "reflection"`.
6. When handwriting exists, also return `reflection: { content, recommendation_id, source_url, page_anchors, uncertain_segments }`. The Worker appends it to the preserved personal reflection and queues Taste Mapper.
7. For every `output_contract=source_note_v2` job, return a hash-bound `extraction` receipt with `contract`, `complete:true`, the real adapter, SHA-256 `source_hash`, exact `source_word_count`, exact submitted `note_word_count`, and `coverage_status:complete|source-bounded`. The Worker rejects thin notes relative to source length, legacy Foundation/Case Studies/Exploitation/Defense templates, generated title suffixes, unanchored Units, duplicate Units, and any submitted recall drafts.
8. Return 1–16 durable `learning_units` only for ideas worth retaining. Every Unit type—not only claims—requires at least one exact page, timestamp, section, quote, URL-fragment, or user-observation anchor. Include user synthesis only when Mahmood supplied it; generated summaries are not his synthesis.
9. Never return `srs_drafts`, `recall`, flash cards, quizzes, or generated recall questions. Recall cards are created only by an explicit learner-authored action outside extraction. Legacy `learning_units_v1` jobs follow the same prohibition.
10. Complete through `POST /agent/jobs/:id/complete`. The Worker writes the source note, sections, extraction receipt metadata, optional handwriting reflection, anchored Units, audit entry, and terminal consolidation receipt to D1. The site presents the source synthesis, Mahmood's separate reflection, retained ideas, and anchors together in one note dossier.
11. Progressive distillation is user-controlled after extraction. Never create claim highlights or synthesis revisions automatically, and never rewrite canonical note sections. A meaningful Unit relation requires a typed relation, plain-language explanation, endpoint-owned source anchoring, and canonical branch ownership; keyword similarity alone is never sufficient.
12. Only after successful completion of a non-book source, write the matching Obsidian archive copy. Never create Obsidian archive copies for books or book chapters. Archive failure never rolls back D1; report it for retry.
13. On failure, call `POST /agent/jobs/:id/fail` with a useful error. Jobs use leases, retries, and idempotency.

For `generator=lite-visual`, process the HTML artifact exactly once. The PDF is its print companion, not a second extraction source. Anchor the note to the original recommendation and source, and retain the shared `pair_id` in the result.

## Source-note v2 shape

Return one source-shaped document, not a pile of generated item cards:

```json
{
  "extraction": {
    "contract": "source_note_v2",
    "complete": true,
    "adapter": "html_readability|youtube_transcript|pdf_text|artifact_html|direct_text|other_real_adapter",
    "source_hash": "<sha256>",
    "source_word_count": 1200,
    "note_word_count": 420,
    "coverage_status": "complete"
  },
  "note": {
    "kind": "guide",
    "title": "<exact clean source title>",
    "abstract": "<one short orientation, no thesis repetition>",
    "sections": [{ "section_key": "body", "label": "Source note", "direction": "auto", "content": "<complete bilingual note with separate English and Egyptian-Arabic blocks>" }]
  },
  "learning_units": []
}
```

Do not append “Source Notes,” “Study Guide,” or another generated suffix to the real title. Do not repeat the abstract inside every section. A short source may yield a short note; a long source must yield proportionally complete synthesis with its mechanisms, examples, numbers, qualifications, counterpoints, and uncertainty intact.

## Multi-lesson note replacement

For an explicit merge, resolve the exact Level and paginate its live lesson metadata; use each lesson's current primary source and ready HTML, not title-search matches or older companion pairs. Repeated or misleading source titles do not override lesson placement. Read all selected HTML bodies, preserve distinct quotations and short explanations, and create one Level-owned note with `stage_id` plus links to every source HTML. Inventory source-owned and Level-owned notes first; unrelated personal reflections sharing the topic remain outside the merge. Save and verify the complete replacement before deleting only the old in-scope notes the user authorized. Preserve a recovery copy and synchronize the non-book Obsidian archive. Never alter lesson completion merely because notes were merged.
