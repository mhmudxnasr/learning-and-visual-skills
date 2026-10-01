#!/usr/bin/env python3
"""Build a deterministic, gapless Lite Visual source-scope authoring skeleton."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

WORD_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?؟])\s+")
CLAUSE_BREAK_RE = re.compile(r"(?<=[،؛:])\s+")


def words(value: str) -> list[str]:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", value)
    value = value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})).lower()
    return WORD_RE.findall(value)


def semantic_units(text: str, maximum: int) -> list[tuple[list[str], str]]:
    """Return the smallest natural units needed to respect ``maximum``."""
    units: list[tuple[list[str], str]] = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if words(part)]
    for paragraph in paragraphs:
        sentences = [part.strip() for part in SENTENCE_BREAK_RE.split(paragraph) if words(part)]
        for index, sentence in enumerate(sentences):
            sentence_words = words(sentence)
            boundary = "paragraph" if index == len(sentences) - 1 else "sentence"
            if len(sentence_words) <= maximum:
                units.append((sentence_words, boundary))
                continue
            clauses = [part.strip() for part in CLAUSE_BREAK_RE.split(sentence) if words(part)]
            if len(clauses) > 1 and all(len(words(clause)) <= maximum for clause in clauses):
                for clause_index, clause in enumerate(clauses):
                    clause_boundary = boundary if clause_index == len(clauses) - 1 else "clause"
                    units.append((words(clause), clause_boundary))
                continue
            for start in range(0, len(sentence_words), maximum):
                end = min(start + maximum, len(sentence_words))
                hard_boundary = boundary if end == len(sentence_words) else "hard word limit inside an overlong sentence"
                units.append((sentence_words[start:end], hard_boundary))
    return units


def draft_scopes(text: str, target: int) -> list[tuple[int, int, list[str], str]]:
    """Pack complete sentences or clauses into gapless hard-bounded drafts."""
    packed: list[tuple[int, int, list[str], str]] = []
    start = 0
    current: list[str] = []
    current_boundary = "source end"
    for unit_words, boundary in semantic_units(text, target):
        if current and len(current) + len(unit_words) > target:
            packed.append((start, start + len(current), current, current_boundary))
            start += len(current)
            current = []
        current.extend(unit_words)
        current_boundary = boundary
    if current:
        packed.append((start, start + len(current), current, "source end"))
    return packed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--target-words", type=int, default=120, help="hard maximum words per draft scope")
    args = parser.parse_args()
    if args.target_words < 20 or args.target_words > 120:
        parser.error("--target-words must be between 20 and 120")
    source_bytes = args.source.read_bytes()
    source_text = source_bytes.decode("utf-8")
    source_words = words(source_text)
    if not source_words:
        parser.error("source has no readable words")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else {}
    source_obj = manifest.get("source") if isinstance(manifest, dict) else {}
    if isinstance(source_obj, dict):
        source_url = source_obj.get("url") or source_obj.get("source_url")
        source_title = source_obj.get("title") or source_obj.get("source_title")
        source_kind = source_obj.get("kind") or source_obj.get("source_kind")
    else:
        source_url = source_obj if isinstance(source_obj, str) else manifest.get("source_url")
        source_title = manifest.get("title") or manifest.get("source_title")
        source_kind = manifest.get("kind") or manifest.get("source_kind")

    spans = []
    for index, (start, end, chunk_words, draft_boundary) in enumerate(draft_scopes(source_text, args.target_words), start=1):
        spans.append({
            "id": f"scope-{index:02d}",
            "word_start": start,
            "word_end": end,
            "anchor": " ".join(chunk_words[:12]),
            "semantic_label": "AUTHOR_REQUIRED: name the single coherent source movement in this scope.",
            "boundary_reason": f"AUTHOR_REQUIRED: verify or move this draft {draft_boundary} boundary to the source's real semantic turn.",
            "summary": "AUTHOR_REQUIRED: summarize every hadith, ruling, example, qualification, attribution, correction, definition, and conclusion in this span.",
        })
    payload = {
        "schema_version": "lite-visual-source-scope/v3",
        "source": {
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "word_count": len(source_words),
            "url": source_url,
            "title": source_title,
            "kind": source_kind or "article",
        },
        "spans": spans,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "word_count": len(source_words), "span_count": len(spans), "target_words": args.target_words, "target_is_hard_limit": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
