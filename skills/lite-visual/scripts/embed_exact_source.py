#!/usr/bin/env python3
"""Embed one visible, complete source edition into a Lite Visual HTML article."""

from __future__ import annotations

import argparse
import html
import json
import re
import tempfile
import unicodedata
from pathlib import Path


WORD_RE = re.compile(r"[\w؀-ۿ]+", re.UNICODE)
EXACT_SECTION_RE = re.compile(
    r"\s*<section\b[^>]*\bid=[\"']exact-source[\"'][^>]*>.*</section>\s*(?=</article>)",
    re.I | re.S,
)
EXACT_STYLE_RE = re.compile(
    r"\s*<style\b[^>]*\bid=[\"']exact-source-style[\"'][^>]*>.*?</style>\s*",
    re.I | re.S,
)
QUOTE_RE = re.compile(r"[\"“”]([^\"“”]+)[\"“”]")
NUMBER_RUN_RE = re.compile(r"(?<![\w])([0-9]+(?:[.,٫٬][0-9]+)*(?:[ \t/−-][0-9]+(?:[.,٫٬][0-9]+)*)*(?:[%٪،,])?)")


def arabic_quotation_marks(value: str) -> str:
    return QUOTE_RE.sub(lambda match: f"«{match.group(1)}»", value)


def exact_html(value: str) -> str:
    escaped = html.escape(value, quote=False)
    return NUMBER_RUN_RE.sub(lambda match: f'<bdi dir="ltr">{match.group(1)}</bdi>', escaped)


def source_tokens(value: str) -> list[str]:
    value = unicodedata.normalize("NFKC", value)
    # Scope offsets are counted after removing Arabic vocalization and Quranic
    # annotation marks.  Keep the source's base-letter spelling visible, but
    # remove those non-word annotations before slicing so every HTML scope uses
    # the exact same token boundaries as the v6 validator.
    value = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", value)
    return WORD_RE.findall(value)


def source_word_offsets(value: str) -> list[tuple[int, int]]:
    """Map the validator's normalized word boundaries back to untouched text.

    A presentation ligature can expand to several normalized words. Reject a
    scope boundary inside that one character instead of duplicating/dropping it.
    """
    normalized: list[str] = []
    positions: list[int] = []
    translations = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})
    for position, character in enumerate(value):
        transformed = unicodedata.normalize("NFKC", character)
        transformed = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", transformed)
        transformed = transformed.translate(translations).lower()
        normalized.extend(transformed)
        positions.extend([position] * len(transformed))
    return [(positions[match.start()], positions[match.end()-1]+1) for match in WORD_RE.finditer("".join(normalized))]


def strip_existing(document: str) -> str:
    return EXACT_STYLE_RE.sub("\n", EXACT_SECTION_RE.sub("\n", document))


def exact_source_markup(source_text: str, scope: dict) -> str:
    offsets = source_word_offsets(source_text)
    sections: list[str] = []
    cursor = 0
    for index, span in enumerate(scope.get("spans") or [], start=1):
        scope_id = str(span.get("id") or "")
        start = int(span.get("word_start", -1))
        end = int(span.get("word_end", -1))
        if not re.fullmatch(r"scope-[a-zA-Z0-9._-]+", scope_id) or start != cursor or end <= start or end > len(offsets):
            raise ValueError(f"invalid source scope at position {index}")
        if end < len(offsets) and offsets[end-1][1] > offsets[end][0]:
            raise ValueError(f"scope {scope_id} splits a source ligature; move the semantic boundary")
        char_start = offsets[start][0] if start else 0
        char_end = offsets[end][0] if end < len(offsets) else len(source_text)
        text = source_text[char_start:char_end]
        sections.append(
            f'<span data-exact-source-scope="{html.escape(scope_id, quote=True)}">{exact_html(text)}</span>'
        )
        cursor = end
    if not sections:
        raise ValueError("source scope contains no spans")
    if cursor != len(offsets):
        raise ValueError("source scopes do not reach the final source word")
    return (
        '<section id="exact-source" aria-labelledby="exact-source-title">'
        '<h2 id="exact-source-title">النص الكامل للمصدر</h2>'
        '<p class="exact-source-intro">نسخة كاملة مرتبة للمراجعة والتحقق من ألفاظ المصدر.</p>'
        + '<div class="exact-source-text" dir="auto">' + "".join(sections) + '</div>'
        + '</section>'
    )


def embed(source_path: Path, scope_path: Path, html_path: Path) -> None:
    source_text = source_path.read_text(encoding="utf-8")
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    document = strip_existing(html_path.read_text(encoding="utf-8"))
    closing = document.lower().rfind("</article>")
    if closing < 0:
        raise ValueError("HTML requires a closing canonical article")
    style = (
        '<style id="exact-source-style">'
        '#exact-source{margin-block-start:3rem;padding-block-start:2rem;border-block-start:1px solid currentColor}'
        '#exact-source h2{margin:0 0 .75rem}.exact-source-intro{max-width:68ch}'
        '.exact-source-text{max-width:72ch;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9}'
        '@media print{#exact-source{break-before:page}.exact-source-text{orphans:3;widows:3}}'
        '</style>'
    )
    updated = document[:closing].rstrip() + "\n" + exact_source_markup(source_text, scope) + "\n" + document[closing:]
    head_close = updated.lower().find("</head>")
    if head_close < 0:
        raise ValueError("HTML requires a closing head")
    updated = updated[:head_close].rstrip() + "\n" + style + "\n" + updated[head_close:]
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=html_path.parent, prefix=f".{html_path.name}.", suffix=".tmp", delete=False) as handle:
            handle.write(updated)
            temporary = Path(handle.name)
        temporary.replace(html_path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-scope", required=True, type=Path)
    parser.add_argument("--html", required=True, type=Path)
    args = parser.parse_args()
    embed(args.source, args.source_scope, args.html)
    print(json.dumps({"ok": True, "html": str(args.html), "exact_source_embedded": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
