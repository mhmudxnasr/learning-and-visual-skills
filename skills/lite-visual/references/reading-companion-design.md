# Source-derived editorial design

Read [arabic-teaching.md](arabic-teaching.md) first. Develop explanation and visual structure together. Follow the preferred study format in [SKILL.md](../SKILL.md); this reference supplies presentation details, not a competing prose-first default.

Mahmood prefers the compact editorial hierarchy and native visual explanations in the GPT-5.6 cognitive-attraction companion, supplemented by Muse's clear orientation and consolidated results. Use [the annotated visual references](approved-visual-language.md) and their preserved HTML to learn the composition. Carry the useful relationships and reading rhythm into new work, while preserving the new source's full depth and choosing an appropriate palette. This preference permits reusable design techniques, not a fixed article template or copied source claims.

## Art direction

The former `.agents/skills/intent` and `.agents/skills/frontend-design` paths have been retired and must not be recreated. Apply the required Intent and Frontend Design reasoning directly for each companion.

Make a companion the reader wants to spend time with. The design should feel considered from the opening to the last source note: confident typography, purposeful space, a coherent palette, and clear relationships between explanation, quotation, example, and evidence. Keep the learner's single job visible: understand this source without navigating a second system.

Choose a visual direction from the material's tone and structure. A text built around quoted passages may benefit from generous Naskh typography for quotations and quieter explanation; a technical mechanism may need crisp labels, aligned stages, and clearly isolated notation; a historical argument may benefit from a clear chronology. These illustrate decisions, not themes to select or structures to impose. Honor a stated visual preference and otherwise make the choice directly.

Establish a consistent type hierarchy, spacing rhythm, color roles, and one recognizable editorial detail. That detail can be the treatment of section openings, a fine rule, a comparison layout, or the relation between quotations and commentary. Give it a useful role and repeat it selectively. Related chapters can maintain a family resemblance while their content determines their internal composition. Unrelated sources should not inherit a previous companion's styling mechanically.

Prefer semantic reading flow over cards, dashboards, visual chrome, or decorative structure. Preserve strong Arabic readability, natural prose, contrast, responsive reflow, and A4 print behavior. Do not equate a polished result with adding more elements or making everything larger.

Make concrete reading decisions directly; no design-rationale report or metadata form is required. Consider which comparison, sequence, distinction, or source structure the design helps the reader follow. Avoid invented symbolism such as a color “embodying wisdom” or whitespace “representing transformation.”

## Compose the opening and the reading rhythm

Give the opening a clear focal point. Use a distinctive, readable title, a brief source line, and an opening explanation that immediately develops the source's question. Differentiate their scale and weight; keep supporting information quiet but legible. Size the title for its actual Arabic length and natural line breaks. Avoid forced breaks that work only on a wide screen, disconnected Arabic drop caps, or decorative words that compete with the title.

The opening must earn its height. A header containing only a title or a short deck must not consume most of the first screen or push the lesson below the fold. Keep such openings compact enough that the first source-bearing section is visible or clearly begins in the initial viewport. A taller opening is acceptable only when it contains substantial source-grounded material whose layout needs that space. Display type must stay fully visible, comfortably sized, and subordinate to the reading task.

Shape the whole article, not just its header. Keep connected paragraphs together with relatively small gaps; use larger space at a genuine change in the argument. Let a quotation, worked example, comparison, or concise sequence change the reading rhythm where it belongs. Keep supporting prose brief enough that the relationship remains visible. Vary the visual form with the reasoning; do not repeat decorative heading–paragraph–box compositions.

Give each recurring treatment a stable meaning. A quotation's typography and attribution should distinguish it from the author's explanation; an editorial example needs a visible label; a comparison needs aligned criteria. Avoid highlighting every paragraph or repeating a sentence as a decorative pull quote. Use emphasis for the distinction the reader needs to retain, preserving the surrounding explanation.

## Typography, color, and space

- Give display text, body prose, quotations, and supporting labels distinct roles. One well-chosen Arabic family can be enough; use a second only when it provides a meaningful contrast. Set weights the chosen fonts actually support, and choose a deliberate Arabic-capable fallback. Avoid a collection of unrelated font styles.
- Mahmood reads the HTML in portrait on an 11.5-inch Huawei TGR-W09. At that portrait tablet width, use 24px body prose by default with about 1.7–1.8 line height, at least 20px for substantive explanation inside figures, and at least 17px for captions and supporting labels. Keep phone body text around 20–22px rather than inheriting tiny desktop utility type. Tune upward for the font's actual shaping and density. Let headings be expressive without squeezing diacritics, dominating every screen, or clipping long lines.
- Use a comfortable reading column around 45–65 Arabic characters per line on the portrait tablet. Adapt the exact CSS measure to the chosen Arabic font rather than forcing a generic rem width. Related short comparisons may extend beyond that column on wide screens while long prose retains its measure. Use a small, coherent spacing scale instead of unrelated margins on every element.
- Assign colors clear roles: page, text, secondary text, rules, and emphasis. A restrained palette can include a strong accent; give that accent something specific to do, such as identifying comparison headings or a source-supported sequence. Keep long prose on a calm surface and secondary text readable. Do not use pale labels, gradients, or heavy shadows to manufacture hierarchy.
- Choose one consistent language for rules, fills, and edges. Separate ordinary prose with space; reserve borders and tinted areas for real grouping. Avoid wrapping each section in a rounded panel. Let the hierarchy remain understandable in grayscale through wording, weight, alignment, and spacing.

An appropriately licensed embedded font is allowed; remote font requests are not. Wait for fonts before printing. Avoid letter spacing on connected Arabic text and full justification that creates distracting gaps. Use logical CSS properties such as `margin-inline`, `padding-inline`, and `border-inline-start` so alignment follows the Arabic reading direction. Keep English terms and notation deliberately isolated rather than letting them disturb adjacent punctuation.

## Author the single canonical HTML body

Write one self-contained UTF-8 HTML5 file in Arabic with `<html lang="ar" dir="rtl">`. It must contain exactly one `<main>` and exactly one `<article data-canonical-content="true">`. That article contains the authored Egyptian-Arabic explanation, and the PDF prints that same body. There is no mandatory duplicate source appendix.

Include standards-mode doctype, UTF-8 and responsive viewport metadata, a useful title, one leading `<h1>`, and a non-skipping heading hierarchy. Native comparison tables need captions and header cells. Inline SVG must not embed raster `<image>` nodes, rasterizing filters, decorative paths, or external assets.

The body must preserve the source's argument, mechanism, examples, evidence, qualifications, disagreements, and conclusion. Follow the source's real narrative shape. Use meaningful headings and natural reading transitions; do not force repeated cards or identical section compositions. A short source may produce a short companion. A complex source must remain deep enough to replace the original.

Mark editorial clarification, added examples, and translated quotations consistently with visible Arabic labels. Establish the main source attribution once and repeat it where ambiguity would arise; do not add a provenance badge to every paragraph. Keep hashes, internal source/job IDs, extraction diagnostics, and production receipts outside the reading article; retain them in the companion receipt and workspace. Use a short reader-facing source note and local uncertainty markers only where they affect understanding. Dense comparisons must reflow into readable stacked structures on narrow screens instead of relying on horizontal scrolling.

Place a short page, section, or timestamp reference beside important numbers, quotations, disputed claims, and figures, using locations present in the accepted extraction. Link only to a real source target; otherwise show the location as text. Figure captions retain units, relevant conditions, and source location. Recheck a doubtful passage directly while writing; no claim ledger or separate fact-checking workflow is required.

Use stable section IDs when they help navigation:

```html
<section id="mechanism"></section>
```

The design should make its purpose clear through the reading experience. Direct production does not require design-intent or design-signature metadata.

Use semantic HTML, source-specific CSS, native lists, blockquotes, tables, figures, and equations. This is a semantic HTML document in Arabic, not a styled wrapper around another payload. CSS custom properties are allowed inside this one file for clarity, but they are not a preset and must not be copied mechanically to another source. Choose every color and type role for this source; maintain readable Arabic type, a comfortable measure, strong contrast, and meaning that survives grayscale.

## Make relationships visible with native structures

Choose a visual when position, alignment, connection, or scale helps explain a specific relationship in this source. Decide what the reader needs to understand and whether seeing that relationship helps more than prose alone. Make that decision during authoring, without a rationale form, manifest, score, or visual quota. Preserve extended quotations, narrative, and close reading when prose teaches them best.

| Source relationship                   | Preferred form                                                 | What the form must explain                                        |
| ------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------------------- |
| Alternatives with shared criteria     | Native comparison table                                        | How the alternatives differ on the same questions                 |
| A mechanism or ordered procedure      | Connected HTML sequence; SVG only when spatial structure helps | The intermediate steps and the meaning of each connection         |
| Evidence and an argument              | Claim/evidence comparison                                      | Which observation supports the claim and where its support ends   |
| Change over time                      | Timeline or source-based chart                                 | The actual order; spacing represents duration only when justified |
| Comparable quantities                 | Native table, CSS bars, or accessible SVG                      | Magnitude with correct units, scale, and conditions               |
| Feedback, geometry, or overlap        | Small accessible SVG when native structures are insufficient   | The loop or spatial relationship a list would conceal             |
| A subtle distinction                  | Matched cases and nearby explanation                           | Which difference changes the conclusion                           |
| Narrative or ambiguous interpretation | Passage and commentary                                         | The source's sequence, perspective, and ambiguity                 |

These are choices, not page templates. Reuse a form when the same relationship recurs; do not force unrelated content into it or vary a useful form merely for novelty. Keep the supporting example and qualification beside the visual.

Style those structures to expose the relationship. Compare alternatives against the same criteria; align the stages of a process; connect a quoted passage to its explanation through proximity and type. Prefer descriptive labels to icon legends. A visually prominent claim still needs its conditions and attribution nearby. Do not invent quantities, dates, causal links, or visual proportions to make a composition more striking.

Give every arrow a defensible meaning. Sequence, correlation, a proposed mechanism, and causal evidence are different claims; label connections so they retain the distinctions in [arabic-teaching.md](arabic-teaching.md). Naming a cause and an outcome is insufficient when the source explains intermediate steps.

For numerical visuals, keep bounds and intervals as bounds and intervals: “less than 50” is not an exact observation of 50. Label different populations, denominators, units, or time periods explicitly, and avoid treating unlike quantities as directly comparable. Bar lengths need a meaningful common baseline; disclose a truncated scale where one is justified. Qualitative schematics must be labeled as such and must not imply measured curves, exact proportions, or invented results. Use a table when a chart would suggest unsupported precision.

A minimal inline SVG is allowed only when one spatial, causal, temporal, or quantitative relationship becomes materially clearer by being seen and cannot be expressed as clearly with prose or a native structure. It must be authored directly inside the HTML, source-grounded, genuinely RTL where direction matters, and contain `role="img"`, `<title>`, `<desc>`, Arabic labels, and a specific `data-visual-purpose`. Zero SVG is normal. There is no SVG quota.

For hard technical or mathematical material, use semantic equation markup when notation is essential and explain every symbol in Arabic at first use. Keep the mechanism legible to a beginner without deleting the source's precision.

Forbidden in ordinary companions (explicit media extensions follow the separate policy in [SKILL.md](../SKILL.md)):

- `<img>`, `<picture>`, raster assets, external SVG files, canvas, audio, video, iframe, or remote fonts/styles;
- mind maps, generated images, image atlases, visual galleries, decorative diagrams, generic icon rows, or visual chrome;
- scripts, forms, buttons, quizzes, mandatory pauses, answer revealers, widgets, scores, streaks, XP, progress, or a second learning system;
- hidden transcript padding, collapsed source text, duplicate prose, generic summary cards, or remote dependencies.

## Responsive reading

- Isolate English terms, identifiers, numbers, and equations with `bdi` or appropriate `dir="ltr"` blocks. Explain notation in adjacent Arabic prose; preserve units, signs, decimal points, and source uncertainty.
- On narrow screens, reduce outer gutters and display scale before reducing reading text. The 820 × 1180 portrait-tablet view keeps a 24px body and 17px supporting floor; phone widths may reduce body text only to 20–22px. Collapse supporting columns into the canonical reading order, with their labels and relationships intact. Let long titles, terms, references, and figure captions wrap. Use flexible tracks with `min-width: 0` where needed; avoid fixed heights and absolute positioning for reading content.
- Keep comparisons readable without horizontal scrolling. Stack labelled entries when needed while retaining their criteria and meaning. Essential explanation must remain visible at every width; mobile is a complete edition, not a shortened one.
- Ensure 200% text resizing does not lose content or create two-dimensional scrolling.
- Preserve keyboard focus for real links; avoid controls when the document has no action to perform.
- Give substantial sections stable IDs. Put a long contents list at the article end with a compact top link; a short inline list is optional when it helps. Short articles need neither. For long books with recurring concepts, add a small concept index or reading order using real section anchors and verified companion URLs; link to the existing explanation instead of duplicating it. Preserve chapter ownership and assigned-source boundaries. Keep this navigation usable in PDF, with no search app, disclosure controls, or progress system. Do not expose internal job metadata as navigation.
- Respect `prefers-reduced-motion`; the normal contract needs no motion.

## Compose the A4 edition

- Every page is A4.
- PDF comes from the final HTML hash.
- Give print its own type scale, margins, and spacing while retaining the same visual identity. Mahmood reads on an 11.5-inch Huawei TGR-W09 in portrait. Use 18pt A4 body text by default, about 1.7–1.8 line height, margins around 13–15mm, and at least 13pt for substantive tables, captions, and supporting labels. Aim for roughly 45–65 Arabic characters per line at fit-page/100%. These are readability floors, not targets to shrink toward. The larger type already creates substantially more physical leading; avoid very loose 2× spacing that detaches adjacent lines. Adjust upward for a dense or narrow Arabic face, and add pages rather than reducing the type to preserve a page count. Remove screen-only outer framing and reset wide-layout offsets. Keep paragraphs comfortable and supporting labels readable.
- Use white or very light print surfaces, economical rules, and restrained accent color. The hierarchy and meaning must survive grayscale and printing without background fills. Keep full explanatory text and source notes in the canonical reading order.
- Do not add a separate cover unless the source genuinely needs one; never allow a title-only first page.
- Avoid isolated headings, clipped native structures, and split captions. Let a complete visual study unit have breathing room; do not fill unused page space with extra prose.
- Keep each bounded study unit and its figure on one page where practical; divide an oversized unit at a meaningful conceptual boundary. Keep headings with following content and use sensible widows/orphans. Do not apply `break-inside:avoid` to entire long sections or every coverage scope. Repeat table headers when tables span pages, and keep a short caption with the item it describes.
- Preserve the same reading order and canonical text.
- Use the shared PDF renderer for tagged output and heading-derived bookmarks. Preserve descriptive metadata and working internal links. Semantic HTML alone does not prove the PDF's reading order; make claims only for checks actually performed.
- Links may remain visible as text; remote assets may not be fetched while printing.

Apply these decisions during authoring and fix concrete defects when encountered. Use the focused representative layout check in SKILL.md; no separate review ritual, design report, or exhaustive HTML/PDF audit is required. Integrity-only receipts continue to establish binding, not visual quality.
