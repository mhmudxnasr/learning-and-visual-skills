---
name: lite-visual
description: Turn a dense article or report into a single-file interactive HTML study artifact. Minimal version of visual-learn — core comprehension and design principles only, no scaffold, no changelog. Only triggers when "visual" and "lite" are said together.
---

# Visual Learn Lite

Single, offline, double-clickable HTML file. Not a summary — a comprehension engine.

## Comprehension (do this first, before any design)

- **Reorder by prerequisite, not source order.** List every concept, then sequence by what the reader needs to already know. Don't inherit the source's paragraph order.
- **One idea per section.** If a section needs "and also," split it.
- **Explain before you name.** Plain-language problem first, jargon term second — never the reverse.
- **Interactive elements must teach, not decorate.** A slider only earns its place if moving it reveals something the prose didn't already say.
- **Reread as a beginner.** After drafting a section, check every sentence for an assumed fact or term you haven't established yet.
- **Comprehensive ≠ reformatted.** Keep every fact from the source, but restructure how ideas relate — don't just repaint dense prose into nicer boxes.

## The bar

- **Comprehensive coverage.** All mechanisms, examples, and stats from the source — via progressive disclosure, not compression.
- **Interactive at every section.** Tinkerable visuals, not static screenshots or decorative card grids.
- **B2 English + glossary.** Short sentences, one idea each. Jargon → clickable glossary term, defined plainly. Test: blank out the jargon term mentally — does the sentence still parse?
- **Zero AI tells.** No cream/sand background, no cliché font pairs (avoid Inter, Newsreader, Fraunces, Lora, Playfair as defaults), no side-stripe borders, no ghost-cards (thin border + big shadow), no identical card grids, no kicker-above-every-heading.
- **Offline, single file.** No CDN dependencies. System-font fallbacks.

## Build order

1. Name three voice words for the artifact (e.g. "scholarly, candid, vivid"). Let them pick the font and color feel — don't start from tokens.
2. Draft content following the comprehension rules above.
3. Add one interactive element per section that demonstrates a real cause-and-effect.
4. Add active recall (a question + reveal) every 2-3 sections.
5. Add a glossary drawer, theme toggle, and scroll progress if useful — keep JS dependency-free.

## Delivery

When the user asks to send the artifact to Telegram, use:

```bash
hermes send --to telegram:<chat_id> "MEDIA:/absolute/path/to/artifact.html"
```

This sends the HTML file as a downloadable document attachment — not inline text, not a path reference. `MEDIA:<path>` is the attachment syntax; `--file` reads text into the message body (wrong for this).

## Ship checklist

- [ ] Sections in prerequisite order, not source order
- [ ] Every section: one idea, explained before named
- [ ] Every interactive element demonstrates something, isn't decoration
- [ ] Reread pass done for assumed knowledge
- [ ] No AI-tell defaults (fonts, cream bg, side-stripes, ghost-cards)
- [ ] Contrast ≥ 4.5:1 body text
- [ ] Opens offline via double-click, no console errors

Output the file directly. No explanation of the scaffold — the file is the response.

## Delivery (Telegram gateway)

User is always the same Telegram target — `telegram:5556183632`. Skip the `--list` lookup.

```bash
hermes send --to telegram:5556183632 "MEDIA:/absolute/path/to/artifact.html"
```

**`MEDIA:` prefix is what turns a path-as-text into an actual file attachment. Without it, the user gets the literal string `/home/.../file.html` as a useless text message. This is the #1 mistake. Always include `MEDIA:`.**

Rules:
- **Always use the `MEDIA:/abs/path` form in the message body.** Never just paste a path alone. Never use `--file` for binaries (it reads as text). The `MEDIA:` prefix is the only thing that makes Telegram receive the file as an attachment.
- Always absolute paths. Relative paths silently fail.
- HTML artifacts travel as `.html` attachments; Telegram won't render inline, the user opens them in a browser on their phone.
- Don't ask "want me to send it?" — if the source is the Telegram gateway and a file was produced, just send.
- One short confirmation line in chat ("sent. [filename] delivered.") — no path re-print, no content summary.

For full delivery workflow + pitfalls, see the `telegram-gateway-delivery` skill.
