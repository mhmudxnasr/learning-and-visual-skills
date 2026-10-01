# Efficient execution and tool choices

Default to the direct path: acquire the full source → write the canonical Arabic HTML → render once → seal identity and bytes → publish when authorized. Mahmood removed mandatory editorial passes, reviewed-scope/meaning-unit paperwork, the forced source appendix, and exhaustive HTML/PDF quality checks. Do not silently put them back in the background.

## Avoid repeated work

- Read common guidance once per active context. Keep the current source and necessary references in context; retrieve completed work from files.
- Reuse the hash-verified extraction. Extract a book once, then use its exact chapter bodies. Never redo OCR or transcription merely because HTML changed.
- Write the explanation directly in the canonical HTML. Do not create separate full prose, HTML, and PDF drafts that drift or require three rewrites.
- Run `finish` once per changed article. An unchanged signed receipt reuses the existing pair. Publication rechecks hashes without re-rendering it.
- Overlap at most two independent acquisition/render processes in different workspaces while writing the next source. Extraction is cached twice: `extract_source.py` by content-addressed key, and `prepare` skips it entirely when the workspace already holds a complete receipt-matching extraction of the same source. Do not parallelize mutable state or corpus activation.
- Read compact JSON and failed-stage output. Avoid repeated full-file dumps, polling loops, validation rituals, or a new service solely to rename the same commands.

## Batch the independent work

- During setup, acquire the exact supplied source while reading the required branch/capability information when those inputs are independent. Read a verified title alongside acquisition when needed for the article. Wait for source evidence before choosing a branch, and for the canonical dossier before binding publication identity. Never parallelize a mutation with its dependent verification.
- On the first `finish`, collect the opening and dense HTML/PDF views, narrow-screen view, and final PDF page together. One browser session can capture the HTML views at their respective widths; one PDF-open can render just those selected pages. Inspect the collected images together rather than launching a fresh round for each view. This is the existing focused check, not an exhaustive page or editorial audit.
- If the ending spills onto a nearly empty page, first adjust local footer/contents spacing and break rules. Preserve teaching prose and comfortable body text; a genuinely substantial ending may need its own page. Apply observed fixes as one batch, rerender the changed HTML once, and recheck affected views only. Do not promise zero rerenders or shorten source coverage for a timing target.
- Publish the unchanged signed pair only after those checks. Reuse the publisher's canonical ready-pair readback; obtain exact Queue membership once when Queue placement was requested. Never regenerate an already-ready pair merely to verify it.

## Stalls and remaining costs

Source reading and good explanation still require model time. A hundred long sources cannot honestly be made complete through short summaries. First network fetches, difficult OCR, and audio transcription can dominate; use the existing receipt-bound cache and only the necessary acquisition fallback. YouTube audio still requires positive proof that no manual/generated captions exist.

Runner subprocesses report stage start/completion, elapsed seconds, and a running update every 30 seconds. Default limits are 120 minutes for acquisition (which also has adapter-specific limits), 180 seconds for rendering, and 600 seconds for publication. The standalone renderer closes its browser after 150 seconds; navigation is bounded at 30 seconds. A workspace lock fails immediately instead of waiting silently. Direct Worker HTTP requests retain their 120-second bound.

`LITE_VISUAL_STEP_TIMEOUT_SECONDS` can set a positive command limit, at most 86400 seconds, for a diagnosed unusually large task. Do not increase it blindly or automatically retry a failure. After an ambiguous publication, verify the exact pair/job state first. Timeouts identify a failed stage; they are not permission to report completion or discard the source.

## Measured redundant cost

Before the direct-path change, the old browser audit waited one animation frame for every text node in each of five modes, and the PDF audit launched two tools per page. These repeats were removed from the optional historical validator too. It still visits every text node and page when explicitly requested.

On this host on 2026-09-05, three runs of the same synthetic 33-page article (120 source units; 362 reading text nodes per mode; fixture SHA-256 `87872a57c1087e3cdd6c97d33668ca3badf269ea1d63c548e65c9c711c4b9109`) gave these medians:

| Technical stage | Before | Optimized optional audit |
|---|---:|---:|
| Chromium PDF render | 0.789 s | 0.701 s |
| All-mode browser audit | 31.031 s | 1.104 s |
| All-page PDF audit | 0.989 s | 0.149 s |
| Combined measured time | 32.882 s | 1.963 s |

The direct default skips both audit rows entirely. These are synthetic technical measurements, not timings for reading, teaching, acquisition, publication, or 100 real sources. Reproduce the optional-audit measurement with `python3 scripts/benchmark_checks.py --repeats 3`; do not run benchmarks during ordinary authoring.

## Tools researched on 2026-09-05

Keep the existing direct Playwright/Chromium renderer for this workload. Scripts already call mature libraries; an MCP is an interface, not a faster PDF engine. Microsoft's [Playwright CLI guidance](https://github.com/microsoft/playwright-cli) recommends CLI/skills for token-efficient repeatable agent work, while MCP suits exploratory sessions needing persistent browser state. This workflow does not need accessibility-tree conversations to print a file.

[Gotenberg](https://gotenberg.dev/docs/configuration) maintains Chromium state and supports concurrent conversions. It is a reasonable future option for a continuously busy shared render queue. On this host the measured render is already under a second for the fixture; a Docker service, deployment, queue management, and another API are not justified by that evidence. No Gotenberg speedup has been measured here.

[Docling](https://docling-project.github.io/docling/reference/pipeline_options/) offers layout, OCR, and table processing for difficult input documents. Consider a targeted extraction adapter only after a real source demonstrates a failure in the existing PyMuPDF/Readability/Pandoc routes. It is not a replacement for Egyptian-Arabic explanation, and its benefit has not been benchmarked here.

Retain the installed PyMuPDF acquisition adapter and page-selective Tesseract fallback. [PyMuPDF's extraction documentation](https://pymupdf.readthedocs.io/en/latest/app1.html) distinguishes plain text, block, and detailed extraction; use the simplest adequate route and inspect actual source failures before adding heavier models.

Do not switch this Arabic workflow to WeasyPrint based on a generic PDF recommendation: its [current feature documentation](https://doc.courtbouillon.org/weasyprint/latest/api_reference.html) lists RTL/bidirectional text among unsupported CSS 2.1 features. Chromium also gives the HTML and PDF the same layout engine. No new dependency or MCP was installed for these changes.
