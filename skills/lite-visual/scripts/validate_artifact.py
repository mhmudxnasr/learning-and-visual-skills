#!/usr/bin/env python3
"""Deterministically validate one code-only Lite Visual HTML/A4-PDF pair.

The HTML article is the single canonical reading body. The PDF must be printed
from that exact file. This gate does not inspect screenshots and accepts no
subjective QA score: source coverage, markup, geometry, accessibility, print,
and text parity either pass or publication stops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from receipt_attestation import RECEIPT_SCHEMA, WORKFLOW_CONTRACT, attest_receipt, target_sha256
from process_runtime import ProcessFailure, execute

SCOPE_SCHEMAS = {"lite-visual-source-scope/v2", "lite-visual-source-scope/v3"}
LEDGER_SCHEMA = "lite-visual-coverage-ledger/v1"
EDITORIAL_SCHEMA = "lite-visual-editorial-review/v1"
MEANING_KINDS = {"claim", "definition", "mechanism", "example", "evidence", "qualification", "attribution", "conclusion", "step", "quotation", "context", "question", "narrative"}
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
WORD_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)


class ValidationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def normalize_arabic(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", value)
    return value.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})).lower()


def words(value: str) -> list[str]:
    return WORD_RE.findall(normalize_arabic(value))


def compact_characters(value: str) -> str:
    return "".join(character for character in normalize_arabic(value) if character.isalnum())


def ngrams(value: str, size: int = 3) -> list[str]:
    return [value[index:index + size] for index in range(max(0, len(value) - size + 1))]


def ordered_pdf_scope(compact_pdf: str, expected: str, cursor: int) -> int | None:
    anchor_size = min(32, max(20, len(expected) // 12))
    scope_cursor = cursor
    search_at = cursor
    while True:
        start = compact_pdf.find(expected[:anchor_size], search_at)
        if start < 0:
            break
        candidate = compact_pdf[start:start + len(expected)]
        inventory_match = len(candidate) == len(expected) and Counter(candidate) == Counter(expected)
        expected_index = 0
        pdf_index = start
        skipped = 0
        maximum_skipped = max(4, len(expected) // 400)
        while expected_index < len(expected) and pdf_index < len(compact_pdf):
            if expected[expected_index] == compact_pdf[pdf_index]:
                expected_index += 1
            else:
                skipped += 1
                if skipped > maximum_skipped:
                    break
            pdf_index += 1
        if expected_index == len(expected) and compact_pdf.rfind(expected[-anchor_size:], start, pdf_index) >= 0:
            return pdf_index
        # Poppler can locally transpose complete RTL word runs at a visual line
        # boundary, including the last word of a scope. Accept that extractor-
        # only case when an ordered opening anchor identifies one exact-length
        # contiguous region with an identical character inventory. The canonical
        # HTML order and every exact source word are checked before PDF parity.
        if inventory_match:
            return start + len(expected)
        search_at = start + 1
    # A visual RTL line can also transpose the opening word run, so the
    # expected prefix may begin inside the extracted scope. Limit this final
    # fallback to the immediate post-scope boundary (normally only the compact
    # "المقطع N" label intervenes) and require an exact-length, identical
    # character inventory. This cannot accept missing or additional text.
    final_start = min(len(compact_pdf) - len(expected), scope_cursor + 512)
    expected_inventory = Counter(expected)
    for start in range(scope_cursor, max(scope_cursor, final_start) + 1):
        candidate = compact_pdf[start:start + len(expected)]
        if len(candidate) == len(expected) and Counter(candidate) == expected_inventory:
            return start + len(expected)
    return None


def run(command: list[str], label: str, cwd: Path | None = None) -> str:
    try:
        return execute(command, label, cwd=cwd)
    except ProcessFailure as exc:
        raise ValidationError(str(exc)) from exc


class CanonicalHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_attrs: dict[str, str] = {}
        self.main_count = 0
        self.canonical_count = 0
        self.canonical_depth = 0
        self.skip_depth = 0
        self.text: list[str] = []
        self.authored_text: list[str] = []
        self.authored_id_text: dict[str, list[str]] = {}
        self.seen_ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.scope_ids: list[str] = []
        self.element_ids: list[str | None] = []
        self.id_text: dict[str, list[str]] = {}
        self.headings: list[tuple[int, str]] = []
        self.current_heading: tuple[int, list[str]] | None = None
        self.svg_stack: list[dict[str, Any]] = []
        self.svgs: list[dict[str, Any]] = []
        self.tables = 0
        self.table_captions = 0
        self.table_headers = 0
        self.exact_scope_text: dict[str, list[str]] = {}
        self.exact_scope_order: list[str] = []
        self.exact_scope_duplicates: set[str] = set()
        self.exact_scope_stack: list[tuple[str, int]] = []

    @staticmethod
    def attrs(value: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.lower(): item or "" for key, item in value}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = self.attrs(attrs)
        element_id = values.get("id")
        if element_id:
            if element_id in self.seen_ids:
                self.duplicate_ids.add(element_id)
            self.seen_ids.add(element_id)
        if tag == "html":
            self.html_attrs = values
        if tag == "main":
            self.main_count += 1
        if tag == "article" and values.get("data-canonical-content") == "true":
            self.canonical_count += 1
            self.canonical_depth += 1
            self.element_ids.append(values.get("id") or None)
        elif self.canonical_depth and tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.canonical_depth += 1
            self.element_ids.append(values.get("id") or None)
        if tag in {"style", "script", "template", "noscript"}:
            self.skip_depth += 1
        if self.canonical_depth and not self.skip_depth:
            for scope_id in values.get("data-source-scope", "").split():
                if scope_id:
                    self.scope_ids.append(scope_id)
            if re.fullmatch(r"h[1-6]", tag):
                self.current_heading = (int(tag[1]), [])
            if tag == "svg":
                svg = {"attrs": values, "has_title": False, "has_desc": False, "text": []}
                self.svg_stack.append(svg)
                self.svgs.append(svg)
            elif self.svg_stack and tag == "title":
                self.svg_stack[-1]["has_title"] = True
            elif self.svg_stack and tag == "desc":
                self.svg_stack[-1]["has_desc"] = True
            if tag == "table":
                self.tables += 1
            elif tag == "caption":
                self.table_captions += 1
            elif tag == "th":
                self.table_headers += 1
            exact_scope = values.get("data-exact-source-scope", "")
            if exact_scope:
                if not re.fullmatch(r"scope-[a-zA-Z0-9._-]+", exact_scope):
                    self.exact_scope_duplicates.add(exact_scope)
                elif exact_scope in self.exact_scope_text:
                    self.exact_scope_duplicates.add(exact_scope)
                else:
                    self.exact_scope_text[exact_scope] = []
                    self.exact_scope_order.append(exact_scope)
                self.exact_scope_stack.append((exact_scope, self.canonical_depth))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.current_heading and tag == f"h{self.current_heading[0]}":
            self.headings.append((self.current_heading[0], " ".join(self.current_heading[1]).strip()))
            self.current_heading = None
        if tag == "svg" and self.svg_stack:
            self.svg_stack.pop()
        if tag in {"style", "script", "template", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if self.canonical_depth:
            self.exact_scope_stack = [item for item in self.exact_scope_stack if item[1] != self.canonical_depth]
            if self.element_ids:
                self.element_ids.pop()
            self.canonical_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.canonical_depth or self.skip_depth:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if not value:
            return
        self.text.append(value)
        is_authored = "exact-source" not in self.element_ids and not self.exact_scope_stack
        if is_authored:
            self.authored_text.append(value)
        for element_id in self.element_ids:
            if element_id:
                self.id_text.setdefault(element_id, []).append(value)
                if is_authored:
                    self.authored_id_text.setdefault(element_id, []).append(value)
        if self.current_heading:
            self.current_heading[1].append(value)
        if self.svg_stack:
            self.svg_stack[-1]["text"].append(value)
        for scope_id, _ in self.exact_scope_stack:
            if scope_id in self.exact_scope_text:
                self.exact_scope_text[scope_id].append(value)


def check_source_scope(source_path: Path, scope_path: Path) -> tuple[list[str], int]:
    source_bytes = source_path.read_bytes()
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"source text must be UTF-8: {exc}") from exc
    source_words = words(source_text)
    if not source_words:
        raise ValidationError("source text has no readable words")
    scope = load_json(scope_path, "source scope")
    scope_schema = str(scope.get("schema_version") or "")
    if scope_schema not in SCOPE_SCHEMAS:
        raise ValidationError("source scope schema_version must be lite-visual-source-scope/v2 or lite-visual-source-scope/v3")
    source = scope.get("source")
    if not isinstance(source, dict):
        raise ValidationError("source scope source must be an object")
    expected_hash = hashlib.sha256(source_bytes).hexdigest()
    if source.get("sha256") != expected_hash:
        raise ValidationError("source scope hash does not match the extracted source")
    if source.get("word_count") != len(source_words):
        raise ValidationError("source scope word_count does not match the extracted source")
    spans = scope.get("spans")
    if not isinstance(spans, list) or not spans:
        raise ValidationError("source scope must contain one or more spans")
    ids: list[str] = []
    cursor = 0
    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            raise ValidationError(f"source scope span {index + 1} must be an object")
        scope_id = str(span.get("id") or "")
        start = span.get("word_start")
        end = span.get("word_end")
        if not re.fullmatch(r"scope-[a-zA-Z0-9._-]+", scope_id) or scope_id in ids:
            raise ValidationError(f"source scope span {index + 1} needs a unique scope-* id")
        if not isinstance(start, int) or not isinstance(end, int) or start != cursor or end <= start or end > len(source_words):
            raise ValidationError("source scope spans must partition the complete source contiguously without gaps or overlap")
        if end - start > 120:
            raise ValidationError(f"source scope span {scope_id} exceeds the 120-word semantic inventory limit")
        summary = str(span.get("summary") or "").strip()
        if not str(span.get("anchor") or "").strip() or not summary or summary.startswith("AUTHOR_REQUIRED"):
            raise ValidationError(f"source scope span {scope_id} requires an anchor and source-grounded summary")
        if scope_schema == "lite-visual-source-scope/v3":
            semantic_label = str(span.get("semantic_label") or "").strip()
            boundary_reason = str(span.get("boundary_reason") or "").strip()
            if not semantic_label or semantic_label.startswith("AUTHOR_REQUIRED"):
                raise ValidationError(f"source scope span {scope_id} requires an authored semantic_label")
            if not boundary_reason or boundary_reason.startswith("AUTHOR_REQUIRED"):
                raise ValidationError(f"source scope span {scope_id} requires an authored boundary_reason")
        ids.append(scope_id)
        cursor = end
    if cursor != len(source_words):
        raise ValidationError("source scope spans do not reach the final source word")
    return ids, len(source_words)


def check_html(html_path: Path, scope_ids: list[str]) -> tuple[str, dict[str, Any], CanonicalHTML]:
    try:
        html = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"HTML must be UTF-8: {exc}") from exc
    lower = html.lower()
    if not re.search(r"<!doctype\s+html", lower):
        raise ValidationError("HTML requires a standards-mode doctype")
    forbidden_tags = re.findall(r"<\s*(img|picture|source|canvas|video|audio|iframe|object|embed|script|form|button|input|textarea|select)\b", lower)
    if forbidden_tags:
        raise ValidationError("code-only companion contains forbidden media or interaction tags: " + ", ".join(sorted(set(forbidden_tags))))
    if re.search(r"<(?:link|style)\b[^>]*(?:https?:)?//", lower) or re.search(r"url\(\s*['\"]?https?://", lower):
        raise ValidationError("HTML must not load remote styles, fonts, or assets")
    if re.search(r"\b(?:data-template|data-theme|style-lock|visual-preset|palette-preset)\b", lower):
        raise ValidationError("HTML must not carry a template, theme, style-lock, or palette preset")
    if not re.search(r"<meta\b[^>]*name=[\"']viewport[\"'][^>]*content=[\"'][^\"']*width=device-width", lower):
        raise ValidationError("HTML requires a responsive viewport declaration")
    for name in ("lite-visual-design-intent", "lite-visual-design-signature"):
        match = re.search(rf"<meta\b[^>]*name=[\"']{name}[\"'][^>]*content=[\"']([^\"']+)", html, re.I)
        if not match or len(match.group(1).strip()) < 12:
            raise ValidationError(f"HTML requires a source-specific {name} meta statement")
    if not re.search(r"<title>\s*[^<]{2,}\s*</title>", html, re.I):
        raise ValidationError("HTML requires a useful title")
    if not re.search(r"@page\s*{[^}]*size\s*:\s*A4\b", html, re.I | re.S):
        raise ValidationError("HTML print CSS must declare @page size: A4")
    if not re.search(r"@media\s+print", html, re.I):
        raise ValidationError("HTML requires an explicit print stylesheet")
    if re.search(r"<[^>]+\shidden(?:\s|=|>)", lower) or re.search(r"aria-hidden=[\"']true[\"']", lower):
        raise ValidationError("canonical companion must not hide reading content")

    parser = CanonicalHTML()
    parser.feed(html)
    if parser.duplicate_ids:
        raise ValidationError("HTML contains duplicate navigation/evidence IDs: " + ", ".join(sorted(parser.duplicate_ids)))
    if parser.html_attrs.get("dir", "").lower() != "rtl" or not parser.html_attrs.get("lang", "").lower().startswith("ar"):
        raise ValidationError("HTML root must declare lang=ar and dir=rtl")
    if parser.main_count != 1 or parser.canonical_count != 1:
        raise ValidationError("HTML requires exactly one main and one article[data-canonical-content=true]")
    canonical_text = " ".join(parser.text)
    canonical_words = words(canonical_text)
    if len(canonical_words) < 60 or len(ARABIC_RE.findall(canonical_text)) < 120:
        raise ValidationError("canonical Arabic reading body is too shallow")
    if not parser.headings or parser.headings[0][0] != 1 or sum(1 for level, _ in parser.headings if level == 1) != 1:
        raise ValidationError("canonical article requires exactly one leading h1")
    for previous, current in zip(parser.headings, parser.headings[1:]):
        if current[0] > previous[0] + 1:
            raise ValidationError("heading hierarchy skips a level")
    rendered_scope_ids = set(parser.scope_ids)
    unknown = rendered_scope_ids - set(scope_ids)
    missing = set(scope_ids) - rendered_scope_ids
    if unknown:
        raise ValidationError("HTML references unknown source scope ids: " + ", ".join(sorted(unknown)))
    if missing:
        raise ValidationError("HTML omits source scope ids: " + ", ".join(sorted(missing)))
    if parser.tables and (parser.table_captions < parser.tables or parser.table_headers < parser.tables):
        raise ValidationError("every native table requires a caption and header cells")
    for index, svg in enumerate(parser.svgs, start=1):
        attrs = svg["attrs"]
        fragment = " ".join(svg["text"])
        if attrs.get("role") != "img" or not attrs.get("data-visual-purpose"):
            raise ValidationError(f"inline SVG {index} requires role=img and a source-specific data-visual-purpose")
        if not svg["has_title"] or not svg["has_desc"] or not ARABIC_RE.search(fragment):
            raise ValidationError(f"inline SVG {index} requires Arabic labels plus title and desc")
    stats = {"canonical_words": len(canonical_words), "authored_words": len(words(" ".join(parser.authored_text))), "headings": len(parser.headings), "tables": parser.tables, "inline_svgs": len(parser.svgs), "source_scopes": len(scope_ids)}
    return canonical_text, stats, parser


def contains_word_sequence(container: str | list[str], anchor: str) -> bool:
    container_words = container if isinstance(container, list) else words(container)
    container_words = [compact_characters(token) for token in container_words if compact_characters(token)]
    anchor_words = [compact_characters(token) for token in words(anchor) if compact_characters(token)]
    if len(anchor_words) < 2:
        return False
    size = len(anchor_words)
    return any(container_words[index:index + size] == anchor_words for index in range(len(container_words) - size + 1))


def authored_digest(parser: CanonicalHTML) -> str:
    return hashlib.sha256(" ".join(parser.authored_text).encode("utf-8")).hexdigest()


def check_editorial_review(ledger: dict[str, Any], parser: CanonicalHTML) -> dict[str, Any]:
    review = ledger.get("editorial_review")
    if not isinstance(review, dict) or review.get("schema_version") != EDITORIAL_SCHEMA:
        raise ValidationError(f"coverage ledger requires an editorial_review with schema_version {EDITORIAL_SCHEMA}")
    if review.get("language") != "egyptian-arabic":
        raise ValidationError("editorial review must declare the requested egyptian-arabic teaching voice")
    for field in ("reader_goal", "assumed_knowledge"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            raise ValidationError(f"editorial review requires {field}")
    if review.get("authored_text_sha256") != authored_digest(parser):
        raise ValidationError("editorial review is stale: authored_text_sha256 does not match the final authored explanation")
    passes = review.get("passes")
    if not isinstance(passes, dict):
        raise ValidationError("editorial review requires fidelity, teaching, language, and continuity passes")
    for name in ("fidelity", "teaching", "language", "continuity"):
        evidence = passes.get(name)
        if not isinstance(evidence, dict) or not isinstance(evidence.get("note"), str) or not evidence["note"].strip():
            raise ValidationError(f"editorial review requires concrete {name} evidence")
        section = str(evidence.get("section_id") or "")
        anchor = str(evidence.get("anchor_text") or "")
        if section not in parser.authored_id_text or not contains_word_sequence(" ".join(parser.authored_id_text[section]), anchor):
            raise ValidationError(f"editorial {name} evidence does not resolve to an authored passage")
    return {"editorial_review_schema": EDITORIAL_SCHEMA, "editorial_review_passes": 4}


def check_claim_traceability(source_path: Path, scope_path: Path, ledger_path: Path, parser: CanonicalHTML) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    source_words = words(source_bytes.decode("utf-8"))
    scope = load_json(scope_path, "source scope")
    spans = {str(span["id"]): span for span in scope["spans"]}
    ledger = load_json(ledger_path, "coverage ledger")
    if ledger.get("schema_version") != LEDGER_SCHEMA:
        raise ValidationError(f"coverage ledger schema_version must be {LEDGER_SCHEMA}")
    if ledger.get("source_sha256") != hashlib.sha256(source_bytes).hexdigest():
        raise ValidationError("coverage ledger hash does not match the extracted source")
    claims = ledger.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValidationError("coverage ledger must contain one or more claims")
    declared_items = ledger.get("source_items", [])
    if not isinstance(declared_items, list) or any(not str(item).strip() for item in declared_items):
        raise ValidationError("coverage ledger source_items must be a list of non-empty identifiers")
    expected_items = {str(item).strip() for item in declared_items}
    claim_ids: set[str] = set()
    covered_scopes: set[str] = set()
    scope_claim_counts = Counter()
    covered_items: set[str] = set()
    meaning_unit_count = 0
    for index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            raise ValidationError(f"coverage claim {index} must be an object")
        claim_id = str(claim.get("id") or "")
        if not re.fullmatch(r"claim-[a-zA-Z0-9._-]+", claim_id) or claim_id in claim_ids:
            raise ValidationError(f"coverage claim {index} needs a unique claim-* id")
        claim_ids.add(claim_id)
        claim_scopes = claim.get("source_scope_ids")
        if not isinstance(claim_scopes, list) or not claim_scopes:
            raise ValidationError(f"coverage claim {claim_id} requires source_scope_ids")
        normalized_scopes = [str(scope_id) for scope_id in claim_scopes]
        if len(normalized_scopes) != 1:
            raise ValidationError(f"coverage claim {claim_id} must clear exactly one fine source scope")
        unknown = set(normalized_scopes) - set(spans)
        if unknown:
            raise ValidationError(f"coverage claim {claim_id} references unknown scopes: {', '.join(sorted(unknown))}")
        source_anchor = str(claim.get("source_anchor_text") or "").strip()
        scoped_words: list[str] = []
        for scope_id in normalized_scopes:
            span = spans[scope_id]
            scoped_words.extend(source_words[int(span["word_start"]):int(span["word_end"])])
        if not contains_word_sequence(scoped_words, source_anchor):
            raise ValidationError(f"coverage claim {claim_id} source anchor is not present in its declared source scopes")
        source_summary = str(claim.get("source_summary") or "").strip()
        if not source_summary:
            raise ValidationError(f"coverage claim {claim_id} requires a source-grounded summary")
        if source_summary != str(spans[normalized_scopes[0]].get("summary") or "").strip():
            raise ValidationError(f"coverage claim {claim_id} summary must match its reviewed source scope summary")
        section_id = str(claim.get("html_section_id") or "").strip()
        if section_id == "exact-source" or section_id.startswith("exact-source-"):
            raise ValidationError(f"coverage claim {claim_id} must map to authored analysis, not the complete-source appendix")
        if section_id not in parser.authored_id_text:
            raise ValidationError(f"coverage claim {claim_id} references missing visible HTML section #{section_id}")
        html_anchor = str(claim.get("html_anchor_text") or "").strip()
        authored_section = " ".join(parser.authored_id_text[section_id])
        if not contains_word_sequence(authored_section, html_anchor):
            raise ValidationError(f"coverage claim {claim_id} HTML anchor is not present in #{section_id}")
        units = claim.get("meaning_units")
        if not isinstance(units, list) or not units:
            raise ValidationError(f"coverage claim {claim_id} requires a reviewed meaning_units inventory")
        seen_units: set[tuple[str, str, str]] = set()
        for unit in units:
            if not isinstance(unit, dict) or not isinstance(unit.get("kind"), str) or unit["kind"] not in MEANING_KINDS:
                raise ValidationError(f"coverage claim {claim_id} has an invalid meaning unit kind")
            source_unit = str(unit.get("source_anchor_text") or "")
            html_unit = str(unit.get("html_anchor_text") or "")
            identity = (unit["kind"], source_unit, html_unit)
            if identity in seen_units:
                raise ValidationError(f"coverage claim {claim_id} repeats a meaning unit")
            seen_units.add(identity)
            if not contains_word_sequence(scoped_words, source_unit) or not contains_word_sequence(authored_section, html_unit):
                raise ValidationError(f"coverage claim {claim_id} meaning unit does not resolve to its source and authored passage")
            meaning_unit_count += 1
        source_item = str(claim.get("source_item") or "").strip()
        if source_item and source_item not in expected_items:
            raise ValidationError(f"coverage claim {claim_id} requires a declared source_item")
        covered_scopes.update(normalized_scopes)
        scope_claim_counts.update(normalized_scopes)
        if source_item:
            covered_items.add(source_item)
    missing_scopes = set(spans) - covered_scopes
    if missing_scopes:
        raise ValidationError("coverage ledger omits source scopes: " + ", ".join(sorted(missing_scopes)))
    duplicated_scopes = sorted(scope_id for scope_id, count in scope_claim_counts.items() if count != 1)
    if duplicated_scopes:
        raise ValidationError("coverage ledger must clear each fine source scope exactly once: " + ", ".join(duplicated_scopes))
    missing_items = expected_items - covered_items
    if missing_items:
        raise ValidationError("coverage ledger omits declared source items: " + ", ".join(sorted(missing_items)))
    return {"claims": len(claims), "meaning_units": meaning_unit_count, "declared_source_items": len(expected_items), **check_editorial_review(ledger, parser)}


def check_exact_source_coverage(source_path: Path, scope_path: Path, parser: CanonicalHTML) -> dict[str, Any]:
    source_words = words(source_path.read_text(encoding="utf-8"))
    scope = load_json(scope_path, "source scope")
    spans = scope.get("spans") or []
    expected_ids = [str(span.get("id") or "") for span in spans]
    if parser.exact_scope_duplicates:
        raise ValidationError("exact source scope ids must be unique: " + ", ".join(sorted(parser.exact_scope_duplicates)))
    if parser.exact_scope_order != expected_ids:
        raise ValidationError("exact source scopes are missing, duplicated, or out of source order")
    exact_words = 0
    for span in spans:
        scope_id = str(span["id"])
        expected = source_words[int(span["word_start"]):int(span["word_end"])]
        actual = words(" ".join(parser.exact_scope_text.get(scope_id, [])))
        if actual != expected:
            raise ValidationError(f"exact source scope {scope_id} differs from the extracted source")
        exact_words += len(actual)
    if exact_words != len(source_words):
        raise ValidationError("exact source scopes do not preserve every extracted source word")
    return {"exact_source_scopes": len(expected_ids), "exact_source_words": exact_words}


BROWSER_SCRIPT = r"""
import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
const path = process.argv[1];
const seconds = Number(process.env.LITE_VISUAL_CHILD_TIMEOUT_SECONDS ?? 150);
if (!Number.isFinite(seconds) || seconds <= 0) throw new Error('invalid browser deadline');
const started = Date.now();
const browser = await chromium.launch({headless:true,timeout:Math.min(30000,seconds*1000)});
const watchdog = setTimeout(() => { void browser.close().catch(() => {}); }, Math.max(1,seconds*1000-(Date.now()-started)));
try {
const page = await browser.newPage({javaScriptEnabled:false});
const input = pathToFileURL(path).href;
const blocked = new Set();
await page.route('**/*', async route => {
  const url = route.request().url();
  if (url === input || url.startsWith('data:')) await route.continue();
  else { blocked.add(url); await route.abort(); }
});
const load = async () => {
  await page.goto(input, {waitUntil:'load',timeout:30000});
  await page.evaluate(() => document.fonts.ready);
  if (blocked.size) throw new Error('Companion is not self-contained: external resources were blocked');
};
const results = [];
const inspect = async () => page.evaluate(async () => {
  const exact = [...document.querySelectorAll('[data-exact-source-scope]')];
  const article = document.querySelector('article[data-canonical-content="true"]');
  const issues = [];
  let textNodes = 0;
  const colorContext = document.createElement('canvas').getContext('2d', {willReadFrequently:true});
  const rgba = (value) => {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) {
      if (!colorContext || !CSS.supports('color',value)) return null;
      colorContext.clearRect(0,0,1,1);
      colorContext.fillStyle = value;
      colorContext.fillRect(0,0,1,1);
      const channels = [...colorContext.getImageData(0,0,1,1).data];
      return [...channels.slice(0,3),channels[3]/255];
    }
    const parts = match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    return parts.length >= 3 ? [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1] : null;
  };
  const effectiveBackground = (element) => {
    const chain = [];
    for (let node = element; node; node = node.parentElement) chain.unshift(node);
    let color = [255,255,255];
    for (const node of chain) {
      const bg = rgba(getComputedStyle(node).backgroundColor);
      if (!bg || bg[3] <= 0) continue;
      color = bg.slice(0,3).map((channel,index) => channel * bg[3] + color[index] * (1-bg[3]));
    }
    return color;
  };
  const luminance = (color) => {
    const channels = color.map((value) => { const n=value/255; return n <= .04045 ? n/12.92 : ((n+.055)/1.055) ** 2.4; });
    return channels[0]*.2126 + channels[1]*.7152 + channels[2]*.0722;
  };
  const contrast = (front, back) => { const a=luminance(front), b=luminance(back); return (Math.max(a,b)+.05)/(Math.min(a,b)+.05); };
  for (const el of article ? [article] : []) {
    const id = 'canonical-article';
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) issues.push(`${id}:hidden`);
    if ((style.overflow === 'hidden' || style.overflowY === 'hidden' || style.overflow === 'clip' || style.overflowY === 'clip') && el.scrollHeight > el.clientHeight + 2) issues.push(`${id}:clipped`);
    if (style.clipPath !== 'none') issues.push(`${id}:clip-path`);
    if (rect.left < -2 || rect.right > document.documentElement.clientWidth + 2) issues.push(`${id}:off-canvas`);
    for (const candidate of [el, ...el.querySelectorAll('*')]) for (const pseudo of ['::before','::after']) {
      const pseudoStyle = getComputedStyle(candidate, pseudo);
      if (pseudoStyle.content && !['none','normal','""'].includes(pseudoStyle.content) && Number(pseudoStyle.opacity || 1) > .1) issues.push(`${id}:pseudo-content`);
    }
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!node.textContent.trim()) continue;
      if (node.parentElement?.closest('style,script,template,noscript,svg title,svg desc')) continue;
      textNodes += 1;
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = [...range.getClientRects()].filter((item) => item.width > 0 && item.height > 0);
      const parent = node.parentElement || el;
      const textStyle = getComputedStyle(parent);
      let opacity = 1;
      let clipped = false;
      for (let ancestor = parent; ancestor; ancestor = ancestor.parentElement) {
        const ancestorStyle = getComputedStyle(ancestor);
        opacity *= Number(ancestorStyle.opacity || 1);
        const bounds = ancestor.getBoundingClientRect();
        if (ancestorStyle.display === 'none' || ['hidden','collapse'].includes(ancestorStyle.visibility) || ancestorStyle.clipPath !== 'none') clipped = true;
        if (['hidden','clip'].includes(ancestorStyle.overflowX) && rects.some(r => r.left < bounds.left-2 || r.right > bounds.right+2)) clipped = true;
        if (['hidden','clip'].includes(ancestorStyle.overflowY) && rects.some(r => r.top < bounds.top-2 || r.bottom > bounds.bottom+2)) clipped = true;
      }
      const fontSize = parseFloat(textStyle.fontSize);
      const lineHeight = parseFloat(textStyle.lineHeight);
      const foreground = rgba(textStyle.webkitTextFillColor === 'transparent' ? 'rgba(0,0,0,0)' : textStyle.color);
      const transparent = !foreground || foreground[3] < .8 || textStyle.webkitTextFillColor === 'transparent';
      parent.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      // Instant scrolling and the following geometry/hit-test reads flush layout
      // synchronously. A frame wait per text node adds ~N/60 seconds per mode.
      // Still inspect every node, its ancestors, and its actual hit-test result.
      const visibleRect = [...range.getClientRects()].find((item) => item.width > 0 && item.height > 0 && item.bottom > 0 && item.top < innerHeight);
      const top = visibleRect ? document.elementsFromPoint(Math.min(innerWidth-1, Math.max(0, visibleRect.left + visibleRect.width/2)), Math.min(innerHeight-1, Math.max(0, visibleRect.top + visibleRect.height/2)))[0] : null;
      const occluded = !visibleRect || !top || !parent.contains(top);
      const background = effectiveBackground(parent);
      const compositeForeground = foreground ? foreground.slice(0,3).map((channel,index) => channel*foreground[3]*opacity+background[index]*(1-foreground[3]*opacity)) : null;
      const lowContrast = compositeForeground ? contrast(compositeForeground, background) < 4.5 : true;
      const prose = parent.closest('p,li,td,th,blockquote,dd,dt,[data-exact-source-scope]') && !parent.closest('nav,figcaption,footer');
      const minSize = prose ? 16 : 12;
      const minLeading = prose ? 1.45 : 1.1;
      const location = parent.closest('[data-source-scope],[data-exact-source-scope],[id]');
      const label = location?.getAttribute('data-source-scope') || location?.getAttribute('data-exact-source-scope') || location?.id || parent.tagName;
      if (!rects.length || clipped || opacity < 0.8 || transparent || lowContrast || occluded || fontSize < minSize || Number.isFinite(lineHeight) && lineHeight < fontSize * minLeading) issues.push(`${label}:unreadable-text`);
    }
  }
  const body = getComputedStyle(document.body);
  const firstBlock = article ? article.firstElementChild : null;
  const opening = firstBlock && firstBlock.querySelector('h1')
    ? firstBlock
    : article ? (article.querySelector(':scope > header') || article.querySelector(':scope > .opening')) : null;
  const openingIssues = [];
  if (opening && innerWidth >= 768) {
    const rect = opening.getBoundingClientRect();
    const wordCount = (opening.innerText || '').trim().split(/\s+/).filter(Boolean).length;
    if (rect.height > innerHeight * .65 && wordCount < 80) openingIssues.push('sparse-opening-consumes-most-of-viewport');
  }
  const title = article ? article.querySelector('h1') : null;
  if (title && parseFloat(getComputedStyle(title).fontSize) > 72) openingIssues.push('oversized-title');
  if (opening && title) {
    const a = title.getBoundingClientRect();
    const overlapsTitle = [...opening.querySelectorAll('*')].some((el) => {
      if (el === title || el.contains(title) || title.contains(el)) return false;
      if (![...el.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim())) return false;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      const b = el.getBoundingClientRect();
      return Math.min(a.right,b.right)-Math.max(a.left,b.left) > 4 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top) > 4;
    });
    if (overlapsTitle) openingIssues.push('title-overlaps-opening-text');
  }
  const visible = [...document.querySelectorAll('body *')].filter((el) => {
    const style = getComputedStyle(el); const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  });
  const overflow = visible.filter((el) => { const r=el.getBoundingClientRect(); return r.left < -2 || r.right > document.documentElement.clientWidth + 2; }).slice(0,8).map((el)=>el.tagName.toLowerCase()+'.'+String(el.className||''));
  return {direction:body.direction, scrollWidth:document.documentElement.scrollWidth, clientWidth:document.documentElement.clientWidth, overflow, fontSize:parseFloat(body.fontSize), lineHeight:parseFloat(body.lineHeight), exactCount:exact.length, exactTextNodes:textNodes, exactIssues:issues, openingIssues};
});
for (const width of [360, 768, 1280]) {
  await page.setViewportSize({width, height:900});
  await load();
  results.push({width, ...(await inspect())});
}
await page.setViewportSize({width:1280,height:900});
await load();
const resizedNodes = await page.evaluate(() => {
  const sizes = [...document.querySelectorAll('body,body *')].filter(el => !el.closest('style,script,template,noscript')).map(el => {
    const style=getComputedStyle(el);
    return {el,size:parseFloat(style.fontSize),leading:parseFloat(style.lineHeight)};
  });
  for (const {el,size,leading} of sizes) {
    el.style.setProperty('font-size',`${size*2}px`,'important');
    if (Number.isFinite(leading)) el.style.setProperty('line-height',`${leading*2}px`,'important');
  }
  if (sizes.some(({el,size}) => Math.abs(parseFloat(getComputedStyle(el).fontSize)-size*2) > .1)) throw new Error('text enlargement did not double every computed text size');
  return sizes.length;
});
results.push({textResize:true, resizedNodes, ...(await inspect())});
await page.emulateMedia({media:'print'});
await load();
results.push({printMedia:true, ...(await inspect())});
process.stdout.write(JSON.stringify(results));
} finally {
  clearTimeout(watchdog);
  await browser.close();
}
"""


def check_browser(html_path: Path, expected_exact_scopes: int) -> dict[str, Any]:
    root = Path("/home/mahmud/recommendations-worker")
    output = run(["node", "--input-type=module", "-e", BROWSER_SCRIPT, str(html_path.resolve())], "responsive browser validation", root)
    try:
        results = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"responsive browser validation returned invalid JSON: {exc}") from exc
    for item in results:
        mode = "print media" if item.get("printMedia") else "200% text size" if item.get("textResize") else f"{item.get('width')}px"
        if item.get("exactCount") != expected_exact_scopes or item.get("exactTextNodes", 0) < expected_exact_scopes or item.get("exactIssues"):
            raise ValidationError(f"canonical reading content or source scopes are missing, hidden, or unreadable in {mode}: {item.get('exactIssues')}")
        if item.get("scrollWidth", 0) > item.get("clientWidth", 0) + 2 or item.get("overflow"):
            raise ValidationError(f"HTML overflows horizontally in {mode}: {item.get('overflow')}")
        if item.get("textResize"):
            if item.get("scrollWidth", 0) > item.get("clientWidth", 0) + 2:
                raise ValidationError("HTML overflows horizontally at 200% text size")
            continue
        if item.get("printMedia"):
            if item.get("direction") != "rtl":
                raise ValidationError("HTML is not RTL in print media")
            continue
        if item.get("direction") != "rtl":
            raise ValidationError(f"computed direction is not RTL at {item.get('width')}px")
        if item.get("openingIssues"):
            raise ValidationError(f"HTML opening obstructs the reading task at {item.get('width')}px: {item.get('openingIssues')}")
        if item.get("scrollWidth", 0) > item.get("clientWidth", 0) + 2 or item.get("overflow"):
            raise ValidationError(f"HTML overflows horizontally at {item.get('width')}px: {item.get('overflow')}")
        if item.get("fontSize", 0) < 16 or item.get("lineHeight", 0) < item.get("fontSize", 0) * 1.45:
            raise ValidationError("body typography is too small or cramped for sustained Arabic reading")
    print_result = next(item for item in results if item.get("printMedia"))
    return {"viewports": [360, 768, 1280], "text_resize_percent": 200, "resized_elements": next(item["resizedNodes"] for item in results if item.get("textResize")), "print_exact_source_scopes": print_result["exactCount"], "print_reading_text_nodes": print_result["exactTextNodes"]}


def check_pdf(pdf_path: Path, canonical_text: str, source_text: str, exact_scope_text: dict[str, list[str]]) -> dict[str, Any]:
    info = run(["pdfinfo", str(pdf_path)], "pdfinfo")
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.M)
    if not pages_match:
        raise ValidationError("PDF page count is unavailable")
    page_count = int(pages_match.group(1))
    if page_count < 1:
        raise ValidationError("PDF has no pages")
    page_info = run(["pdfinfo", "-f", "1", "-l", str(page_count), str(pdf_path)], "all-page PDF geometry")
    sizes = re.findall(r"^Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", page_info, re.M | re.I)
    if [int(number) for number, _, _ in sizes] != list(range(1, page_count + 1)):
        raise ValidationError("PDF page geometry is missing, duplicated, or out of order")
    # One extraction retains Poppler's existing Arabic ordering and form-feed
    # boundaries. Do not strip its final page separator before splitting.
    pdf_text = run(["pdftotext", str(pdf_path), "-"], "all-page PDF text extraction")
    page_texts = pdf_text.split("\f")
    if len(page_texts) == page_count + 1 and not page_texts[-1].strip():
        page_texts.pop()
    if len(page_texts) != page_count:
        raise ValidationError("PDF extracted page boundaries do not match the page count")
    for (number, width, height), page_text in zip(sizes, page_texts):
        page = int(number)
        if abs(float(width) - 595) > 2 or abs(float(height) - 842) > 2:
            raise ValidationError(f"PDF page {page} is not A4")
        if len(words(page_text)) < 8:
            raise ValidationError(f"PDF page {page} is near-empty")
    compact_pdf = compact_characters(pdf_text)
    cursor = 0
    exact_characters = 0
    for scope_id, values in exact_scope_text.items():
        expected = compact_characters(" ".join(values))
        if not expected:
            raise ValidationError(f"PDF exact source scope {scope_id} has no expected text")
        position = ordered_pdf_scope(compact_pdf, expected, cursor)
        if position is None:
            raise ValidationError(f"PDF exact source scope {scope_id} is missing, changed, or out of order")
        cursor = position
        exact_characters += len(expected)
    html_words = words(canonical_text)
    pdf_words = words(pdf_text)
    word_overlap = sum((Counter(html_words) & Counter(pdf_words)).values()) / max(1, len(html_words))
    html_ngrams = ngrams(compact_characters(canonical_text))
    pdf_ngrams = ngrams(compact_characters(pdf_text))
    character_overlap = sum((Counter(html_ngrams) & Counter(pdf_ngrams)).values()) / max(1, len(html_ngrams))
    if word_overlap < 0.88 and character_overlap < 0.95:
        missing = list((Counter(html_words) - Counter(pdf_words)).elements())[:12]
        raise ValidationError(
            f"PDF text parity is too low (word overlap={word_overlap:.1%}, "
            f"character-trigram overlap={character_overlap:.1%}; HTML words={len(html_words)}, "
            f"PDF words={len(pdf_words)}, missing sample={missing}); "
            "print from the canonical HTML without rewriting it"
        )
    source_words = words(source_text)
    source_word_overlap = sum((Counter(source_words) & Counter(pdf_words)).values()) / max(1, len(source_words))
    source_ngrams = ngrams(compact_characters(source_text))
    source_character_overlap = sum((Counter(source_ngrams) & Counter(pdf_ngrams)).values()) / max(1, len(source_ngrams))
    return {
        "pages": page_count,
        "canonical_word_overlap": round(word_overlap, 4),
        "canonical_character_trigram_overlap": round(character_overlap, 4),
        "source_word_overlap": round(source_word_overlap, 4),
        "source_character_trigram_overlap": round(source_character_overlap, 4),
        "pdf_exact_source_scopes": len(exact_scope_text),
        "pdf_exact_source_characters": exact_characters,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="complete cached UTF-8 source text")
    parser.add_argument("--source-scope", required=True, type=Path, help="gapless source coverage manifest")
    parser.add_argument("--coverage-ledger", required=True, type=Path, help="claim-level source-to-HTML traceability ledger")
    parser.add_argument("--html", required=True, type=Path, help="single canonical semantic HTML body")
    parser.add_argument("--pdf", required=True, type=Path, help="A4 PDF printed from the canonical HTML")
    parser.add_argument("--work-item", required=True, type=Path, help="exact publication target identity")
    parser.add_argument("--source-extraction", required=True, type=Path, help="complete source extraction receipt")
    parser.add_argument("--receipt-out", required=True, type=Path, help="write the hash-bound passing receipt here")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--authored-digest":
        parser = CanonicalHTML()
        parser.feed(Path(argv[1]).read_text(encoding="utf-8"))
        if parser.canonical_count != 1 or not parser.authored_text:
            print("FAIL: digest requires one canonical article with authored text", file=sys.stderr)
            return 1
        print(authored_digest(parser))
        return 0
    args = parse_args(argv)
    try:
        for path, label in ((args.source, "source"), (args.source_scope, "source scope"), (args.coverage_ledger, "coverage ledger"), (args.html, "HTML"), (args.pdf, "PDF"), (args.work_item, "work item"), (args.source_extraction, "source extraction")):
            if not path.is_file() or path.stat().st_size == 0:
                raise ValidationError(f"{label} file is missing or empty: {path}")
        with tempfile.TemporaryDirectory(prefix="lite-visual-validation-") as directory:
            snapshot_root = Path(directory)
            snapshots: dict[str, Path] = {}
            for label, path in (("source", args.source), ("source_scope", args.source_scope), ("coverage_ledger", args.coverage_ledger), ("html", args.html), ("pdf", args.pdf), ("work_item", args.work_item), ("source_extraction", args.source_extraction)):
                target = snapshot_root / path.name
                shutil.copyfile(path, target)
                snapshots[label] = target
            checks_started = time.perf_counter()
            scope_ids, source_word_count = check_source_scope(snapshots["source"], snapshots["source_scope"])
            canonical_text, html_stats, parser = check_html(snapshots["html"], scope_ids)
            ledger_stats = check_claim_traceability(snapshots["source"], snapshots["source_scope"], snapshots["coverage_ledger"], parser)
            exact_stats = check_exact_source_coverage(snapshots["source"], snapshots["source_scope"], parser)
            static_finished = time.perf_counter()
            browser_stats = check_browser(snapshots["html"], exact_stats["exact_source_scopes"])
            browser_finished = time.perf_counter()
            pdf_stats = check_pdf(snapshots["pdf"], canonical_text, snapshots["source"].read_text(encoding="utf-8"), parser.exact_scope_text)
            pdf_finished = time.perf_counter()
            work_item = load_json(snapshots["work_item"], "work item")
            extraction = load_json(snapshots["source_extraction"], "source extraction")
            target = {key: str(work_item.get(key) or "").strip() for key in ("recommendation_id", "source_url", "source_title")}
            chapter_key = str(work_item.get("chapter_key") or "").strip()
            if chapter_key:
                target["chapter_key"] = chapter_key
            if any(not value for value in target.values()):
                raise ValidationError("work item must contain recommendation_id, source_url, and source_title")
            if extraction.get("status") != "complete" or extraction.get("content_sha256") != sha256(snapshots["source"]):
                raise ValidationError("source extraction is not complete or does not match source.txt")
            raw_stats = {"source_words": source_word_count, **ledger_stats, **exact_stats, **html_stats, **browser_stats, **pdf_stats,
                         "static_checks_ms": round((static_finished-checks_started)*1000),
                         "browser_checks_ms": round((browser_finished-static_finished)*1000),
                         "pdf_checks_ms": round((pdf_finished-browser_finished)*1000)}
            stats = {
                (f"{key}_basis_points" if isinstance(value, float) else key): (round(value * 10_000) if isinstance(value, float) else value)
                for key, value in raw_stats.items()
            }
            receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "workflow_contract": WORKFLOW_CONTRACT,
            "status": "passed",
            "source_sha256": sha256(snapshots["source"]),
            "source_scope_sha256": sha256(snapshots["source_scope"]),
            "coverage_ledger_sha256": sha256(snapshots["coverage_ledger"]),
            "html_sha256": sha256(snapshots["html"]),
            "pdf_sha256": sha256(snapshots["pdf"]),
            "work_item_sha256": sha256(snapshots["work_item"]),
            "source_extraction_sha256": sha256(snapshots["source_extraction"]),
            "target": target,
            "target_sha256": target_sha256(target),
            "checks": {"source_coverage": True, "claim_traceability": True, "exact_source_html": True, "exact_source_pdf": True, "canonical_html": True, "code_only": True, "rtl": True, "accessibility": True, "responsive": True, "print_a4": True, "pdf_parity": True},
            "stats": stats,
            "validated_at": datetime.now(timezone.utc).isoformat(),
            }
            attest_receipt(receipt)
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.receipt_out.parent, prefix=f".{args.receipt_out.name}.", suffix=".tmp", delete=False) as handle:
                handle.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            temporary.replace(args.receipt_out)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        print(json.dumps({"ok": True, "status": "passed", "receipt": str(args.receipt_out), "stats": receipt["stats"]}, ensure_ascii=False))
        return 0
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
