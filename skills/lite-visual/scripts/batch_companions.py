#!/usr/bin/env python3
"""Make HTML companions for several Compass sources, one proven run at a time.

Hermes reliably finishes one companion per run but stalls when one turn must
author several. This runner starts a fresh one-shot Hermes run per source (the
same request that works for a single item), then verifies each source record.

Usage:
  batch_companions.py start <recommendation_id> [<recommendation_id> ...]
      Detaches, prints the progress log path, and returns immediately.
  batch_companions.py status [<log>]
      Prints the latest (or given) batch's per-item results.

Each item ends as `ready` (source record shows a ready companion), `failed`
(the run finished without a ready companion; its output tail is logged), or
`skipped` (already ready before the run).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

CLIENT = Path.home() / ".hermes/skills/workflow/learning-compass-site-operator/scripts/site_request.py"
LOG_DIR = Path.home() / ".hermes/cache/companion-batches"
REPO = Path.home() / "recommendations-worker"
PER_ITEM_TIMEOUT = 3600


def read(path: str, field: str):
    env = {k: v for k, v in os.environ.items() if k != "HERMES_TURN_ID"}
    proc = subprocess.run([sys.executable, str(CLIENT), "request", "GET", path, "--field", field],
                          capture_output=True, text=True, timeout=120, env=env)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def log(fh, **event) -> None:
    fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}, ensure_ascii=False) + "\n")
    fh.flush()


def run(ids: list[str], log_path: Path) -> None:
    with log_path.open("a") as fh:
        log(fh, event="batch_started", items=ids)
        for rid in ids:
            item = read(f"/capture/{rid}/record", "item.id,video_title,video_url") or {}
            title = item.get("video_title") or rid
            if read(f"/capture/{rid}/record", "companion.status") == "ready":
                log(fh, event="item", id=rid, title=title, result="skipped", reason="already ready")
                continue
            log(fh, event="item_started", id=rid, title=title)
            prompt = (f'make the html companion for the Compass source "{title}" '
                      f"(recommendation_id {rid}, {item.get('video_url', '')}) and publish it")
            started = time.time()
            try:
                proc = subprocess.run(["hermes", "-z", prompt], cwd=REPO, capture_output=True,
                                      text=True, timeout=PER_ITEM_TIMEOUT)
                tail = (proc.stdout or proc.stderr or "")[-600:]
            except subprocess.TimeoutExpired:
                tail = f"timed out after {PER_ITEM_TIMEOUT}s"
            status = read(f"/capture/{rid}/record", "companion.status")
            log(fh, event="item", id=rid, title=title, result="ready" if status == "ready" else "failed",
                seconds=round(time.time() - started), hermes_reply=tail)
        log(fh, event="batch_finished")


def status(log_path: Path | None) -> int:
    logs = sorted(LOG_DIR.glob("*.jsonl"))
    if log_path is None:
        if not logs:
            print(json.dumps({"error": "no batches"}))
            return 1
        log_path = logs[-1]
    events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    items = {e["id"]: e for e in events if e.get("event") in ("item_started", "item")}
    done = any(e.get("event") == "batch_finished" for e in events)
    print(json.dumps({"log": str(log_path), "finished": done,
                      "items": [{k: v for k, v in e.items() if k != "hermes_reply" or e.get("result") == "failed"}
                                for e in items.values()]}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "start":
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
        log_path.touch()
        subprocess.Popen([sys.executable, __file__, "_run", str(log_path), *sys.argv[2:]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(json.dumps({"started": True, "items": sys.argv[2:], "log": str(log_path),
                          "status_command": f"python3 {__file__} status {log_path}"}))
        return 0
    if len(sys.argv) >= 3 and sys.argv[1] == "_run":
        run(sys.argv[3:], Path(sys.argv[2]))
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "status":
        return status(Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
