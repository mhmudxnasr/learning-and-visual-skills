# Source coverage contract

Historical exhaustive-audit reference only. Mahmood removed these manual scopes, claims, meaning units, and editorial-review gates from the default workflow on 2026-09-05. Load this file only for an explicitly requested full audit or an existing v6 receipt investigation. Direct production uses machine-written provenance and an honest integrity-only receipt; it must not populate or claim this audit by default.

### 2. Prove gapless source coverage

Create `source-scope.json` using `lite-visual-source-scope/v3`:

```json
{
  "schema_version": "lite-visual-source-scope/v3",
  "source": {
    "sha256": "<sha256 of source.txt>",
    "word_count": 1234,
    "url": "https://source.example/item",
    "title": "Exact source title",
    "kind": "article"
  },
  "spans": [
    {
      "id": "scope-01",
      "word_start": 0,
      "word_end": 100,
      "anchor": "opening through first mechanism",
      "semantic_label": "The source's opening claim and first complete mechanism",
      "boundary_reason": "Ends where the source finishes that mechanism and turns to its first example",
      "summary": "Source-grounded statement of every claim, example, and caveat in this span."
    }
  ]
}
```

The spans must partition every normalized word in `source.txt` contiguously from zero through the final word, with no gaps or overlap. Use semantic boundaries within the installed validator's maximum of 120 normalized words per scope. Each v3 scope needs a reviewed `semantic_label`, `boundary_reason`, and summary. For a long argument use adjacent scopes and preserve its continuity in the article. Do not discard a sentence, quotation, example, or qualification to meet the limit.

Each reviewed span summary must name every hadith, ruling, example, qualification, attribution, correction, definition, and conclusion inside that semantic unit. Each span lands in at least one visible HTML section through `data-source-scope`. Coverage is evidence, not a percentage guessed by the author. A long coherent scope may map to several adjacent authored sections carrying the same scope ID. Keep the article readable by shaping the material with source-derived headings, paragraphs, native lists, blockquotes, definitions, or tables where those structures genuinely fit; never solve density by deleting meaning or by forcing card-like fragments.

Start the manifest with `scripts/build_source_scope.py`; it groups complete paragraphs and sentences around a soft drafting target and computes exact word bounds and source anchors. Its boundaries are proposals, not authorship. Read the complete source, move boundaries to the source's real semantic turns, and replace every `AUTHOR_REQUIRED` summary, semantic label, and boundary reason before validation.

Create `coverage-ledger.json` using `lite-visual-coverage-ledger/v1`. Each `claim-*` clears exactly one fine source scope, repeats that scope's reviewed summary exactly, and binds an exact `source_anchor_text` to an exact `html_anchor_text` inside one meaningful authored `html_section_id`. Every scope must have exactly one claim. When the source has numbered notices, rules, cases, or steps, declare the original identifiers in `source_items`, map every identifier through `source_item`, and preserve those identifiers visibly in the HTML.

## Meaning units and editorial evidence

Each claim also contains `meaning_units`, a non-empty array enumerating the distinct meanings actually present in that scope. Each unit has `kind`, `source_anchor_text`, and `html_anchor_text`. Use `claim`, `definition`, `mechanism`, `example`, `evidence`, `qualification`, `attribution`, `conclusion`, `step`, `quotation`, `context`, `question`, or `narrative` as appropriate. Source anchors must occur in this claim's source scope; authored anchors must occur in its real authored section. Anchors need enough words to identify the relevant passage. Do not produce a one-unit placeholder for a scope containing several distinct points. Keep exactly one parent claim per scope; its units capture the finer detail without turning the article into scope-sized fragments.

Add one `editorial_review` object to the same ledger. Its schema is `lite-visual-editorial-review/v1`:

```json
{
  "schema_version": "lite-visual-editorial-review/v1",
  "language": "egyptian-arabic",
  "reader_goal": "The concrete understanding this source should give Mahmood",
  "assumed_knowledge": "Relevant known competence and the prerequisites explained here",
  "authored_text_sha256": "<digest from the command below>",
  "passes": {
    "fidelity": {"section_id": "mechanism", "anchor_text": "Exact final passage", "note": "Specific omission/overstatement repaired, or specific fidelity evidence verified"},
    "teaching": {"section_id": "mechanism", "anchor_text": "Exact final passage", "note": "The actual reader difficulty and how this passage resolves it"},
    "language": {"section_id": "mechanism", "anchor_text": "Exact final passage", "note": "A concrete language revision or a specifically checked clear explanation"},
    "continuity": {"section_id": "conclusion", "anchor_text": "Exact final passage", "note": "How the ending and transitions retain the source's argument and limits"}
  }
}
```

Perform all four passes over the entire authored text as described in [arabic-teaching.md](arabic-teaching.md). The passage evidence records accountable observations from those passes; it is not permission to review only four passages. Never generate stock “all good” notes or fabricate revisions. These are evidence records, not numeric quality scores.

Get the digest after the final prose revision:

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/validate_artifact.py \
  --authored-digest /abs/work/companion.html
```

The digest covers the parsed authored text, including its headings, quotations, and punctuation, while excluding the runner-managed source edition. CSS-only changes do not pretend that new prose was reviewed; any authored text change requires a fresh review digest and updated passage evidence. The ledger itself is already hashed in the signed v6 receipt. New validations require this evidence. Earlier immutable signed receipts remain historical receipts, not proof of review under this editorial contract.

The validator establishes exact evidence locations and hash binding. It cannot determine whether every nuance was identified or whether Egyptian Arabic reads naturally. The author remains responsible for those judgments and must not describe a mechanical pass as proof of semantic or literary quality.
