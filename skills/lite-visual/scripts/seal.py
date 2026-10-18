"""Seal a built companion for the Worker: hash the files, bind the target, sign the receipt.

The Worker accepts a companion only with a signed `lite-visual-html-integrity/v1`
receipt. The receipt proves which bytes belong to which source; it says nothing
about teaching quality (`quality_checks=not_run`). Nothing here is for Hermes to
edit or fill by hand.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any

INTEGRITY_SCHEMA = "lite-visual-html-integrity/v1"
# The Worker and durable jobs still name the v4 workflow contract.
WORKFLOW_CONTRACT = "lite-visual-linear/v4"
ATTESTATION_ALGORITHM = "hmac-sha256"
ATTESTATION_KEY_ID = "lite-visual-v6-2026-08-28-r2"
SIGNING_KEY_FILE = Path.home() / ".hermes" / "secrets" / "lite-visual-receipt-signing-key"
CHECKS = ("source_extraction_binding", "target_identity", "artifact_hashes", "canonical_body")
FILES = {"source_sha256": "source.txt", "source_extraction_sha256": "source-extraction.json", "work_item_sha256": "work-item.json",
    "source_scope_sha256": "source-scope.json", "coverage_ledger_sha256": "coverage-ledger.json", "html_sha256": "companion.html"}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
CANONICAL = re.compile(r"<article\b[^>]*\bdata-canonical-content=\"true\"")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    # Must match the Worker's canonical form: sorted keys, no spaces, UTF-8.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def target_sha256(target: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(target)).hexdigest()


def signing_key() -> bytes:
    value = os.environ.get("LITE_VISUAL_RECEIPT_SIGNING_KEY", "").strip()
    if not value and SIGNING_KEY_FILE.is_file():
        value = SIGNING_KEY_FILE.read_text(encoding="utf-8").strip()
    if len(value.encode("utf-8")) < 32:
        raise ValueError("Lite Visual receipt signing key is missing or shorter than 32 bytes")
    return value.encode("utf-8")


def signature(receipt: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "attestation"}
    return hmac.new(signing_key(), canonical_json_bytes(unsigned), hashlib.sha256).hexdigest()


def receipt_valid(receipt: Any, expected: dict[str, str] | None = None) -> bool:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != INTEGRITY_SCHEMA or receipt.get("workflow_contract") != WORKFLOW_CONTRACT:
        return False
    if receipt.get("status") != "passed" or receipt.get("verification_scope") != "integrity-only" or receipt.get("quality_checks") != "not_run":
        return False
    checks = receipt.get("checks")
    # `is True`, not ==: the Worker rejects 1 where it expects true.
    if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(checks[key] is not True for key in CHECKS) or "pdf_sha256" in receipt:
        return False
    if any(not SHA256_RE.fullmatch(str(receipt.get(key) or "")) for key in (*FILES, "target_sha256")):
        return False
    target = receipt.get("target")
    if not isinstance(target, dict) or any(not str(target.get(key) or "").strip() for key in ("recommendation_id", "source_url", "source_title")):
        return False
    if receipt.get("target_sha256") != target_sha256(target) or any(receipt.get(key) != value for key, value in (expected or {}).items()):
        return False
    attestation = receipt.get("attestation") or {}
    if attestation.get("algorithm") != ATTESTATION_ALGORITHM or attestation.get("key_id") != ATTESTATION_KEY_ID:
        return False
    try:
        return hmac.compare_digest(str(attestation.get("signature") or ""), signature(receipt))
    except ValueError:
        return False


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare_provenance(work: Path) -> dict[str, Any]:
    """Check the extraction matches source.txt and write the two placeholder records the Worker still hashes."""
    source, manifest = work / "source.txt", work / "source-extraction.json"
    extraction = json.loads(manifest.read_text(encoding="utf-8"))
    if extraction.get("schema_version") != "lite-visual-source-extraction/v1" or extraction.get("status") != "complete" or extraction.get("content_sha256") != digest(source):
        raise ValueError("source extraction must be complete and match source.txt")
    write_json(work / "source-scope.json", {"schema_version": "lite-visual-source-provenance/v1", "authoring_mode": "direct",
        "source": {"sha256": digest(source), "word_count": extraction["word_count"], "kind": extraction.get("source_kind") or "article"}, "spans": []})
    write_json(work / "coverage-ledger.json", {"schema_version": "lite-visual-authoring-provenance/v1", "authoring_mode": "direct",
        "source_sha256": digest(source), "claims": [], "editorial_review": "not_required"})
    return extraction


def current_receipt(work: Path) -> dict[str, Any] | None:
    """The existing receipt when every sealed file is unchanged, so an unchanged companion is never resealed."""
    path = work / "validation-receipt.json"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        expected = {key: digest(work / name) for key, name in FILES.items()}
    except (OSError, ValueError):
        return None
    return receipt if receipt_valid(receipt, expected) else None


def seal(work: Path) -> dict[str, Any]:
    stored = json.loads((work / "work-item.json").read_text(encoding="utf-8"))
    target = {key: str(stored.get(key) or "").strip() for key in ("recommendation_id", "source_url", "source_title", "chapter_key") if key != "chapter_key" or stored.get(key)}
    if any(not target.get(key) for key in ("recommendation_id", "source_url", "source_title")):
        raise ValueError("work-item.json must identify the exact source target")
    extraction = prepare_provenance(work)
    if len(CANONICAL.findall((work / "companion.html").read_text(encoding="utf-8"))) != 1:
        raise ValueError("companion.html must come from build_companion.py (one canonical article)")
    hashes = {key: digest(work / name) for key, name in FILES.items()}
    if hashes["source_sha256"] != extraction["content_sha256"]:
        raise ValueError("source.txt changed while sealing")
    receipt = {"schema_version": INTEGRITY_SCHEMA, "workflow_contract": WORKFLOW_CONTRACT, "status": "passed",
        "verification_scope": "integrity-only", "quality_checks": "not_run", **hashes,
        "target": target, "target_sha256": target_sha256(target), "checks": dict.fromkeys(CHECKS, True)}
    receipt["attestation"] = {"algorithm": ATTESTATION_ALGORITHM, "key_id": ATTESTATION_KEY_ID, "signature": signature(receipt)}
    write_json(work / "validation-receipt.json", receipt)
    return receipt
