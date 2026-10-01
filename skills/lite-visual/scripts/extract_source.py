#!/usr/bin/env python3
"""Resolve any Visual Lite source into one verified, cached UTF-8 source.txt.

Fast path: a fresh cache hit copies the immutable extraction locally without a
network request. First-run paths stay source-specific: Mozilla Readability for
articles, official/manual captions then generated captions for YouTube,
PyMuPDF plus bounded OCR for PDFs, OPF spine order for EPUB, Pandoc for office
documents, and direct bytes for text/uploads.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup


VERSION = "lite-visual-source-extractor/4"
SCHEMA = "lite-visual-source-extraction/v1"
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path("/home/mahmud/recommendations-worker")
ARTICLE_SCRIPT = SCRIPT_DIR / "extract_article.mjs"
RENDER_SCRIPT = SCRIPT_DIR / "render_page.mjs"
TRANSCRIPT_SCRIPT = SCRIPT_DIR / "fetch_transcript.py"
DEFAULT_CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "learning-compass" / "source-extraction"
WORD_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
PAYWALL_RE = re.compile(r"(?:subscribe to (?:continue|read)|sign in to (?:continue|read)|members only|subscriber-only|اشترك (?:للمتابعة|للقراءة)|سجّل الدخول للمتابعة)", re.I)
TIMESTAMP_LABEL_RE = re.compile(r"\[\d{1,2}:\d{1,3}(?::\d{1,3}(?:\.\d{1,3})?(?:WORDS_BEHIND_START)?)?\]")
BROKEN_TIMESTAMP_LABEL_RE = re.compile(r"\[\d{1,2}:\d{1,3}(?::\d{1,3}(?:\.\d{1,3})?)?(?=\s+(?:\[|[\u0600-\u06ff]))")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class ExtractionError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def word_count(value: str) -> int:
    return len(WORD_RE.findall(value))


def stripped_text_sha256(value: str) -> str:
    return sha256_bytes(value.strip().encode("utf-8"))


def normalized_words(value: str) -> list[str]:
    normalized = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", value)
    normalized = normalized.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})).lower()
    return WORD_RE.findall(normalized)


def duplicate_passages(value: str, size: int = 40) -> list[tuple[int, int]]:
    tokens = normalized_words(value)
    seen: dict[tuple[str, ...], int] = {}
    found: list[tuple[int, int, int]] = []
    for index in range(max(0, len(tokens) - size + 1)):
        window = tuple(tokens[index:index + size])
        previous = seen.get(window)
        if previous is not None and index - previous >= size:
            covered = any(
                index - previous == second - first
                and first <= previous
                and index >= second
                and previous + size <= first + exact_run
                and index + size <= second + exact_run
                for first, second, exact_run in found
            )
            if not covered:
                exact_run = 0
                while previous + exact_run < len(tokens) and index + exact_run < len(tokens) and tokens[previous + exact_run] == tokens[index + exact_run]:
                    exact_run += 1
                found.append((previous, index, exact_run))
        seen.setdefault(window, index)
    return [(first, second) for first, second, _ in found]


def duplicate_passage(value: str, size: int = 40) -> tuple[int, int] | None:
    repeated = duplicate_passages(value, size)
    return repeated[0] if repeated else None


def segment_start_for_word(segments: list[dict[str, Any]], offset: int) -> float:
    cursor = 0
    for segment in segments:
        next_cursor = cursor + len(normalized_words(str(segment.get("text") or "")))
        if cursor <= offset < next_cursor:
            return float(segment["start_seconds"])
        cursor = next_cursor
    raise ExtractionError(f"repeated passage word offset {offset} is outside the timestamped segments")


def validate_repetition_review(
    review_path: Path,
    receipt: dict[str, Any],
    repeated: tuple[int, int],
    raw_text: str,
) -> dict[str, Any]:
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ExtractionError(f"verified repetition review is invalid JSON: {exc}") from exc
    if not isinstance(review, dict) or review.get("schema_version") != "riyadh-salihin-repetition-review/v1":
        raise ExtractionError("verified repetition review has an unsupported schema")
    if review.get("recording_number") != receipt.get("number"):
        raise ExtractionError("verified repetition review recording number does not match")
    if review.get("transcript_sha256") != receipt.get("transcript_sha256") or review.get("source_audio_sha256") != receipt.get("source_audio_sha256"):
        raise ExtractionError("verified repetition review is not bound to the transcript and audio hashes")
    passage = review.get("passage") or {}
    expected_offsets = (passage.get("first_word_offset"), passage.get("second_word_offset"))
    if expected_offsets != repeated or passage.get("word_count") != 40 or passage.get("classification") != "spoken_repetition":
        raise ExtractionError("verified repetition review does not match the detected passage")
    words = normalized_words(raw_text)
    first, second = repeated
    if words[first:first + 40] != words[second:second + 40]:
        raise ExtractionError("verified repetition review passage is not identical at both offsets")
    exact_run = 0
    while first + exact_run < len(words) and second + exact_run < len(words) and words[first + exact_run] == words[second + exact_run]:
        exact_run += 1
    if passage.get("exact_run_words") != exact_run:
        raise ExtractionError("verified repetition review exact-run length is stale")
    segments = receipt.get("segments") or []
    first_start = segment_start_for_word(segments, first)
    second_start = segment_start_for_word(segments, second)
    if passage.get("first_segment_start_seconds") != first_start or passage.get("second_segment_start_seconds") != second_start:
        raise ExtractionError("verified repetition review timestamp anchors are stale")
    if second_start <= first_start or not str(passage.get("reason") or "").strip():
        raise ExtractionError("verified repetition review lacks a grounded spoken-repetition rationale")
    return review


def extract_verified_transcript(
    transcript_path: Path,
    receipt_path: Path,
    canonical_source: str,
    strip_embedded_timestamps: bool,
    repetition_review_path: Path | None,
) -> tuple[str, dict[str, Any], list[str]]:
    if not transcript_path.is_file() or not receipt_path.is_file():
        raise ExtractionError("verified transcript text or receipt does not exist")
    parsed = urlparse(canonical_source)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ExtractionError("canonical transcript source must be a public HTTP(S) URL without credentials")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ExtractionError(f"verified transcript receipt is invalid JSON: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != "riyadh-salihin-local-transcript/v1":
        raise ExtractionError("verified transcript receipt has an unsupported schema")
    raw_text = transcript_path.read_text(encoding="utf-8-sig")
    transcript_sha256 = receipt.get("transcript_sha256")
    if not isinstance(transcript_sha256, str) or not SHA256_RE.fullmatch(transcript_sha256):
        raise ExtractionError("verified transcript receipt lacks a valid transcript hash")
    if stripped_text_sha256(raw_text) != transcript_sha256:
        raise ExtractionError("verified transcript text does not match its receipt hash")
    audio_sha256 = receipt.get("source_audio_sha256")
    if not isinstance(audio_sha256, str) or not SHA256_RE.fullmatch(audio_sha256):
        raise ExtractionError("verified transcript receipt lacks a valid source audio hash")
    if receipt.get("media_url") != canonical_source:
        raise ExtractionError("verified transcript receipt media URL does not match the canonical source")
    quality = receipt.get("quality") or {}
    chunks = receipt.get("chunks") or []
    if quality.get("passed") is not True or not chunks or any((chunk.get("quality") or {}).get("passed") is not True for chunk in chunks):
        raise ExtractionError("verified transcript receipt or one of its chunks did not pass quality gates")
    segments = receipt.get("segments") or []
    if not segments:
        raise ExtractionError("verified transcript receipt has no timestamped segments")
    previous_start = -1.0
    for segment in segments:
        try:
            start = float(segment["start_seconds"])
            end = float(segment["end_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractionError("verified transcript receipt contains an invalid segment") from exc
        if start < previous_start or end < start:
            raise ExtractionError("verified transcript receipt timestamps are not monotonic")
        previous_start = start
    repeated_passages = duplicate_passages(raw_text)
    repeated = repeated_passages[0] if repeated_passages else None
    repetition_review = None
    if repeated and not repetition_review_path:
        raise ExtractionError(f"verified transcript repeats a 40-word passage at word offsets {repeated[0]} and {repeated[1]}")
    if repeated and repetition_review_path:
        repetition_review = validate_repetition_review(repetition_review_path, receipt, repeated, raw_text)
    if len(repeated_passages) > 1:
        first, second = repeated_passages[1]
        raise ExtractionError(f"verified transcript contains an additional unreviewed 40-word repetition at word offsets {first} and {second}")
    removed_timestamp_labels = 0
    text = raw_text
    if strip_embedded_timestamps:
        text, removed_timestamp_labels = TIMESTAMP_LABEL_RE.subn(" ", text)
        text, removed_broken_labels = BROKEN_TIMESTAMP_LABEL_RE.subn(" ", text)
        removed_timestamp_labels += removed_broken_labels
        text = re.sub(r"[ \t]{2,}", " ", text)
    text = normalize_text(text)
    if TIMESTAMP_LABEL_RE.search(text) or BROKEN_TIMESTAMP_LABEL_RE.search(text):
        raise ExtractionError("embedded timestamp labels remain in the verified transcript")
    if word_count(text) < 20:
        raise ExtractionError("verified transcript extraction is too shallow")
    metadata = {
        "engine": "verified-local-transcript-receipt",
        "title": receipt.get("title") or None,
        "language": "ar",
        "receipt_schema": receipt["schema_version"],
        "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
        "transcript_sha256": transcript_sha256,
        "source_audio_sha256": audio_sha256,
        "source_duration_seconds": receipt.get("source_duration_seconds"),
        "recording_number": receipt.get("number"),
        "detail_url": receipt.get("detail_url"),
        "transformation": "removed_embedded_timestamp_labels" if removed_timestamp_labels else "none",
        "removed_timestamp_labels": removed_timestamp_labels,
        "repetition_review_sha256": sha256_bytes(repetition_review_path.read_bytes()) if repetition_review else None,
        "checks": {
            "minimum_words": True,
            "receipt_quality_passed": True,
            "chunk_quality_passed": True,
            "transcript_hash_matches": True,
            "audio_hash_present": True,
            "timestamps_monotonic": True,
            "duplicate_passage_safe": repeated is None or repetition_review is not None,
            "canonical_source_matches": True,
            "embedded_timestamp_labels_absent": True,
        },
    }
    warnings = [f"Removed {removed_timestamp_labels} embedded timestamp labels from the verified transcript."] if removed_timestamp_labels else []
    if repetition_review:
        warnings.append("Accepted one hash-bound, timestamp-anchored spoken repetition from the verified review.")
    return text, metadata, warnings


def run(command: list[str], label: str, cwd: Path | None = None, timeout: int = 180) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    if completed.returncode != 0:
        raise ExtractionError(f"{label} failed: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout


def is_url(value: str) -> bool:
    return urlparse(value).scheme.lower() in {"http", "https"}


def validate_public_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ExtractionError("source URL must be public HTTP(S) without embedded credentials")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ExtractionError(f"source hostname did not resolve: {exc}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ExtractionError("source URL resolves to a private, local, reserved, or otherwise non-public address")


def fetch_public_url(url: str, timeout: float, max_bytes: int) -> tuple[bytes, str, str, dict[str, str]]:
    headers = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36", "accept": "text/html,application/xhtml+xml,application/pdf,application/epub+zip,text/plain;q=0.9,*/*;q=0.5"}
    current = url
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 5)), follow_redirects=False, headers=headers) as client:
        for _ in range(6):
            validate_public_url(current)
            response = client.get(current)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ExtractionError("source redirect omitted its destination")
                current = urljoin(str(response.url), location)
                continue
            response.raise_for_status()
            declared = int(response.headers.get("content-length") or 0)
            if declared > max_bytes:
                raise ExtractionError(f"source exceeds the {max_bytes} byte download limit")
            data = response.content
            if len(data) > max_bytes:
                raise ExtractionError(f"source exceeds the {max_bytes} byte download limit")
            return data, response.headers.get("content-type", "").split(";", 1)[0].lower(), str(response.url), {key.lower(): value for key, value in response.headers.items() if key.lower() in {"etag", "last-modified"}}
    raise ExtractionError("source exceeded the maximum redirect count")


def article_from_html(html: bytes, source_url: str) -> dict[str, Any]:
    document_url = source_url if is_url(source_url) else Path(source_url).resolve().as_uri()
    with tempfile.NamedTemporaryFile(prefix="lite-visual-article-", suffix=".html", delete=False) as handle:
        path = Path(handle.name)
        handle.write(html)
    try:
        output = run(["node", str(ARTICLE_SCRIPT), str(path), document_url], "Mozilla Readability", PROJECT_ROOT, 30)
        parsed = json.loads(output)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("text"), str):
            raise ExtractionError("Mozilla Readability returned an invalid payload")
        return parsed
    finally:
        path.unlink(missing_ok=True)


def render_article(url: str) -> bytes:
    validate_public_url(url)
    with tempfile.NamedTemporaryFile(prefix="lite-visual-render-", suffix=".html", delete=False) as handle:
        path = Path(handle.name)
    try:
        run(["node", str(RENDER_SCRIPT), url, str(path)], "bounded browser rendering", PROJECT_ROOT, 30)
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def article_checks(text: str, block_count: int = 0) -> dict[str, Any]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if word_count(part) >= 5]
    normalized = [re.sub(r"\W+", " ", part.lower()).strip() for part in paragraphs]
    duplicates = len(normalized) - len(set(normalized))
    words = word_count(text)
    paywall = bool(PAYWALL_RE.search(text[:4000])) and words < 600
    return {
        "minimum_words": words >= 80,
        "multiple_paragraphs": len(paragraphs) >= 3 or block_count >= 3,
        "no_truncated_paywall": not paywall,
        "duplicate_paragraph_ratio": round(duplicates / max(1, len(paragraphs)), 4),
    }


def extract_article(data: bytes, source_url: str, allow_browser: bool) -> tuple[str, dict[str, Any], list[str]]:
    warnings: list[str] = []
    parsed = article_from_html(data, source_url)
    text = normalize_text(parsed["text"])
    checks = article_checks(text, int(parsed.get("block_count") or 0))
    if (not all(value is True for key, value in checks.items() if key != "duplicate_paragraph_ratio") or checks["duplicate_paragraph_ratio"] > 0.25) and allow_browser and is_url(source_url):
        rendered = render_article(source_url)
        browser_parsed = article_from_html(rendered, source_url)
        browser_text = normalize_text(browser_parsed["text"])
        browser_checks = article_checks(browser_text, int(browser_parsed.get("block_count") or 0))
        if word_count(browser_text) > word_count(text) and all(value is True for key, value in browser_checks.items() if key != "duplicate_paragraph_ratio"):
            parsed, text, checks = browser_parsed, browser_text, browser_checks
            parsed["engine"] = "playwright+mozilla-readability"
            warnings.append("direct HTML was incomplete; used bounded JavaScript rendering")
    if not checks["minimum_words"] or not checks["multiple_paragraphs"] or not checks["no_truncated_paywall"] or checks["duplicate_paragraph_ratio"] > 0.25:
        raise ExtractionError(f"article completeness gate failed: {json.dumps(checks, ensure_ascii=False)}")
    metadata = {key: parsed.get(key) for key in ("engine", "title", "byline", "site_name", "excerpt", "language", "canonical_url")}
    metadata["checks"] = checks
    return text, metadata, warnings


def extract_pdf(data: bytes, allow_ocr: bool) -> tuple[str, dict[str, Any], list[str]]:
    import fitz
    warnings: list[str] = []
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"PDF could not be opened: {exc}") from exc
    if document.needs_pass:
        raise ExtractionError("PDF is encrypted and requires a password")
    pages: list[str] = []
    ocr_pages: list[int] = []
    empty_pages: list[int] = []
    for index, page in enumerate(document):
        text = normalize_text(page.get_text("text", sort=True)).strip()
        if word_count(text) < 8 and allow_ocr:
            if not shutil.which("tesseract"):
                raise ExtractionError("PDF needs OCR but tesseract is unavailable")
            with tempfile.TemporaryDirectory(prefix="lite-visual-ocr-") as directory:
                image = Path(directory) / "page.png"
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(image)
                completed = subprocess.run(["tesseract", str(image), "stdout", "-l", "ara+eng", "--psm", "6"], text=True, capture_output=True, timeout=180)
                if completed.returncode == 0:
                    text = normalize_text(completed.stdout).strip()
                    if text:
                        ocr_pages.append(index + 1)
        if word_count(text) < 3:
            empty_pages.append(index + 1)
        pages.append(f"[PAGE {index + 1}]\n{text}".strip())
    if not pages:
        raise ExtractionError("PDF has no pages")
    if len(empty_pages) > max(2, int(len(pages) * 0.1)):
        raise ExtractionError(f"PDF remains incomplete after extraction; near-empty pages: {empty_pages[:20]}")
    if ocr_pages:
        warnings.append(f"OCR used on pages: {','.join(map(str, ocr_pages))}")
    text = normalize_text("\n\n".join(pages))
    if word_count(text) < 20:
        raise ExtractionError("PDF extraction is too shallow")
    return text, {"engine": "pymupdf+tesseract" if ocr_pages else "pymupdf", "page_count": len(pages), "ocr_pages": ocr_pages, "near_empty_pages": empty_pages, "checks": {"all_pages_visited": True, "near_empty_pages_within_limit": True}}, warnings


def extract_epub(data: bytes) -> tuple[str, dict[str, Any], list[str]]:
    try:
        archive = ZipFile(io.BytesIO(data))
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        if rootfile is None or not rootfile.attrib.get("full-path"):
            raise ExtractionError("EPUB container has no package rootfile")
        opf_path = PurePosixPath(rootfile.attrib["full-path"])
        package = ET.fromstring(archive.read(str(opf_path)))
        manifest = {item.attrib.get("id", ""): item.attrib for item in package.findall(".//{*}manifest/{*}item")}
        spine = [item.attrib.get("idref", "") for item in package.findall(".//{*}spine/{*}itemref")]
        title = "".join(package.findtext(".//{*}metadata/{*}title", default=""))
        language = package.findtext(".//{*}metadata/{*}language", default="")
        sections: list[str] = []
        missing: list[str] = []
        visited: list[str] = []
        textless: list[str] = []
        for position, item_id in enumerate(spine, start=1):
            href = manifest.get(item_id, {}).get("href")
            if not href:
                missing.append(item_id)
                continue
            member = str((opf_path.parent / PurePosixPath(href.split("#", 1)[0])).as_posix())
            try:
                soup = BeautifulSoup(archive.read(member), "html.parser")
            except KeyError:
                missing.append(member)
                continue
            visited.append(member)
            for node in soup(["script", "style", "nav", "noscript"]):
                node.decompose()
            body = soup.body or soup
            text = normalize_text(body.get_text("\n")).strip()
            if text:
                sections.append(f"[SPINE {position}: {member}]\n{text}")
            else:
                textless.append(member)
        if missing:
            raise ExtractionError(f"EPUB reading order references missing resources: {missing[:10]}")
        text = normalize_text("\n\n".join(sections))
        if word_count(text) < 50:
            raise ExtractionError("EPUB extraction is too shallow")
        warnings = [f"Textless spine resources visited: {','.join(textless)}"] if textless else []
        return text, {
            "engine": "epub-opf-spine",
            "title": title,
            "language": language,
            "spine_items": len(spine),
            "visited_items": len(visited),
            "extracted_items": len(sections),
            "textless_items": textless,
            "checks": {"complete_spine": len(spine) == len(visited)},
        }, warnings
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"EPUB extraction failed: {exc}") from exc


def extract_document(path: Path) -> tuple[str, dict[str, Any], list[str]]:
    if not shutil.which("pandoc"):
        raise ExtractionError("document conversion requires pandoc")
    text = normalize_text(run(["pandoc", str(path), "-t", "plain", "--wrap=none"], "Pandoc document extraction", timeout=120))
    if word_count(text) < 20:
        raise ExtractionError("document extraction is too shallow")
    return text, {"engine": "pandoc", "checks": {"minimum_words": True}}, []


def extract_transcript(source: str, languages: str, timestamps: bool, allow_audio_fallback: bool) -> tuple[str, dict[str, Any], list[str]]:
    with tempfile.TemporaryDirectory(prefix="lite-visual-transcript-") as directory:
        output = Path(directory) / "source.txt"
        manifest = Path(directory) / "receipt.json"
        command = ["python3", str(TRANSCRIPT_SCRIPT), source, "--output", str(output), "--manifest", str(manifest), "--languages", languages]
        if timestamps:
            command.append("--timestamps")
        if not allow_audio_fallback:
            command.append("--no-audio-fallback")
        run(command, "timed-media transcript", timeout=3600)
        receipt = json.loads(manifest.read_text(encoding="utf-8"))
        return normalize_text(output.read_text(encoding="utf-8")), receipt, list(receipt.get("warnings") or [])


def detect_kind(source: str, requested: str) -> str:
    if requested != "auto":
        return requested
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        return "youtube"
    suffix = Path(parsed.path if is_url(source) else source).suffix.lower()
    if suffix == ".pdf": return "pdf"
    if suffix == ".epub": return "epub"
    if suffix in {".html", ".htm", ".xhtml"}: return "article"
    if suffix in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json"}: return "text"
    if suffix in {".docx", ".odt", ".rtf", ".doc"}: return "document"
    if suffix in {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".mp4", ".mkv", ".webm"}: return "audio"
    return "article" if is_url(source) else "text"


def cache_identity(source: str, kind: str, languages: str, timestamps: bool, provenance: dict[str, Any] | None = None) -> str:
    identity: dict[str, Any] = {"version": VERSION, "source": source, "kind": kind, "languages": languages, "timestamps": timestamps}
    path = Path(source)
    if not is_url(source) and path.exists():
        stat = path.stat()
        identity["local"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    if kind in {"youtube", "audio"}:
        # Adapter changes must invalidate receipts made by older, shallower gates.
        identity["transcript_adapter_sha256"] = sha256_bytes(TRANSCRIPT_SCRIPT.read_bytes())
    if provenance:
        identity["provenance"] = provenance
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="public URL or local source file")
    parser.add_argument("--source", dest="source_option", help="alias for the positional source")
    parser.add_argument("--kind", choices=["auto", "article", "youtube", "audio", "pdf", "epub", "document", "text"], default="auto")
    parser.add_argument("--output", required=True, type=Path, help="write immutable UTF-8 source text here")
    parser.add_argument("--manifest", type=Path, help="write the structured extraction receipt here")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--cache-max-age", type=int, default=0, help="seconds; 0 selects a source-kind default")
    parser.add_argument("--force", action="store_true", help="ignore a valid cache entry")
    parser.add_argument("--languages", "--language", default="ar,ar-SA,ar-EG,en")
    parser.add_argument("--no-timestamps", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--no-audio-fallback", action="store_true")
    parser.add_argument("--verified-transcript-receipt", type=Path, help="hash-bound local transcript receipt")
    parser.add_argument("--canonical-source", help="official media URL bound by the verified transcript receipt")
    parser.add_argument("--strip-embedded-timestamps", action="store_true", help="remove bracketed timestamp labels after receipt-hash verification")
    parser.add_argument("--verified-repetition-review", type=Path, help="hash-bound review for one genuine spoken 40-word repetition")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-bytes", type=int, default=25_000_000)
    args = parser.parse_args(argv)
    args.source = args.source_option or args.source
    if not args.source:
        parser.error("one source URL or path is required")
    if bool(args.verified_transcript_receipt) != bool(args.canonical_source):
        parser.error("--verified-transcript-receipt and --canonical-source must be supplied together")
    if args.verified_transcript_receipt and is_url(args.source):
        parser.error("a verified transcript receipt requires a local transcript source")
    if args.verified_repetition_review and not args.verified_transcript_receipt:
        parser.error("--verified-repetition-review requires --verified-transcript-receipt")
    args.manifest = args.manifest or args.output.with_suffix(args.output.suffix + ".extraction.json")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    started = time.perf_counter()
    kind = "audio" if args.verified_transcript_receipt else detect_kind(args.source, args.kind)
    provenance = None
    if args.verified_transcript_receipt:
        if not args.verified_transcript_receipt.is_file():
            parser_error = "verified transcript receipt does not exist"
            failure = {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "blocked", "source": args.source, "source_kind": kind, "cache_hit": False, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "error": parser_error}
            write_json(args.manifest, failure)
            print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
            return 1
        provenance = {
            "receipt_sha256": sha256_bytes(args.verified_transcript_receipt.read_bytes()),
            "local_transcript_sha256": stripped_text_sha256(Path(args.source).read_text(encoding="utf-8-sig")),
            "canonical_source": args.canonical_source,
            "strip_embedded_timestamps": args.strip_embedded_timestamps,
            "repetition_review_sha256": sha256_bytes(args.verified_repetition_review.read_bytes()) if args.verified_repetition_review and args.verified_repetition_review.is_file() else None,
        }
    key = cache_identity(args.source, kind, args.languages, not args.no_timestamps, provenance)
    cache_text = args.cache_dir / key[:2] / key / "source.txt"
    cache_manifest = args.cache_dir / key[:2] / key / "manifest.json"
    default_age = 30 * 86400 if kind in {"youtube", "audio"} else 86400 if is_url(args.source) else 3650 * 86400
    max_age = args.cache_max_age or default_age
    try:
        if not args.force and cache_text.is_file() and cache_manifest.is_file() and time.time() - cache_manifest.stat().st_mtime <= max_age:
            receipt = json.loads(cache_manifest.read_text(encoding="utf-8"))
            if receipt.get("status") == "complete" and sha256_bytes(cache_text.read_bytes()) == receipt.get("content_sha256"):
                args.output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cache_text, args.output)
                receipt = {**receipt, "cache_hit": True, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "output": str(args.output)}
                write_json(args.manifest, receipt)
                print(json.dumps(receipt, ensure_ascii=False))
                return 0

        warnings: list[str] = []
        response_headers: dict[str, str] = {}
        resolved_source = args.canonical_source or args.source
        if args.verified_transcript_receipt:
            text, metadata, warnings = extract_verified_transcript(
                Path(args.source),
                args.verified_transcript_receipt,
                args.canonical_source,
                args.strip_embedded_timestamps,
                args.verified_repetition_review,
            )
        elif kind in {"youtube", "audio"}:
            text, metadata, warnings = extract_transcript(args.source, args.languages, not args.no_timestamps, not args.no_audio_fallback)
        else:
            local_path = Path(args.source)
            content_type = ""
            if is_url(args.source):
                data, content_type, resolved_source, response_headers = fetch_public_url(args.source, args.timeout, args.max_bytes)
                if content_type == "application/pdf": kind = "pdf"
                elif content_type in {"application/epub+zip", "application/x-epub+zip"}: kind = "epub"
                elif content_type == "text/plain": kind = "text"
                with tempfile.NamedTemporaryFile(prefix="lite-visual-source-", suffix=Path(urlparse(resolved_source).path).suffix, delete=False) as handle:
                    downloaded = Path(handle.name)
                    handle.write(data)
                local_path = downloaded
            else:
                if not local_path.is_file():
                    raise ExtractionError("local source file does not exist")
                data = local_path.read_bytes()
            try:
                if kind == "article": text, metadata, warnings = extract_article(data, resolved_source, not args.no_browser)
                elif kind == "pdf": text, metadata, warnings = extract_pdf(data, not args.no_ocr)
                elif kind == "epub": text, metadata, warnings = extract_epub(data)
                elif kind == "document": text, metadata, warnings = extract_document(local_path)
                elif kind == "text":
                    try: text = normalize_text(data.decode("utf-8-sig"))
                    except UnicodeDecodeError as exc: raise ExtractionError("text source is not UTF-8") from exc
                    if word_count(text) < 10: raise ExtractionError("text source is too shallow")
                    metadata = {"engine": "direct-utf8", "checks": {"minimum_words": True}}
                else: raise ExtractionError(f"unsupported source kind: {kind}")
            finally:
                if is_url(args.source): local_path.unlink(missing_ok=True)

        encoded = text.encode("utf-8")
        receipt = {
            "schema_version": SCHEMA,
            "extractor_version": VERSION,
            "status": "complete",
            "source": args.canonical_source or args.source,
            "resolved_source": resolved_source,
            "source_kind": kind,
            "method": metadata.get("engine") or metadata.get("method"),
            "title": metadata.get("title") or None,
            "language": metadata.get("language") or None,
            "content_sha256": sha256_bytes(encoded),
            "word_count": word_count(text),
            "character_count": len(text),
            "cache_key": key,
            "cache_hit": False,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "output": str(args.output),
            "checks": metadata.get("checks") or {},
            "adapter": {key: value for key, value in metadata.items() if key not in {"checks", "text"}},
            "http_validators": response_headers,
            "warnings": warnings,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
        cache_text.parent.mkdir(parents=True, exist_ok=True)
        cache_text.write_bytes(encoded)
        write_json(cache_manifest, {**receipt, "output": str(cache_text)})
        write_json(args.manifest, receipt)
        print(json.dumps(receipt, ensure_ascii=False))
        return 0
    except Exception as exc:
        failure = {"schema_version": SCHEMA, "extractor_version": VERSION, "status": "blocked", "source": args.source, "source_kind": kind, "cache_key": key, "cache_hit": False, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "error": str(exc)}
        write_json(args.manifest, failure)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
