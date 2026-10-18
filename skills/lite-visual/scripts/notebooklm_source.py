#!/usr/bin/env python3
"""Acquire a source's full text through NotebookLM, within the free plan.

Hermes never transcribes audio or OCRs scans locally. YouTube, audio, and PDF
sources go to NotebookLM, which fetches public URLs on Google's side and reads
uploaded files once. The free plan allows about 50 chat questions per rolling
24 hours and 50 sources per notebook, so this adapter:

- reads `source fulltext`, which costs no chat question;
- reuses a source already indexed in any notebook instead of adding it again;
- spends chat questions only on scanned PDFs (they index as page images),
  asking for a word-for-word transcription of 10-page chunks;
- caps extraction at EXTRACTION_CHATS questions per 24 hours, leaving the rest
  for Mahmood's own questions, and caches every chunk so a paused scan resumes
  where it stopped instead of paying again;
- deletes every source it added and sweeps leftovers from interrupted runs.

When NotebookLM cannot produce text, the source is skipped.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CLI = str(Path.home() / ".local/bin/notebooklm")
NOTEBOOK_TITLE = "Compass transcripts"
CHAT_LEDGER = Path.home() / ".hermes/skills/notebooklm/data/chat-usage.jsonl"
CHUNK_CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "learning-compass" / "notebooklm-chunks"
DAILY_CHATS = 50
EXTRACTION_CHATS = 40
WAIT_SECONDS = 1800
PAGES_PER_ASK = 10
MAX_PDF_BYTES = 200_000_000
LEFTOVER_AGE = timedelta(hours=3)
WORD_RE = re.compile(r"[\w؀-ۿ]+", re.UNICODE)
# Scanned pages index as image links plus image ids instead of text.
IMAGE_LINE_RE = re.compile(r"^(?:https://lh3\.googleusercontent\.com/\S+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
CITATION_RE = re.compile(r"\s?\[\d+(?:\s?[,\-–]\s?\d+)*\]")
# A verbatim transcription never opens with summary/introduction meta-language; such an opening
# means NotebookLM answered with a summary, which must never become source.txt.
SUMMARY_OPEN_RE = re.compile(
    r"^(?:here(?:'s| is)\s+(?:a\s+|the\s+)?(?:summary|overview|recap)|summary\s*:|overview\s*:"
    r"|this\s+(?:document|source|pdf|file|text)\s+(?:discusses|covers|describes|summarizes|presents)"
    r"|إليك\s+ملخص|ملخص\s+(?:لهذا|للمستند|للنص)|هذا\s+(?:المستند|الملف|المصدر)\s+(?:يتناول|يلخص|يتحدث)\b)",
    re.I,
)
RATE_LIMIT_RE = re.compile(r"rate.?limit|429|quota|too many|resource.?exhausted", re.I)
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
TRANSCRIBE_PROMPT = (
    "You are a verbatim transcription engine, never a summarizer. Transcribe this source word for word, "
    "exactly as written, from the very first word to the very last. "
    "Strictly forbidden: summarizing, condensing, paraphrasing, outlining, omitting any page, section, sentence, "
    "or word, reordering or merging sentences, commentary, analysis, opinion, translation, citation markers, and "
    "meta-language such as 'this document discusses/covers/describes' or 'the author argues'. "
    "Reproduce every sentence exactly once, in the original order and language, keeping headings, line breaks, "
    "repetitions, incomplete sentences, and spelling exactly as they are. "
    "Output only the transcription itself."
)


class NotebookLMUnavailable(RuntimeError):
    """NotebookLM produced no usable text; the caller skips the source."""


class NotebookLMBudgetPaused(RuntimeError):
    """The free chat budget is spent; rerun the same extraction after `resume_at`."""


def _cli(args: list[str], timeout: int) -> tuple[int, dict[str, Any]]:
    for delay in (30, 90, 240, None):
        try:
            completed = subprocess.run([CLI, "--quiet", *args, "--json"], text=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise NotebookLMUnavailable(f"notebooklm {args[0]} timed out after {timeout}s") from exc
        try:
            payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        if completed.returncode != 0 and RATE_LIMIT_RE.search(detail) and delay:
            time.sleep(delay)  # The free tier throttles bursts; back off instead of failing the source.
            continue
        if completed.returncode != 0 and not payload:
            raise NotebookLMUnavailable(f"notebooklm {' '.join(args[:2])} failed: {detail}")
        return completed.returncode, payload
    raise AssertionError("unreachable")


# --- chat budget ---------------------------------------------------------

def _chat_times() -> list[datetime]:
    try:
        lines = CHAT_LEDGER.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    times = [datetime.fromisoformat(json.loads(line)["at"]) for line in lines if line.strip()]
    return sorted(t for t in times if t > since)


def chat_budget() -> dict[str, Any]:
    """Questions used in the rolling 24 hours, shared by extraction and Mahmood's own asks."""
    times = _chat_times()
    return {"used_24h": len(times), "daily_limit": DAILY_CHATS, "extraction_limit": EXTRACTION_CHATS,
            "next_free_at": (times[0] + timedelta(hours=24)).isoformat() if times else None}


def record_chat(purpose: str) -> None:
    times = _chat_times()
    CHAT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    # Rewrite to keep only the rolling window, then append this question.
    rows = [json.dumps({"at": t.isoformat()}) for t in times]
    rows.append(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "purpose": purpose}))
    CHAT_LEDGER.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _reserve_extraction_chat() -> None:
    budget = chat_budget()
    if budget["used_24h"] >= EXTRACTION_CHATS:
        raise NotebookLMBudgetPaused(f"NotebookLM free chat budget for extraction is used ({budget['used_24h']}/{EXTRACTION_CHATS} in 24h); resume after {budget['next_free_at']}")
    record_chat("extraction")


# --- notebook and sources ------------------------------------------------

def _notebooks() -> list[dict[str, Any]]:
    return _cli(["list"], 60)[1].get("notebooks", [])


def _sources(notebook_id: str) -> list[dict[str, Any]]:
    return _cli(["source", "list", "-n", notebook_id], 60)[1].get("sources", [])


def _notebook_id(notebooks: list[dict[str, Any]]) -> str:
    for notebook in notebooks:
        if notebook.get("title") == NOTEBOOK_TITLE:
            notebook_id = notebook["id"]
            cutoff = datetime.now(timezone.utc) - LEFTOVER_AGE
            for source in _sources(notebook_id):
                created = source.get("created_at")
                if created and datetime.fromisoformat(created) < cutoff:
                    _remove(notebook_id, source["id"])  # leftover from an interrupted run
            return notebook_id
    _, created = _cli(["create", NOTEBOOK_TITLE], 60)
    notebook_id = created.get("id") or (created.get("notebook") or {}).get("id")
    if not notebook_id:
        raise NotebookLMUnavailable("notebooklm did not return the new notebook id")
    return notebook_id


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in YOUTUBE_HOSTS:
        match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})", url)
        if match:
            return "youtube:" + match.group(1)
    return url.rstrip("/")


def _existing_source(notebooks: list[dict[str, Any]], url: str) -> tuple[str, str] | None:
    """Find the URL already indexed in Mahmood's notebooks so it is not added again."""
    wanted = _canonical_url(url)
    for notebook in notebooks:
        if notebook.get("title") == NOTEBOOK_TITLE or not notebook.get("is_owner", True):
            continue
        for source in _sources(notebook["id"]):
            if source.get("url") and source.get("status") == "ready" and _canonical_url(source["url"]) == wanted:
                return notebook["id"], source["id"]
    return None


def _add(notebook_id: str, source: str) -> str:
    add = ["source", "add", "-n", notebook_id, source, "--request-timeout", "600"]
    if is_youtube(source):
        add += ["--type", "youtube"]
    _, added = _cli(add, 660)
    source_id = (added.get("source") or {}).get("id")
    if not source_id:
        raise NotebookLMUnavailable(f"notebooklm did not accept the source: {json.dumps(added)[:300]}")
    code, waited = _cli(["source", "wait", "-n", notebook_id, source_id, "--timeout", str(WAIT_SECONDS), "--interval", "5"], WAIT_SECONDS + 60)
    if code != 0 or waited.get("status") != "ready":
        _remove(notebook_id, source_id)
        raise NotebookLMUnavailable(f"NotebookLM could not process the source (status {waited.get('status') or code})")
    return source_id


def _remove(notebook_id: str, source_id: str) -> None:
    subprocess.run([CLI, "--quiet", "source", "delete", "-n", notebook_id, source_id, "-y"], capture_output=True, timeout=120)


def _words(text: str) -> int:
    return len(WORD_RE.findall(text))


def is_youtube(source: str) -> bool:
    return (urlparse(source).hostname or "").lower() in YOUTUBE_HOSTS


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _is_pdf(source: str) -> bool:
    return urlparse(source).path.lower().endswith(".pdf") if _is_url(source) else Path(source).suffix.lower() == ".pdf"


# --- scanned PDFs ----------------------------------------------------------

def _pdf_bytes(source: str) -> bytes:
    if not _is_url(source):
        return Path(source).read_bytes()
    with urlopen(Request(source, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as response:
        data = response.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise NotebookLMUnavailable("scanned PDF exceeds 200 MB")
    return data


def _transcribe(notebook_id: str, source_id: str) -> str:
    _reserve_extraction_chat()
    # --new only clears this dedicated notebook's chat, keeping each transcription independent.
    _, answer = _cli(["ask", "-n", notebook_id, "-s", source_id, "--new", "--request-timeout", "900", TRANSCRIBE_PROMPT], 960)
    text = CITATION_RE.sub("", str(answer.get("answer") or "")).strip()
    if SUMMARY_OPEN_RE.match(text[:300]):
        raise NotebookLMUnavailable("NotebookLM returned a summary instead of a verbatim transcription; source skipped")
    return text


def _transcribe_scanned_pdf(notebook_id: str, source: str) -> tuple[str, int]:
    import fitz  # PyMuPDF only splits pages here; it never reads text from images.

    data = _pdf_bytes(source)
    cache = CHUNK_CACHE / hashlib.sha256(data).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    document = fitz.open(stream=data, filetype="pdf")
    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="compass-nblm-") as directory:
        for start in range(0, len(document), PAGES_PER_ASK):
            end = min(start + PAGES_PER_ASK, len(document)) - 1
            label = f"pages-{start + 1}-{end + 1}"
            cached = cache / f"{label}.txt"
            if cached.is_file():
                text = cached.read_text(encoding="utf-8")
            else:
                chunk_path = Path(directory) / f"{label}.pdf"
                chunk = fitz.open()
                chunk.insert_pdf(document, from_page=start, to_page=end)
                chunk.save(chunk_path)
                source_id = _add(notebook_id, str(chunk_path))
                try:
                    text = _transcribe(notebook_id, source_id)
                finally:
                    _remove(notebook_id, source_id)
                cached.write_text(text, encoding="utf-8")
            parts.append(f"[PAGES {start + 1}-{end + 1}]\n{text}")
    return "\n\n".join(parts), len(document)


# --- entry point -----------------------------------------------------------

def fulltext(source: str, pdf: bool | None = None) -> tuple[str, dict[str, Any]]:
    """Return NotebookLM's full text for a public URL or local file."""
    if not _is_url(source) and not Path(source).is_file():
        raise NotebookLMUnavailable("local source file does not exist")
    notebooks = _notebooks()
    notebook_id = _notebook_id(notebooks)
    existing = _existing_source(notebooks, source) if _is_url(source) else None
    if existing:
        _, payload = _cli(["source", "fulltext", "-n", existing[0], existing[1]], 300)
    else:
        source_id = _add(notebook_id, source)
        try:
            _, payload = _cli(["source", "fulltext", "-n", notebook_id, source_id], 300)
        finally:
            _remove(notebook_id, source_id)
    text = "\n".join(line for line in str(payload.get("content") or "").splitlines() if not IMAGE_LINE_RE.match(line.strip())).strip()
    method, pages = "notebooklm-fulltext", None
    if _words(text) < 20 and (_is_pdf(source) if pdf is None else pdf):
        text, pages = _transcribe_scanned_pdf(notebook_id, source)
        method = "notebooklm-transcription"
    if _words(text) < 20:
        raise NotebookLMUnavailable(f"NotebookLM returned no usable text ({_words(text)} words)")
    return text, {
        "engine": "notebooklm",
        "notebooklm_method": method,
        "reused_notebook_source": bool(existing),
        "title": payload.get("title") or None,
        "notebooklm_source_kind": payload.get("kind"),
        "page_count": pages,
        "character_count": len(text),
        "chat_budget": chat_budget(),
        "checks": {"minimum_words": True, "notebooklm_indexed": True},
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["--budget"]:
        print(json.dumps(chat_budget()))
        raise SystemExit(0)
    if len(sys.argv) != 2:
        raise SystemExit("usage: notebooklm_source.py <url-or-file> | --budget")
    try:
        text, meta = fulltext(sys.argv[1])
    except (NotebookLMUnavailable, NotebookLMBudgetPaused) as exc:
        print(json.dumps({"status": "paused" if isinstance(exc, NotebookLMBudgetPaused) else "skipped", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
    sys.stdout.write(text + "\n")
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
