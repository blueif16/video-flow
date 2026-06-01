"""Idempotent async poller — the ASYNC trigger (CONTRACTS §4, Layer 3).

Fire-and-forget providers (fal/Replicate/Veo) return a request_id and finish
later. The sync hook can't see them. This poller (driven by `/loop 30s`):

  1. scans the async job queue for in-flight jobs: rows with status=="submitted".
  2. polls the provider (mock = immediately "done").
  3. on done: ensures the artifact is downloaded, records the attempt (idempotent),
     flips the node to `landed` (shot) / `judging` (asset), and calls the SAME
     judge_one as the sync hook.
  4. SELF-TERMINATES when there are no `submitted` rows (idle cost = cheap).

WHERE THE QUEUE LIVES: the ledger run block is schema-locked
(additionalProperties:false) — there is no run field for an in-flight provider
job. So the async queue is a SIDECAR file `<project_dir>/_async_jobs.json`:
the async-submit path appends {request_id, provider, status:"submitted", node_id,
request} there and exits; this poller scans + drains it. The ledger stays the
canonical artifact/verdict store; the sidecar is just the in-flight job board.

For V1 the mock provider is synchronous (enqueue_generation lands inline), so this
queue is normally empty and the poller self-terminates immediately. It exists for
the real fire-and-forget path and is exercised by submit_async() + the self-test.

Idempotent: a node already past `landed` is skipped; an attempt already recorded
is not double-recorded; a drained job is marked `done` in the sidecar.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from typing import Optional

from manju.ledger import load
from manju.overlord.control import judge_one, run_request, WRITER

_QUEUE_FILE = "_async_jobs.json"


def _log(msg: str) -> None:
    print(f"[poller] {msg}", file=sys.stderr)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _queue_path(project_dir: str) -> str:
    return os.path.join(project_dir, _QUEUE_FILE)


def _load_queue(project_dir: str) -> list[dict]:
    path = _queue_path(project_dir)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_queue(project_dir: str, jobs: list[dict]) -> None:
    path = _queue_path(project_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def submit_async(node_id: str, request: dict, project_dir: str,
                 request_id: Optional[str] = None, provider: str = "mock") -> dict:
    """Append a fire-and-forget job to the sidecar queue (what the async hook calls).

    The real async hook submits to the provider, gets a request_id, writes this row,
    and exits — the poller drains it later. Returns the queued job row.
    """
    jobs = _load_queue(project_dir)
    job = {
        "request_id": request_id or f"{node_id}:{len(jobs)}",
        "node_id": node_id,
        "provider": provider,
        "status": "submitted",
        "request": request,
        "ts": _now(),
    }
    jobs.append(job)
    _save_queue(project_dir, jobs)
    return job


def _poll_provider(job: dict, project_dir: str) -> Optional[dict]:
    """Poll the provider for this request_id. Mock = immediately done.

    Returns the runner envelope on `done`, or None if still running. A real
    provider adapter would GET the request_id here and download on completion;
    the mock re-runs the (deterministic, skip-if-exists) request to materialize
    the same content-addressed artifact.
    """
    provider = job.get("provider", "mock")
    if provider == "mock":
        req = dict(job.get("request", {}))
        req.setdefault("model", "mock")
        req.setdefault("node_id", job.get("node_id"))
        return run_request(req, project_dir)
    # real providers: a GET on request_id; raise-to-stub until a key is wired.
    raise RuntimeError(f"async provider {provider!r} not implemented (mock is V1)")


def _record_landed(node_id: str, project_dir: str, envelope: dict, job: dict) -> None:
    """Record the downloaded attempt + flip the node into the landed gate (idempotent)."""
    ledger = load(project_dir)
    if node_id not in ledger._index:
        return
    asset = ledger._index[node_id][1] == "asset"
    run = ledger.node(node_id)["run"]

    data = envelope.get("data", {})
    out = envelope.get("output_files", [])
    attempt_id = data.get("attempt_id")

    existing = {a.get("attempt_id") for a in run.get("attempts", [])}
    if attempt_id not in existing:
        ledger.append_attempt(node_id, {
            "attempt_id": attempt_id,
            "ts": _now(),
            "seed": job.get("request", {}).get("seed"),
            "model": envelope.get("model", "mock"),
            "prompt": job.get("request", {}).get("prompt", ""),
            "artifact_path": out[0] if out else None,
            "thumb_path": data.get("thumb_path"),
            "verdict": None,
            "lesson_ref": None,
        })

    cur = run.get("ref_status") if asset else run.get("status")
    try:
        if asset:
            if cur == "none":
                ledger.set_status(node_id, "drafting", WRITER)
                cur = "drafting"
            if cur == "drafting":
                ledger.set_status(node_id, "judging", WRITER)
        else:
            if cur in ("pending", "needs_regen"):
                ledger.set_status(node_id, "generating", WRITER)
                cur = "generating"
            if cur == "generating":
                ledger.set_status(node_id, "landed", WRITER)
    except Exception as e:  # noqa: BLE001 — already landed is fine
        _log(f"land transition skipped for {node_id}: {e}")
    ledger.save()


def poll_once(project_dir: str) -> dict:
    """One poll pass over all submitted rows. Returns a summary; self-terminating.

    For each submitted row that is `done`: download → land → judge_one → mark done.
    """
    jobs = _load_queue(project_dir)
    submitted = [j for j in jobs if j.get("status") == "submitted"]
    if not submitted:
        _log("no submitted rows — idle, self-terminating")
        return {"submitted": 0, "completed": [], "idle": True}

    completed = []
    for job in submitted:
        node_id = job.get("node_id")
        envelope = _poll_provider(job, project_dir)
        if envelope is None:
            continue  # still running; leave it submitted
        _record_landed(node_id, project_dir, envelope, job)
        judge_one(node_id, project_dir)
        job["status"] = "done"
        job["done_ts"] = _now()
        completed.append(node_id)

    _save_queue(project_dir, jobs)
    return {"submitted": len(submitted), "completed": completed, "idle": False}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="overlord async poller (driven by /loop 30s)")
    ap.add_argument("--project-dir", required=True, help="project dir to poll")
    args = ap.parse_args(argv)
    summary = poll_once(args.project_dir)
    _log(f"done: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
