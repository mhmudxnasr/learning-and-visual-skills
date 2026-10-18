#!/usr/bin/env python3
"""Prepare, seal, publish, and optionally close one HTML-only Lite Visual job."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from seal import INTEGRITY_SCHEMA, current_receipt, prepare_provenance, seal
from process_runtime import ProcessFailure, execute
DEFAULT_WORKER = "https://recommendations-worker.mhmudnasr30.workers.dev"
# The API keeps the v4 stage names; HTML-only evidence declares companion_format.
STAGES = ["resolve_source", "extract_source", "map_coverage", "author_html", "render_pdf", "validate_pair", "publish_pair", "verify_record"]
HTML_ONLY = {"companion_format": "html"}
class WorkflowError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


def validate_job_target(job: dict[str, Any], args: argparse.Namespace) -> None:
    payload = job.get("payload") or {}
    if job.get("id") != args.job_id or job.get("job_type") != "visualise_source":
        raise WorkflowError("claimed job identity/type does not match --job-id")
    identities = {str(value) for value in (job.get("recommendation_id"), payload.get("recommendation_id")) if value}
    if identities != {args.recommendation_id}:
        raise WorkflowError("claimed job recommendation identity does not match the publication target")
    if normalized_url(str(payload.get("source_url") or "")) != normalized_url(args.source_url):
        raise WorkflowError("claimed job source URL does not match the publication target")
    if str(payload.get("title") or "").strip() != args.source_title.strip():
        raise WorkflowError("claimed job source title does not match the publication target")
    if payload.get("workflow_contract") != "lite-visual-linear/v4":
        raise WorkflowError("claimed job does not use the current Lite Visual workflow contract")
    if (payload.get("revision_of_pair_id") or None) != (args.supersedes_pair_id or None):
        raise WorkflowError("claimed job revision lineage does not match --supersedes-pair-id")
    if str(payload.get("chapter_key") or "") != str(getattr(args, "chapter_key", None) or ""):
        raise WorkflowError("claimed job chapter identity does not match --chapter-key")


def run(command: list[str], label: str) -> str:
    budgets = {"source extraction": 7200, "atomic companion publication": 600}
    try:
        return execute(command, label, timeout=budgets.get(label, 180)).strip()
    except ProcessFailure as exc:
        raise WorkflowError(str(exc)) from exc


@contextmanager
def workspace_lock(work: Path):
    with (work / ".lite-visual.lock").open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkflowError(f"workspace busy: {work}; another runner owns its lock; inspect that process instead of launching a duplicate") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def api(worker: str, path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (compatible; HermesCron/1.0)", "x-agent-name": "lite-visual-runner"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(worker.rstrip("/") + path, data=data, method=method, headers=headers), timeout=120) as response:
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise WorkflowError(f"{method} {path} failed (HTTP {exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{method} {path} failed: {exc}") from exc


class Heartbeat:
    def __init__(self, worker_url: str, job_id: str, identity: str) -> None:
        self.worker_url, self.job_id, self.identity = worker_url, job_id, identity
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self.stop_event.wait(120):
            try:
                api(self.worker_url, f"/agent/jobs/{self.job_id}/heartbeat", "POST", {"worker": self.identity})
            except Exception as exc:
                print(f"heartbeat warning: {exc}", file=sys.stderr)

    def __enter__(self) -> "Heartbeat":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)


def checkpoint(worker_url: str, job_id: str, identity: str, step: str, evidence: dict[str, Any]) -> None:
    api(worker_url, f"/agent/jobs/{job_id}/checkpoint", "POST", {"worker": identity, "step": step, "evidence": evidence})


def prepare(args: argparse.Namespace) -> int:
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    with workspace_lock(work):
        return _prepare_locked(args, work)


def workspace_extraction_current(source_id: str, source: Path, manifest: Path) -> bool:
    """True when this workspace already holds a complete extraction of exactly this source (same identity, bytes match the receipt)."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        identity = data.get("source")
        urls = {identity.get("url") if isinstance(identity, dict) else identity, data.get("resolved_source")}
        return data.get("status") == "complete" and source_id in urls and hashlib.sha256(source.read_bytes()).hexdigest() == data.get("content_sha256")
    except (OSError, ValueError, AttributeError):
        return False


def _prepare_locked(args: argparse.Namespace, work: Path) -> int:
    source = work / "source.txt"
    manifest = work / "source-extraction.json"
    scope = work / "source-scope.json"
    if workspace_extraction_current(args.source, source, manifest):
        print(json.dumps({"stage": "source extraction", "skipped": "workspace already holds a complete extraction of this source"}), file=sys.stderr)
    else:
        run([sys.executable, str(ROOT / "extract_source.py"), args.source, "--kind", args.kind, "--output", str(source), "--manifest", str(manifest)], "source extraction")
    prepare_provenance(work)
    print(json.dumps({"ok": True, "workdir": str(work), "source": str(source), "manifest": str(manifest), "next": "read the complete source.txt, write companion.md (references/format.md), run build_companion.py, then publish (or finish for a draft)"}, ensure_ascii=False))
    return 0


def ensure_target(work: Path, args: argparse.Namespace) -> None:
    target = {"recommendation_id": args.recommendation_id, "source_url": args.source_url, "source_title": args.source_title}
    if getattr(args, "chapter_key", None):
        target["chapter_key"] = args.chapter_key
    path = work / "work-item.json"
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if any(str(stored.get(key) or "") != str(target.get(key) or "") for key in (*target, "chapter_key")):
            raise WorkflowError("work-item.json does not match the requested source target")
    else:
        path.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def finish(args: argparse.Namespace) -> int:
    work = args.workdir.resolve()
    with workspace_lock(work):
        ensure_target(work, args)
        receipt = current_receipt(work) or seal(work)
        print(json.dumps({"ok": True, "html": str(work / "companion.html"), "receipt": str(work / "validation-receipt.json"), "verification_scope": receipt["verification_scope"], "quality_checks": receipt["quality_checks"]}, ensure_ascii=False))
    return 0


def publish(args: argparse.Namespace) -> int:
    work = args.workdir.resolve()
    with workspace_lock(work):
        return _publish_locked(args, work)


def _publish_locked(args: argparse.Namespace, work: Path) -> int:
    work_item, source, manifest, scope = work / "work-item.json", work / "source.txt", work / "source-extraction.json", work / "source-scope.json"
    ledger, html, receipt = work / "coverage-ledger.json", work / "companion.html", work / "validation-receipt.json"
    ensure_target(work, args)
    for path in (work_item, source, manifest, html):
        if not path.is_file() or not path.stat().st_size:
            raise WorkflowError(f"required workflow input is missing: {path}")
    receipt_data = current_receipt(work) or seal(work)
    try:
        contract = api(args.worker, "/artifacts/pair-contract")
    except WorkflowError as exc:
        raise WorkflowError("receiving Worker does not advertise the direct pair contract; deploy the matching Worker update before publication; finished local HTML is preserved") from exc
    if INTEGRITY_SCHEMA not in contract.get("receipt_schemas", []):
        raise WorkflowError(f"receiving Worker does not support {INTEGRITY_SCHEMA}; finished local HTML is preserved")
    extraction = json.loads(manifest.read_text(encoding="utf-8"))
    scope_data = json.loads(scope.read_text(encoding="utf-8"))
    ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
    job: dict[str, Any] | None = None
    heartbeat: Heartbeat | None = None
    published = False
    try:
        if args.job_id:
            claimed = api(args.worker, f"/agent/jobs/{args.job_id}/claim", "POST", {"worker": args.worker_identity})
            claimed_job = claimed.get("job") or {}
            validate_job_target(claimed_job, args)
            job = claimed_job
            heartbeat = Heartbeat(args.worker, args.job_id, args.worker_identity)
            heartbeat.__enter__()
        current = str((job or {}).get("workflow_step") or "resolve_source")
        if current not in STAGES:
            raise WorkflowError(f"job has unknown workflow step: {current}")
        stage_index = STAGES.index(current)
        def advance(step: str, step_evidence: dict[str, Any]) -> None:
            nonlocal stage_index
            if args.job_id and STAGES.index(step) > stage_index:
                checkpoint(args.worker, args.job_id, args.worker_identity, step, step_evidence)
                stage_index = STAGES.index(step)
        evidence = {
            "extract_source": {"source_identity": args.source_url, "source_kind": scope_data.get("source", {}).get("kind") or "article"},
            "map_coverage": {key: extraction.get(key) for key in ("schema_version", "status", "method", "content_sha256", "cache_key", "word_count")},
            "author_html": {"source_sha256": digest(source), "source_scope_sha256": digest(scope), "word_count": scope_data["source"]["word_count"], "span_count": len(scope_data["spans"]), "authoring_mode": "direct"},
        }
        evidence["map_coverage"]["manifest_path"] = str(manifest)
        if args.job_id:
            for step in ("extract_source", "map_coverage", "author_html"):
                advance(step, evidence[step])
        render_evidence = {"html_sha256": digest(html), "coverage_ledger_sha256": digest(ledger), "claim_count": len(ledger_data.get("claims") or []), "canonical_selector": "article[data-canonical-content=true]", "authoring_mode": "direct", **HTML_ONLY}
        advance("render_pdf", render_evidence)
        advance("validate_pair", {"html_sha256": digest(html), **HTML_ONLY})
        advance("publish_pair", {"validation_schema": receipt_data["schema_version"], "validation_status": receipt_data["status"], "receipt_sha256": digest(receipt), **HTML_ONLY})
        upload_html = html
        if args.upload_basename:
            base = args.upload_basename
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", base):
                raise WorkflowError("--upload-basename must be a lowercase ASCII hyphen slug")
            named = work / "upload"
            named.mkdir(exist_ok=True)
            upload_html = named / f"{base}.html"
            upload_html.unlink(missing_ok=True)
            upload_html.write_bytes(html.read_bytes())
        command = [sys.executable, str(ROOT / "upload_pair.py"), "--html", str(upload_html), "--receipt", str(receipt), "--recommendation-id", args.recommendation_id, "--source-url", args.source_url, "--source-title", args.source_title, "--worker", args.worker]
        for option, value in (("--pair-id", args.pair_id), ("--revision", args.revision), ("--supersedes-pair-id", args.supersedes_pair_id), ("--chapter-key", getattr(args, "chapter_key", None)), ("--chapter-title", getattr(args, "chapter_title", None)), ("--chapter-number", getattr(args, "chapter_number", None))):
            if value:
                command.extend([option, str(value)])
        upload = json.loads(run(command, "atomic companion publication").splitlines()[-1])
        if not upload.get("ok") or upload.get("status") != "ready":
            raise WorkflowError(f"atomic companion publication failed: {upload}")
        published = True
        if args.job_id:
            final_evidence = {"pair_id": upload["pair_id"], "html_artifact_id": upload["html_artifact_id"], **HTML_ONLY}
            advance("verify_record", final_evidence)
            api(args.worker, f"/agent/jobs/{args.job_id}/complete", "POST", {"worker": args.worker_identity, **final_evidence, "validation_status": "passed"})
        print(json.dumps({"ok": True, "validation": receipt_data, "publication": upload, "job_id": args.job_id}, ensure_ascii=False))
        return 0
    except Exception as exc:
        if args.job_id and job and not published:
            try:
                api(args.worker, f"/agent/jobs/{args.job_id}/fail", "POST", {"worker": args.worker_identity, "error": str(exc)[:1800]})
            except Exception:
                pass
        raise
    finally:
        if heartbeat:
            heartbeat.__exit__(None, None, None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("source")
    prep.add_argument("--kind", default="auto", choices=["auto", "article", "youtube", "audio", "pdf", "epub", "document", "text"])
    prep.add_argument("--workdir", required=True, type=Path)
    prep.add_argument("--target-words", type=int, default=280, help="legacy compatibility argument; direct authoring has no scope paperwork")
    prep.set_defaults(handler=prepare)
    pub = sub.add_parser("publish")
    pub.add_argument("--workdir", required=True, type=Path)
    pub.add_argument("--recommendation-id", required=True)
    pub.add_argument("--source-url", required=True)
    pub.add_argument("--source-title", required=True)
    pub.add_argument("--upload-basename", help="Source-specific lowercase slug for the uploaded HTML filename; bytes and receipt are unchanged.")
    pub.add_argument("--pair-id")
    pub.add_argument("--revision")
    pub.add_argument("--supersedes-pair-id")
    pub.add_argument("--chapter-key")
    pub.add_argument("--chapter-title")
    pub.add_argument("--chapter-number", type=int)
    pub.add_argument("--job-id")
    pub.add_argument("--worker-identity", default="hermes-lite-visual-runner-v1")
    pub.add_argument("--worker", default=DEFAULT_WORKER)
    pub.set_defaults(handler=publish)
    local = sub.add_parser("finish", help="seal local HTML without network publication")
    local.add_argument("--workdir", required=True, type=Path)
    local.add_argument("--recommendation-id", required=True)
    local.add_argument("--source-url", required=True)
    local.add_argument("--source-title", required=True)
    local.add_argument("--chapter-key")
    local.set_defaults(handler=finish)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.handler(args)
    except (WorkflowError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
