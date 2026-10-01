"""Bounded local commands with compact progress and whole-process-group cleanup."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class ProcessFailure(RuntimeError):
    pass


def execute(command: list[str], label: str, cwd: Path | None = None, timeout: float = 180) -> str:
    try:
        limit = float(os.environ.get("LITE_VISUAL_STEP_TIMEOUT_SECONDS", timeout))
        if not 0 < limit <= 86400:
            raise ValueError()
    except ValueError as exc:
        raise ProcessFailure("LITE_VISUAL_STEP_TIMEOUT_SECONDS must be positive and at most 86400") from exc
    started = time.monotonic()

    def report(status: str) -> None:
        print(json.dumps({"stage": label, "status": status, "elapsed_seconds": round(time.monotonic()-started, 3), "timeout_seconds": limit}), file=sys.stderr, flush=True)

    report("started")
    child_environment = {**os.environ, "LITE_VISUAL_CHILD_TIMEOUT_SECONDS": str(limit * .85)}
    with subprocess.Popen(command, cwd=cwd, env=child_environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True) as process:
        try:
            while True:
                remaining = limit - (time.monotonic() - started)
                if remaining <= 0:
                    raise ProcessFailure(f"{label} timed out after {limit:g}s; inspect the failed stage before retrying; no automatic retry was attempted")
                try:
                    stdout, stderr = process.communicate(timeout=min(30, remaining))
                    break
                except subprocess.TimeoutExpired:
                    report("running")
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            report("interrupted")
            raise
        if process.returncode:
            report("failed")
            raise ProcessFailure(f"{label} failed: {(stderr or stdout).strip()[-6000:]}")
    report("completed")
    return stdout
