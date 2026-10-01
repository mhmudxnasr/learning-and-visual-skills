"""Seal a rendered pair's identity and bytes without asserting editorial or layout QA."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from receipt_attestation import (ATTESTATION_ALGORITHM, ATTESTATION_KEY_ID, HASH_FIELDS,
    RECEIPT_SCHEMA, SHA256_RE, WORKFLOW_CONTRACT, attest_receipt, canonical_receipt_bytes,
    receipt_attestation_valid, signing_key, target_sha256)
from validate_artifact import CanonicalHTML

INTEGRITY_SCHEMA = "lite-visual-integrity/v1"
INTEGRITY_CHECKS = ("source_extraction_binding", "target_identity", "artifact_hashes", "canonical_body", "render_binding")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_valid(receipt: Any, expected: dict[str, str] | None = None) -> bool:
    if not isinstance(receipt, dict):
        return False
    if receipt.get("schema_version") == RECEIPT_SCHEMA:
        return receipt_attestation_valid(receipt, expected)
    if receipt.get("schema_version") != INTEGRITY_SCHEMA or receipt.get("workflow_contract") != WORKFLOW_CONTRACT or receipt.get("status") != "passed":
        return False
    if receipt.get("verification_scope") != "integrity-only" or receipt.get("quality_checks") != "not_run":
        return False
    checks = receipt.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(INTEGRITY_CHECKS) or any(checks[key] is not True for key in INTEGRITY_CHECKS):
        return False
    if any(not SHA256_RE.fullmatch(str(receipt.get(key) or "")) for key in HASH_FIELDS):
        return False
    target = receipt.get("target")
    if not isinstance(target, dict) or any(not isinstance(target.get(key), str) or not target[key].strip() for key in ("recommendation_id", "source_url", "source_title")):
        return False
    if receipt.get("target_sha256") != target_sha256(target) or any(receipt.get(key) != value for key, value in (expected or {}).items()):
        return False
    attestation = receipt.get("attestation") or {}
    if not isinstance(attestation, dict) or attestation.get("algorithm") != ATTESTATION_ALGORITHM or attestation.get("key_id") != ATTESTATION_KEY_ID:
        return False
    try:
        signature = hmac.new(signing_key(), canonical_receipt_bytes(receipt), hashlib.sha256).hexdigest()
        return hmac.compare_digest(str(attestation.get("signature") or ""), signature)
    except (OSError, ValueError, TypeError):
        return False


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_provenance(work: Path) -> dict[str, Any]:
    source, manifest = work / "source.txt", work / "source-extraction.json"
    extraction = json.loads(manifest.read_text(encoding="utf-8"))
    if extraction.get("schema_version") != "lite-visual-source-extraction/v1" or extraction.get("status") != "complete" or extraction.get("content_sha256") != digest(source):
        raise ValueError("source extraction must be complete and match source.txt")
    # Existing filename/hash columns remain compatible with durable v4 jobs.
    # These machine-written records make no reviewed-scope or claim assertions.
    write_json(work / "source-scope.json", {"schema_version": "lite-visual-source-provenance/v1", "authoring_mode": "direct", "source": {"sha256": digest(source), "word_count": extraction["word_count"], "kind": extraction.get("source_kind") or "article"}, "spans": []})
    write_json(work / "coverage-ledger.json", {"schema_version": "lite-visual-authoring-provenance/v1", "authoring_mode": "direct", "source_sha256": digest(source), "claims": [], "editorial_review": "not_required"})
    return extraction


def finish_pair(work: Path, run) -> dict[str, Any]:
    html, pdf = work / "companion.html", work / "companion.pdf"
    target = json.loads((work / "work-item.json").read_text(encoding="utf-8"))
    target = {key: str(target.get(key) or "").strip() for key in ("recommendation_id", "source_url", "source_title", "chapter_key") if key != "chapter_key" or target.get(key)}
    if any(not target.get(key) for key in ("recommendation_id", "source_url", "source_title")):
        raise ValueError("work-item.json must identify the exact source target")
    extraction = prepare_provenance(work)
    parser = CanonicalHTML()
    parser.feed(html.read_text(encoding="utf-8"))
    if parser.canonical_count != 1 or not parser.authored_text:
        raise ValueError("HTML must contain one non-empty canonical article")
    names = {"source_sha256": "source.txt", "source_extraction_sha256": "source-extraction.json", "work_item_sha256": "work-item.json",
        "source_scope_sha256": "source-scope.json", "coverage_ledger_sha256": "coverage-ledger.json", "html_sha256": "companion.html"}
    before = {key: digest(work / name) for key, name in names.items()}
    render = work / "render-receipt.json"
    run(["node", str(Path(__file__).with_name("render_pdf.mjs")), str(html), str(pdf), str(render)], "canonical PDF render")
    render_data = json.loads(render.read_text(encoding="utf-8"))
    if render_data.get("schema_version") != "lite-visual-render/v1" or render_data.get("html_sha256") != digest(html) or render_data.get("pdf_sha256") != digest(pdf):
        raise ValueError("rendered pair changed after rendering")
    if pdf.read_bytes()[:5] != b"%PDF-":
        raise ValueError("render did not produce a PDF")
    hashes = {key: digest(work / name) for key, name in {**names, "pdf_sha256": "companion.pdf"}.items()}
    if any(hashes[key] != value for key, value in before.items()):
        raise ValueError("workflow inputs changed while rendering")
    if hashes["source_sha256"] != extraction["content_sha256"] or hashes["html_sha256"] != render_data["html_sha256"] or hashes["pdf_sha256"] != render_data["pdf_sha256"]:
        raise ValueError("workflow inputs changed while rendering")
    current_target = json.loads((work / "work-item.json").read_text(encoding="utf-8"))
    if any(str(current_target.get(key) or "").strip() != value for key, value in target.items()):
        raise ValueError("source target changed while rendering")
    receipt = {"schema_version": INTEGRITY_SCHEMA, "workflow_contract": WORKFLOW_CONTRACT, "status": "passed",
        "verification_scope": "integrity-only", "quality_checks": "not_run", **hashes,
        "target": target, "target_sha256": target_sha256(target), "checks": dict.fromkeys(INTEGRITY_CHECKS, True),
        "stats": {"render_ms": render_data["elapsed_ms"]}}
    attest_receipt(receipt)
    write_json(work / "validation-receipt.json", receipt)
    return receipt
