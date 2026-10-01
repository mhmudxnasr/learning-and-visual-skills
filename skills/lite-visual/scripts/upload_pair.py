#!/usr/bin/env python3
"""Atomically publish one validated Lite Visual HTML/PDF pair.

Both files travel in one request. The Worker verifies the validator receipt,
stores both objects, commits both D1 records together, and exposes neither file
when any part fails. Repeating the same pair and hashes safely reuses it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_WORKER = "https://recommendations-worker.mhmudnasr30.workers.dev"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from receipt_attestation import RECEIPT_SCHEMA, WORKFLOW_CONTRACT
from pair_integrity import INTEGRITY_SCHEMA, receipt_valid as receipt_attestation_valid
PAIR_RE = re.compile(r"^lv-[A-Za-z0-9._-]+$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PAIR_HASH_FIELDS = (
    "source_sha256",
    "source_scope_sha256",
    "coverage_ledger_sha256",
    "html_sha256",
    "pdf_sha256",
)


class UploadError(RuntimeError):
    def __init__(self, message: str, *, ambiguous: bool = False):
        super().__init__(message)
        self.ambiguous = ambiguous


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_pair_id(recommendation_id: str, receipt: dict[str, Any], chapter_key: str = "") -> str:
    parts = [str(receipt[key]) for key in PAIR_HASH_FIELDS]
    if chapter_key:
        parts.append(f"chapter:{chapter_key}")
    fingerprint = hashlib.sha256("\n".join(parts).encode()).hexdigest()[:20]
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "-", recommendation_id)
    return f"lv-{safe_id}-{fingerprint}"


def normalized_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


def request_json(request: urllib.request.Request) -> tuple[int, dict[str, Any]]:
    if not request.has_header("User-agent"):
        request.add_header("User-Agent", "Mozilla/5.0 (compatible; HermesCron/1.0)")
    if not request.has_header("X-agent-name"):
        request.add_header("x-agent-name", "lite-visual")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": raw or str(exc)}
        raise UploadError(f"Worker rejected atomic pair (HTTP {exc.code}): {payload}", ambiguous=exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UploadError(f"Worker request failed: {exc}", ambiguous=True) from exc


def validate_inputs(args: argparse.Namespace) -> dict[str, Any]:
    for path, label in ((args.html, "--html"), (args.pdf, "--pdf"), (args.receipt, "--receipt")):
        if not path.is_file() or path.stat().st_size == 0:
            raise UploadError(f"{label} must point to a non-empty file")
    if args.html.suffix.lower() not in {".html", ".htm"}:
        raise UploadError("--html must be an HTML file")
    if args.pdf.suffix.lower() != ".pdf" or args.pdf.read_bytes()[:5] != b"%PDF-":
        raise UploadError("--pdf must be a valid PDF file")
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UploadError(f"--receipt must be valid UTF-8 JSON: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") not in {RECEIPT_SCHEMA, INTEGRITY_SCHEMA} or receipt.get("workflow_contract") != WORKFLOW_CONTRACT or receipt.get("status") != "passed":
        raise UploadError("--receipt must be a passing integrity receipt or historical v6 validation receipt")
    if not receipt_attestation_valid(receipt):
        raise UploadError("--receipt attestation is missing or invalid")
    target = receipt.get("target") or {}
    if target.get("recommendation_id") != args.recommendation_id or normalized_url(str(target.get("source_url") or "")) != normalized_url(args.source_url) or str(target.get("source_title") or "").strip() != args.source_title.strip() or str(target.get("chapter_key") or "") != str(args.chapter_key or ""):
        raise UploadError("--receipt target identity does not match publication arguments")
    if any(not SHA256_RE.fullmatch(str(receipt.get(key) or "")) for key in PAIR_HASH_FIELDS):
        raise UploadError("--receipt must contain every full lowercase content SHA-256")
    for key, path in (("html_sha256", args.html), ("pdf_sha256", args.pdf)):
        if receipt.get(key) != file_hash(path):
            raise UploadError(f"--receipt {key} does not match {path.name}")
    if not SHA256_RE.fullmatch(str(receipt.get("source_sha256") or "")):
        raise UploadError("--receipt source_sha256 must be a full lowercase SHA-256")
    if args.pair_id and not PAIR_RE.fullmatch(args.pair_id):
        raise UploadError("--pair-id must start with lv- and contain only letters, digits, dots, underscores, or hyphens")
    if args.supersedes_pair_id and not PAIR_RE.fullmatch(args.supersedes_pair_id):
        raise UploadError("--supersedes-pair-id must be a valid lv-* pair ID")
    return receipt


def multipart(fields: dict[str, str], files: dict[str, tuple[Path, str]]) -> tuple[bytes, str]:
    boundary = f"----litevisual{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"), b"\r\n",
        ])
    for name, (path, content_type) in files.items():
        filename = path.name.replace('"', "")
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(), b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def preflight_target(args: argparse.Namespace) -> None:
    _, payload = request_json(urllib.request.Request(f"{args.worker.rstrip('/')}/capture/{urllib.parse.quote(args.recommendation_id)}/record", headers={"Accept": "application/json"}))
    item = payload.get("item")
    if not isinstance(item, dict):
        raise UploadError("target preflight record has no item")
    if item.get("id") != args.recommendation_id:
        raise UploadError("target preflight record identity does not match --recommendation-id")
    if args.source_url and item.get("video_url") and normalized_url(str(item["video_url"])) != normalized_url(args.source_url):
        raise UploadError("target preflight source URL does not match --recommendation-id")
    if str(item.get("video_title") or "").strip() != args.source_title.strip():
        raise UploadError("target preflight source title does not match --recommendation-id")


def verify_pair(args: argparse.Namespace, pair_id: str, html_id: str, pdf_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    if args.corpus_id:
        _, payload = request_json(urllib.request.Request(f"{args.worker.rstrip('/')}/artifacts/corpora/{urllib.parse.quote(args.corpus_id)}/pairs/{urllib.parse.quote(pair_id)}", headers={"Accept": "application/json"}))
        pair = payload.get("pair") or {}
        if pair.get("state") != "staged" or pair.get("recommendation_id") != args.recommendation_id or pair.get("job_id") != args.job_id or pair.get("workflow_run_id") != args.workflow_run_id or pair.get("supersedes_pair_id") != args.supersedes_pair_id or pair.get("r2_verified") is not True:
            raise UploadError("staged corpus readback does not match the uploaded pair/job")
        if pair.get("html_artifact_id") != html_id or pair.get("pdf_artifact_id") != pdf_id:
            raise UploadError("staged corpus readback does not link the uploaded HTML/PDF artifact IDs")
        expected = {
            "target_sha256": receipt.get("target_sha256"),
            "work_item_sha256": receipt.get("work_item_sha256"),
            "source_extraction_sha256": receipt.get("source_extraction_sha256"),
            "source_sha256": receipt.get("source_sha256"),
            "source_scope_sha256": receipt.get("source_scope_sha256"),
            "coverage_ledger_sha256": receipt.get("coverage_ledger_sha256"),
            "html_sha256": receipt.get("html_sha256"),
            "pdf_sha256": receipt.get("pdf_sha256"),
            "receipt_sha256": file_hash(args.receipt),
        }
        if any(pair.get(key) != value for key, value in expected.items()):
            raise UploadError("staged corpus readback hashes do not match the uploaded receipt")
        return {"corpus": f"/artifacts/corpora/{args.corpus_id}", "status": "staged", "pair_id": pair_id}
    _, payload = request_json(urllib.request.Request(f"{args.worker.rstrip('/')}/capture/{urllib.parse.quote(args.recommendation_id)}/record", headers={"Accept": "application/json"}))
    companion = payload.get("companion") or {}
    if companion.get("status") != "ready" or companion.get("pair_id") != pair_id:
        raise UploadError("source record did not expose the new pair as ready")
    if (companion.get("primary") or {}).get("id") != html_id or (companion.get("secondary") or {}).get("id") != pdf_id:
        raise UploadError("source record does not link the uploaded HTML/PDF artifact IDs")
    return {"source_record": f"/capture/{args.recommendation_id}/record", "status": "ready", "pair_id": pair_id}


def recover_publication(args: argparse.Namespace, pair_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    """Read back one ambiguous POST; never issue another upload automatically."""
    base = args.worker.rstrip('/')
    path = (f"/artifacts/corpora/{urllib.parse.quote(args.corpus_id)}/pairs/{urllib.parse.quote(pair_id)}"
            if args.corpus_id else f"/artifacts/pairs/{urllib.parse.quote(pair_id)}/record")
    _, recovered = request_json(urllib.request.Request(base + path, headers={"Accept": "application/json"}))
    pair = recovered.get("pair") or {}
    html_id = str(pair.get("html_artifact_id") or "")
    pdf_id = str(pair.get("pdf_artifact_id") or "")
    if not html_id or not pdf_id or pair.get("recommendation_id") != args.recommendation_id:
        raise UploadError("canonical pair identity is missing or mismatched")
    if not args.corpus_id:
        if pair.get("id") != pair_id or pair.get("complete") is not True or pair.get("retired") or pair.get("corpus_id"):
            raise UploadError("canonical standalone pair is incomplete, retired, or corpus-owned")
        for role, artifact_id in (("html", html_id), ("pdf", pdf_id)):
            _, record = request_json(urllib.request.Request(
                f"{base}/artifacts/{urllib.parse.quote(artifact_id)}/record", headers={"Accept": "application/json"}))
            artifact = record.get("artifact") or {}
            metadata = artifact.get("metadata") or {}
            if (artifact.get("id") != artifact_id or metadata.get("pair_id") != pair_id
                    or metadata.get("recommendation_id") != args.recommendation_id
                    or metadata.get("role") != role or metadata.get("publication_state") != "ready"
                    or str(metadata.get("chapter_key") or "") != str(args.chapter_key or "")
                    or metadata.get("html_sha256") != receipt.get("html_sha256")
                    or metadata.get("pdf_sha256") != receipt.get("pdf_sha256")
                    or metadata.get("validation_receipt_sha256") != file_hash(args.receipt)
                    or any((metadata.get("validation_receipt") or {}).get(key) != receipt.get(key) for key in PAIR_HASH_FIELDS)):
                raise UploadError("canonical artifact identity or hashes do not match the uploaded receipt")
    verification = verify_pair(args, pair_id, html_id, pdf_id, receipt)
    return {"ok": True, "status_code": 200, "status": "staged" if args.corpus_id else "ready",
            "reused": True, "recovered_after_ambiguous_write": True, "corpus_id": args.corpus_id,
            "pair_id": pair_id, "html_artifact_id": html_id, "pdf_artifact_id": pdf_id,
            "validation_status": "passed", "verification": verification}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path, help="passing receipt emitted by validate_artifact.py")
    parser.add_argument("--recommendation-id", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-title", required=True)
    parser.add_argument("--pair-id")
    parser.add_argument("--revision")
    parser.add_argument("--supersedes-pair-id")
    parser.add_argument("--corpus-id")
    parser.add_argument("--job-id")
    parser.add_argument("--workflow-run-id")
    parser.add_argument("--worker-identity")
    parser.add_argument("--chapter-key")
    parser.add_argument("--chapter-title")
    parser.add_argument("--chapter-number", type=int)
    parser.add_argument("--worker", default=DEFAULT_WORKER)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        receipt = validate_inputs(args)
        preflight_target(args)
        pair_id = args.pair_id or default_pair_id(args.recommendation_id, receipt, args.chapter_key or "")
        if args.supersedes_pair_id == pair_id:
            raise UploadError("--supersedes-pair-id must differ from the new pair ID")
        metadata: dict[str, Any] = {
            "pair_id": pair_id,
            "recommendation_id": args.recommendation_id,
            "source_url": args.source_url or None,
            "source_title": args.source_title,
            "source_checksum": receipt["source_sha256"],
            "generator": "lite-visual",
            "workflow_contract": WORKFLOW_CONTRACT,
            "asset_policy": "code-only",
            "recommended_start": "html",
        }
        if args.corpus_id:
            if not args.job_id or not args.workflow_run_id or not args.worker_identity:
                raise UploadError("--corpus-id requires --job-id, --workflow-run-id, and --worker-identity")
            metadata["corpus_id"] = args.corpus_id
            metadata["job_id"] = args.job_id
            metadata["workflow_run_id"] = args.workflow_run_id
            metadata["worker_identity"] = args.worker_identity
        for key in ("revision", "supersedes_pair_id", "chapter_key", "chapter_title", "chapter_number"):
            value = getattr(args, key)
            if value is not None:
                metadata[key] = value
        body, content_type = multipart(
            {"metadata": json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), "validation_receipt": args.receipt.read_text(encoding="utf-8")},
            {"html": (args.html, "text/html; charset=utf-8"), "pdf": (args.pdf, "application/pdf")},
        )
        try:
            status, response = request_json(urllib.request.Request(f"{args.worker.rstrip('/')}/artifacts/pairs", data=body, method="POST", headers={"Content-Type": content_type, "Accept": "application/json"}))
        except UploadError as exc:
            if not exc.ambiguous:
                raise
            try:
                result = recover_publication(args, pair_id, receipt)
            except UploadError as read_error:
                emit({"ok": False, "error": str(exc), "readback_error": str(read_error),
                      "mutation_outcome_unknown": True, "retry": False, "pair_id": pair_id})
                return 1
            emit(result)
            return 0
        html_id = str((response.get("html") or {}).get("id") or "")
        pdf_id = str((response.get("pdf") or {}).get("id") or "")
        expected_status = "staged" if args.corpus_id else "ready"
        if not html_id or not pdf_id or response.get("status") != expected_status:
            raise UploadError(f"atomic publication returned an incomplete response: {response}")
        verification = verify_pair(args, pair_id, html_id, pdf_id, receipt)
        emit({"ok": True, "status_code": status, "status": expected_status, "reused": bool(response.get("reused")), "corpus_id": args.corpus_id, "pair_id": pair_id, "html_artifact_id": html_id, "pdf_artifact_id": pdf_id, "validation_status": "passed", "verification": verification})
        return 0
    except (UploadError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
