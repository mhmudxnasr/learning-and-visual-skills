#!/usr/bin/env python3
"""Measure local render/browser/PDF checks on a reproducible synthetic Arabic article.

No network, source acquisition, editorial review, receipts, or publication. Timings
describe only these technical stages; they are not a full-source authoring estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from validate_artifact import CanonicalHTML, check_browser, check_pdf


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--units", type=int, default=120)
    cli.add_argument("--repeats", type=int, default=3)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if not 1 <= args.units <= 1000 or not 1 <= args.repeats <= 10:
        cli.error("units must be 1–1000; repeats must be 1–10")
    source = "This synthetic passage explains how conditions connect a cause to its result. Follow each step, preserve the qualifications, and reconsider the conclusion when the conditions change. This is a technical fixture."
    authored = "عشان نفهم العلاقة، بنتابع كل خطوة ونشوف إزاي بتؤثر في اللي بعدها. ولو الظروف اتغيرت، لازم نراجع الاستنتاج ونحدد إذا كان التفسير لسه مناسب ولا محتاج معلومات إضافية."
    sections = "".join(f'<section id="explanation-{i}"><h2>تجربة القراءة {i + 1}</h2><p>{authored}</p></section>' for i in range(args.units))
    exact = "".join(f'<p dir="ltr" data-exact-source-scope="scope-{i}">{source}</p>' for i in range(args.units))
    markup = f'''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>تجربة تقنية</title><style>
@page{{size:A4;margin:18mm}}body{{font-family:Tahoma,sans-serif;font-size:18px;line-height:1.9;color:#111;background:white;margin:20px}}
h1,h2{{line-height:1.4}}h2{{font-size:20px;break-after:avoid}}p{{overflow-wrap:anywhere;orphans:3;widows:3}}@media print{{body{{margin:0}}}}
</style><body><article data-canonical-content="true"><h1>تجربة تقنية لقراءة عربية طويلة</h1>{sections}<section id="exact-source"><h2>النص الكامل للتجربة</h2>{exact}</section></article></body></html>'''
    parser = CanonicalHTML()
    parser.feed(markup)
    runs = []
    with tempfile.TemporaryDirectory(prefix="lite-visual-benchmark-") as folder:
        html, pdf = Path(folder) / "companion.html", Path(folder) / "companion.pdf"
        html.write_text(markup, encoding="utf-8")
        for iteration in range(args.repeats):
            start = time.perf_counter()
            subprocess.run(["node", str(Path(__file__).with_name("render_pdf.mjs")), str(html), str(pdf)], capture_output=True, text=True, check=True, timeout=180)
            rendered = time.perf_counter()
            browser = check_browser(html, args.units)
            checked = time.perf_counter()
            pdf_stats = check_pdf(pdf, " ".join(parser.text), " ".join([source] * args.units), parser.exact_scope_text)
            finished = time.perf_counter()
            run = {"render_seconds": round(rendered-start, 3), "browser_seconds": round(checked-rendered, 3), "pdf_seconds": round(finished-checked, 3), "total_seconds": round(finished-start, 3)}
            runs.append(run)
            print(json.dumps({"iteration": iteration + 1, **run}), flush=True)
    result = {"fixture_sha256": hashlib.sha256(markup.encode()).hexdigest(), "units": args.units, "pages": pdf_stats["pages"], "reading_text_nodes_per_mode": browser["print_reading_text_nodes"], "runs": runs, "median_seconds": {key: round(statistics.median(run[key] for run in runs), 3) for key in runs[0]}, "scope": "Synthetic local render + all-mode browser + all-page PDF checks; excludes acquisition, authoring, editorial review, and publication."}
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
