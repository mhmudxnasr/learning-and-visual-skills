# Visual kit: tablet-ready components

Start every new companion from `assets/kit/kit.css` instead of the older approved HTML. The 2026-09-23 references (`approved-cognitive-attraction.html`, `muse-cognitive-attraction.html`) predate the tablet floors (19px body) and fail `render_pdf.mjs`; keep them for composition ideas only. The kit keeps their hierarchy (numbered units, thesis, comparison, sequence, bars) at 24px body / 18pt print.

## Use

1. Write `article.src.html` with `<style>/*@kit*/ …source-specific overrides… </style>`.
2. `python3 scripts/assemble_kit.py article.src.html companion.html` inlines `assets/kit/fonts.css` (IBM Plex Sans Arabic 400/700, OFL) and `kit.css`. `--no-fonts` skips the ~470 KB font.
3. Retune the `:root` tokens after the marker for the source (accent, alert, gold). Keep the roles: accent = structure, alert = contrast/caution, gold = editorial addition.

Worked examples (source form; assemble to view), each passing the tablet floors:

| Source type | File | Shows |
| --- | --- | --- |
| Argument-driven book chapter | `assets/examples/book-chapter.src.html` | thesis + compare, Naskh quotation, term definition, claim/objection/reply table, proposed-mechanism flow |
| Video or talk transcript | `assets/examples/video-transcript.src.html` | timestamp timeline, worked calculation table, formula, linear-vs-compound compare |
| Data-heavy article | `assets/examples/data-article.src.html` | stat row with denominators, scaled bars, group-size table, part-of-whole bar, limits |

Their content is illustrative fixtures, not summaries of real sources.

## Components and their fixed meaning

| Class | Use for | Rule |
| --- | --- | --- |
| `.unit` + `.unit-head` | one idea or question | heading states the idea; number is automatic |
| `.thesis`, `.lead` | the opening claim | once per article |
| `blockquote` + `cite` | source words | Naskh face; attribution and location in `cite` |
| `.compare` | two cases against the same question | second column tinted, heading in alert |
| `table` (`th.num`, `td.num`) | criteria or figures | caption required; put denominators in row headers |
| `.flow` | ordered steps | `data-kind="proposed"` (dashed) when the mechanism is the author's proposal, not shown by the evidence |
| `.timeline` | chronology or talk structure | `.when` carries date or `mm:ss` |
| `.stats`, `.stat` | headline numbers | every number states its own denominator |
| `.bars` (`--v` 0–100) | comparable quantities | shared zero baseline; state the scale in `.scale`; `data-tone="alert"` for the focal bar |
| `.parts` (`--w`) + `.parts-key` | parts of one whole | stated whole; parts must sum |
| `.def`, `.note`, `.warn`, `.example` | definition, editorial addition, limit, added example | fixed label in the leading `<b>`; never for ordinary prose |
| `.takeaway` | closing result | source's conclusion plus its open question |
| `.ref` | page, section, or timestamp | LTR isolate; place beside the claim |

## Constraints the renderer enforces

- Small labels and captions must be non-prose elements (`small`, `figcaption`, `cite`, `caption`, `th`, or `[data-supporting]` on an ancestor); a `<p>` or `<li>` under 20px (screen) or 16pt (print) fails the readability floor. Use `<small class="eyebrow|source|scale|flow-legend">` for those lines.
- Body paragraphs need at least 1.65 line height on screen and 1.7 in print.
- Print styles must keep meaning in grayscale: outlines and hatching replace tint where a tint carries meaning.

## Creative direction: pick a theme and an opening per source

Do not ship the default look for every source. Choose from the material's tone, then retune the tokens if needed. Set `<html lang="ar" dir="rtl" data-theme="NAME">` (`assemble_kit.py` includes `assets/kit/themes.css`).

| Theme | Fits | Character |
| --- | --- | --- |
| *(default)* scholar | argument, essays, general non-fiction | warm paper, ink-blue structure, terracotta contrast |
| `technical` | mechanisms, code, math, engineering | cool white, teal-blue, orange alert, sharp edges |
| `copper` | history, biography, culture | sand paper, copper accent, teal contrast, Naskh headings |
| `data` | studies, statistics, reports | calm green-teal, larger stat numerals, taller bars |
| `devotional` | religious or reflective texts | soft ivory, deep green, Naskh headings, centered gold-ruled quotations (attribution and grading rules in SKILL.md still apply; no automatic authentication) |

Openings (add one class to the first `<section class="unit">`):

| Class | Use when | Notes |
| --- | --- | --- |
| `open-question` | the source is driven by one question | large balanced title with a short alert rule |
| `open-quote` | one quotation carries the source | put a `<blockquote>` before the `<h1>`; the quote becomes the focal point |
| `open-split` | the source overturns a common belief | `.compare` directly under the title, heavy rule |
| *(none)* | default | title, lead, thesis |

Rules for creative choices: a theme changes color and voice, not the type floors; a signature visual (a timeline spine, one central diagram revisited across units) must explain something, not decorate; and every opening still has to show source-bearing content in the first tablet viewport. Verify with `render_batch.mjs` (readability floors) and one tablet-viewport look at the opening.
