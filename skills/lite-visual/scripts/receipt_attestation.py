#!/usr/bin/env python3
"""Canonical Lite Visual v6 receipt attestation shared by every local gate."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Any


RECEIPT_SCHEMA = "lite-visual-validation/v6"
WORKFLOW_CONTRACT = "lite-visual-linear/v4"
ATTESTATION_ALGORITHM = "hmac-sha256"
ATTESTATION_KEY_ID = "lite-visual-v6-2026-08-28-r2"
DEFAULT_SIGNING_KEY_FILE = Path.home() / ".hermes" / "secrets" / "lite-visual-receipt-signing-key"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
HASH_FIELDS = ("source_sha256", "source_scope_sha256", "coverage_ledger_sha256", "html_sha256", "pdf_sha256", "work_item_sha256", "source_extraction_sha256", "target_sha256")
REQUIRED_CHECKS = (
    "source_coverage",
    "claim_traceability",
    "exact_source_html",
    "exact_source_pdf",
    "canonical_html",
    "code_only",
    "rtl",
    "accessibility",
    "responsive",
    "print_a4",
    "pdf_parity",
)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        if any(not isinstance(key, str) or not key or not all(0x20 <= ord(character) <= 0x7e for character in key) for key in value):
            raise ValueError("receipt object keys must be non-empty printable ASCII")
        return {key: _canonical_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("receipt integer exceeds the cross-runtime safe range")
        return value
    if isinstance(value, float):
        if value.is_integer() and abs(value) <= 9_007_199_254_740_991:
            return int(value)
        raise ValueError("receipt numbers must be safe integers")
    raise ValueError(f"receipt contains unsupported value type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(_canonical_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return canonical_json_bytes({key: value for key, value in receipt.items() if key != "attestation"})


def signing_key() -> bytes:
    value = os.environ.get("LITE_VISUAL_RECEIPT_SIGNING_KEY", "").strip()
    if not value and DEFAULT_SIGNING_KEY_FILE.is_file():
        value = DEFAULT_SIGNING_KEY_FILE.read_text(encoding="utf-8").strip()
    if len(value.encode("utf-8")) < 32:
        raise ValueError("Lite Visual receipt signing key is missing or shorter than 32 bytes")
    return value.encode("utf-8")


def target_sha256(target: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(target)).hexdigest()


def attest_receipt(receipt: dict[str, Any]) -> None:
    receipt["attestation"] = {
        "algorithm": ATTESTATION_ALGORITHM,
        "key_id": ATTESTATION_KEY_ID,
        "signature": hmac.new(signing_key(), canonical_receipt_bytes(receipt), hashlib.sha256).hexdigest(),
    }


def receipt_failures(receipt: Any, expected_hashes: dict[str, str] | None = None) -> list[str]:
    if not isinstance(receipt, dict):
        return ["validation receipt must be an object"]
    failures: list[str] = []
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        failures.append(f"schema_version must be {RECEIPT_SCHEMA}")
    if receipt.get("workflow_contract") != WORKFLOW_CONTRACT:
        failures.append(f"workflow_contract must be {WORKFLOW_CONTRACT}")
    if receipt.get("status") != "passed":
        failures.append("status must be passed")
    checks = receipt.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(REQUIRED_CHECKS) or any(checks.get(key) is not True for key in REQUIRED_CHECKS):
        failures.append("checks must contain the exact passing v6 check set")
    target = receipt.get("target")
    if not isinstance(target, dict) or any(not isinstance(target.get(key), str) for key in ("recommendation_id", "source_url", "source_title")):
        failures.append("target identity is missing or malformed")
    elif receipt.get("target_sha256") != target_sha256(target):
        failures.append("target_sha256 does not match target identity")
    for field in HASH_FIELDS:
        if not SHA256_RE.fullmatch(str(receipt.get(field) or "")):
            failures.append(f"{field} must be a full lowercase SHA-256")
    if expected_hashes:
        for field, expected in expected_hashes.items():
            if receipt.get(field) != expected:
                failures.append(f"{field} does not match the current file")
    attestation = receipt.get("attestation")
    if not isinstance(attestation, dict) or attestation.get("algorithm") != ATTESTATION_ALGORITHM or attestation.get("key_id") != ATTESTATION_KEY_ID or not SHA256_RE.fullmatch(str(attestation.get("signature") or "")):
        failures.append("attestation metadata is missing or malformed")
        return failures
    try:
        expected = hmac.new(signing_key(), canonical_receipt_bytes(receipt), hashlib.sha256).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        failures.append(str(exc))
        return failures
    if not hmac.compare_digest(str(attestation["signature"]), expected):
        failures.append("attestation signature is invalid")
    return failures


def receipt_attestation_valid(receipt: Any, expected_hashes: dict[str, str] | None = None) -> bool:
    return not receipt_failures(receipt, expected_hashes)
