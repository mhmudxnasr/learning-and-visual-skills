#!/usr/bin/env python3
"""Bind an ordered manifest to exact local pairs, without editorial/layout audits.

Writes a registration body; performs no API requests or publication.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pair_integrity import digest, write_json
from receipt_attestation import attest_receipt, canonical_json_bytes
from run_workflow import current_validation_receipt
from upload_pair import default_pair_id
import hashlib

SCHEMA = "lite-visual-corpus-integrity/v1"
CHECKS = {"ordered_targets": True, "local_receipt_bindings": True, "file_hashes": True}
HASH_FIELDS = ("target_sha256", "work_item_sha256", "source_extraction_sha256", "source_sha256", "source_scope_sha256", "coverage_ledger_sha256", "html_sha256", "pdf_sha256", "receipt_sha256")
ROW_FIELDS = ("recording_number", "recommendation_id", "chapter_key", "source_url", "source_title", "workdir", "pair_id", *HASH_FIELDS)


def audit(manifest: Path) -> dict:
    raw = manifest.read_bytes()
    source = json.loads(raw)
    if not isinstance(source, dict):
        raise ValueError("manifest must be a JSON object")
    items = source.get("targets")
    thread = str(source.get("thread_id") or "").strip()
    if not thread or not isinstance(items, list) or not 1 <= len(items) <= 400:
        raise ValueError("manifest requires thread_id and 1–400 ordered targets")
    targets = []
    owners, numbers, jobs = set(), set(), set()
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"target {position} must be an object")
        target = {key: str(item.get(key) or "").strip() for key in ("recommendation_id", "chapter_key", "source_url", "source_title", "workdir", "job_id", "workflow_run_id")}
        if any(not value for key, value in target.items() if key != "chapter_key") or not Path(target["workdir"]).is_absolute():
            raise ValueError(f"target {position} has incomplete identity, job/run, or absolute workspace")
        number = item.get("recording_number")
        if type(number) is not int or number < 1:
            raise ValueError(f"target {position} requires a positive recording_number")
        owner = (target["recommendation_id"], target["chapter_key"])
        if owner in owners or number in numbers or target["job_id"] in jobs:
            raise ValueError("manifest repeats a source/chapter, recording number, or job")
        owners.add(owner); numbers.add(number); jobs.add(target["job_id"])
        work = Path(target["workdir"])
        receipt = current_validation_receipt(*[work / name for name in ("work-item.json", "source-extraction.json", "source.txt", "source-scope.json", "coverage-ledger.json", "companion.html", "companion.pdf", "validation-receipt.json")])
        if receipt is None:
            raise ValueError(f"target {position} has no current hash-matched signed pair")
        identity = {key: target[key] for key in ("recommendation_id", "source_url", "source_title", "chapter_key") if key != "chapter_key" or target[key]}
        if receipt["target"] != identity:
            raise ValueError(f"target {position} differs from its signed source identity")
        target.update(position=position, recording_number=number, supersedes_pair_id=item.get("supersedes_pair_id") or None,
                      pair_id=default_pair_id(target["recommendation_id"], receipt, target["chapter_key"]),
                      **{key: receipt[key] for key in HASH_FIELDS if key != "receipt_sha256"}, receipt_sha256=digest(work / "validation-receipt.json"))
        targets.append(target)
    # Match the Worker's ordered array encoding exactly, including chapter rules.
    target_rows = [[t["recording_number"], t["recommendation_id"], *([t["chapter_key"]] if t["chapter_key"] else []), t["source_url"], t["source_title"], t["workdir"]] for t in targets]
    sha = lambda value: hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    manifest_sha = hashlib.sha256(raw).hexdigest()
    audit_receipt = {"schema_version": SCHEMA, "status": "passed", "verification_scope": "integrity-only", "quality_checks": "not_run",
        "checks": CHECKS, "thread_id": thread, "manifest_sha256": manifest_sha, "target_set_sha256": sha(target_rows),
        "corpus_sha256": sha([[t[key] for key in ROW_FIELDS] for t in targets]), "expected": len(targets), "audited": len(targets), "failed": 0}
    if manifest.read_bytes() != raw:
        raise ValueError("manifest changed during the integrity check")
    attest_receipt(audit_receipt)
    return {"thread_id": thread, "manifest_sha256": manifest_sha, "target_set_sha256": audit_receipt["target_set_sha256"],
        "audit_corpus_sha256": audit_receipt["corpus_sha256"], "expected_pairs": len(targets), "audit_receipt": audit_receipt, "targets": targets}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("manifest", type=Path)
    cli.add_argument("--out", required=True, type=Path)
    args = cli.parse_args()
    try:
        result = audit(args.manifest)
        write_json(args.out, result)
        print(json.dumps({"ok": True, "registration": str(args.out), "pairs": result["expected_pairs"], "quality_checks": "not_run"}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
