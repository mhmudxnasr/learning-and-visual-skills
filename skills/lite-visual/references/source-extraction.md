# Visual Lite source extraction router

Use one entry point for every source:

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/extract_source.py \
  '<URL-or-local-file>' \
  --output /abs/work/source.txt \
  --manifest /abs/work/source-extraction.json
```

The command returns one JSON receipt and writes exactly one immutable UTF-8 `source.txt`. Continue only when `status` is `complete`, the receipt hash matches the file, and every source-kind check passes. Retain `method`, `content_sha256`, `cache_key`, `word_count`, and the manifest path for the runner's existing checkpoints. The `map_coverage` stage name remains for `lite-visual-linear/v4` compatibility; direct authoring does not require a manual coverage map or gapless ledger.

## Fast lanes

“Milliseconds” is an honest target only after the source is cached or already local. A first remote fetch is bounded by the source and network.

| Source | First method | Normal first-run target | Fallback | Stop condition |
|---|---|---:|---|---|
| Fresh cache | hash-verified cached `source.txt` | under 100 ms | re-extract on expiry/hash mismatch | cached hash or receipt mismatch |
| Pasted/local UTF-8 text | direct bytes | under 100 ms | none | invalid UTF-8 or fewer than 10 words |
| Hash-verified local transcript | local UTF-8 plus its accepted transcript receipt | under 100 ms | reacquire the timed source | transcript/audio hash mismatch, failed quality/chunk gate, non-monotonic segments, repeated 40-word passage, or canonical media mismatch |
| Static article | bounded public HTTP fetch → Mozilla Readability in a script-disabled JSDOM | network + roughly 0.1–1 s parsing | Playwright with images/media/fonts blocked, then Readability | short body, paywall/truncation marker, fewer than three meaningful blocks, excessive duplicate boilerplate |
| JavaScript article | bounded Playwright render → Readability | about 3–15 s | none | completeness gate remains red |
| YouTube | `youtube-transcript-api`: requested human captions first, then generated captions | about 0.2–3 s when captions are available | `yt-dlp` subtitle JSON/VTT; then `faster-whisper` only after a complete caption inventory confirms no manual or generated tracks | caption lookup failed without proving absence, a published track is unreadable/incomplete, fewer than 20 words, raw VTT leaked, excessive repeated cues, or audio fallback failed |
| Podcast/audio/video | published captions when the host exposes them | seconds | `yt-dlp` audio → `faster-whisper`; local media goes directly to Whisper | download/transcription failure or shallow transcript |
| Text-layer PDF | PyMuPDF, every page in order with `[PAGE n]` anchors | usually under 1 s for ordinary documents | Tesseract `ara+eng` only on near-empty pages | encryption, no pages, too many pages remain empty |
| Scanned PDF | PyMuPDF page render → Tesseract `ara+eng` | roughly 1–10 s per OCR page | none | page coverage remains incomplete |
| EPUB | container → OPF package → exact spine order → XHTML text | normally under a few seconds | none | broken/missing spine resources or shallow body |
| DOCX/ODT/RTF | Pandoc plain-text conversion | normally under a few seconds | none | conversion failure or shallow body |

These are routing budgets, not success claims. Record the observed `elapsed_ms`; never invent a duration.

## YouTube fidelity order

The adapter checks requested languages `ar,ar-SA,ar-EG,en`, but fidelity outranks translation convenience:

1. Human-created captions in a requested language.
2. Generated captions in a requested language.
3. Another original published caption track.
4. `yt-dlp` subtitle representations, preferring JSON3 and cleaning VTT when necessary.
5. Download audio and transcribe with local `faster-whisper` (`small`, int8, VAD) only after a complete caption inventory positively confirms zero manual and zero generated tracks and no adapter reports a track.

Always retain timestamps for timed media. The manifest identifies `method`, `caption_kind`, selected language, transcript hash, word count, elapsed time, and all failed faster methods. A successful slow fallback must not hide why the fast lane failed.

A caption lookup error is not proof that captions are absent. If a track exists but fails download, parsing, language, or completeness checks, block extraction and preserve that evidence instead of invoking audio. Every YouTube audio-derived manifest must include `audio_fallback_reason=youtube_captions_confirmed_absent` and the exact `caption_absence_evidence`.

Direct adapter command when diagnosis is required:

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/fetch_transcript.py \
  --url 'https://www.youtube.com/watch?v=...' \
  --languages ar,ar-SA,ar-EG,en \
  --timestamps \
  --output /abs/work/source.txt \
  --manifest /abs/work/transcript.json
```

For the accepted Riyadh timed-media corpus with a `riyadh-salihin-local-transcript/v1` receipt, keep the official media URL as source identity and route it through the same extractor:

```bash
python3 /home/mahmud/.hermes/skills/lite-visual/scripts/extract_source.py \
  /abs/corpus/transcripts/019.txt \
  --kind audio \
  --verified-transcript-receipt /abs/corpus/receipts/019.json \
  --canonical-source 'https://source.example/019.mp3' \
  --strip-embedded-timestamps \
  --output /abs/work/source.txt \
  --manifest /abs/work/source-extraction.json
```

This lane first verifies the unmodified transcript against its receipt. It then validates the audio hash, receipt and chunk quality, monotonic segments, canonical media URL, and every repeated 40-word passage family, including immediate repetitions. Any bracketed timestamp labels are removed only after the parent hash passes, and the transformation count remains in the extraction receipt. A genuine quotation repeated later during explanation still blocks by default; accept one detected family only with `--verified-repetition-review` and a review bound to the transcript/audio hashes, exact word offsets, exact-run length, and both timestamped segment anchors. Additional families remain blocked. Do not synthesize or edit an extraction receipt outside this adapter.

## Article completeness

Never use a search snippet, social preview, model summary, RSS excerpt, browser selection, or introduction-only paywall page as the source. Direct HTTP uses manual public-only redirects, DNS/IP checks, a 10-second request budget, and a 25 MB body limit. Scripts never execute in the static parser. The JavaScript browser is a bounded fallback with a fresh session and no images, media, or fonts; it does not use a personal signed-in browser.

Readability must return a substantive body with several meaningful blocks, no visible truncation/paywall marker, and low duplicate boilerplate. JSON-LD `articleBody` may replace Readability only when it is materially more complete. The manifest retains title, byline, language, canonical URL, engine, completeness checks, response validators, and warnings.

If a member/paywall page exposes only an introduction, stop. A linked public transcript, canonical PDF, author-provided mirror, or exact user upload is a new source resolution step; record that identity rather than silently combining unrelated secondary summaries.

For Islamweb audio transcripts, prefer the publisher's observed `Fulltxt.php?audioid=...` print link when `FullContent` extraction omits sections. Readability can label one selected section complete even with `full=1`; compare the extracted headings and opening/ending against the publisher's full transcript before accepting it. Acquire the print URL through the same extractor in a fresh workspace, retaining the original source record as publication identity; never patch a completeness receipt or author from the partial section.

## Cache and recovery

The cache key binds source identity, source kind, extractor version, language order, timestamp policy, and local file size/mtime when applicable. Remote article cache entries expire after one day; timed-media entries after 30 days. A workflow retry uses the already checkpointed content hash even if the normal freshness window later expires. `--force` deliberately re-extracts.

Direct local ASR retains the provider's original segment starts, ends, and repeated speech. Its adapter measures duration with ffprobe, hashes the exact audio and transcript, and blocks non-monotonic/overlapping times, uncovered endings, long gaps, implausible text, or language failure. `WHISPER_LANGUAGE`, `WHISPER_CPU_THREADS`, and `WHISPER_MODEL` are explicit runtime controls; `WHISPER_EVIDENCE_PATH` optionally retains append-only raw segment evidence when a long run fails. That diagnostic file is not an accepted transcript or resumable receipt. The router's timed-media cache key includes the adapter script hash so an earlier shallow receipt cannot survive a repair.

The cache accelerates acquisition; it never weakens source coverage. A cache hit is accepted only when its stored SHA-256 matches the bytes. Keep `source.txt` and its manifest together through validation and publication. On any blocked receipt, preserve the error and stop before authoring or advancing the runner's `map_coverage` checkpoint; do not ask the authoring model to fill missing source material.

## AI handoff

Give the authoring model only:

- exact source identity and kind;
- immutable `source.txt` path and SHA-256;
- extraction manifest path, method, language, and warnings;
- exact page/timestamp/spine anchors already present in the text;
- the current direct-authoring guidance in `SKILL.md` and its teaching/design references, plus the reader's stated question when available.

Do not give it cookies, raw page scripts, network credentials, cache internals, failed partial bodies, or several competing extractions of the same source. Use one verified body per accepted source. Explicit synthesis keeps each source's body and receipt separately, following [batch-authoring.md](batch-authoring.md); never manufacture a combined extraction receipt.
