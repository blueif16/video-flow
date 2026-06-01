"""PostToolUse hook — the SYNC trigger (CONTRACTS §4, Layer 3).

Wired in .claude/settings.json with a matcher on the generation tool. When a
synchronous generator returns a file, Claude Code invokes this with the PostToolUse
payload on STDIN; we mark the node `landed` and call judge_one. Exit 0 always
(a hook must never block the agent).

Also accepts `--node-id <id> --project-dir <dir>` for testability (no stdin).

Resolution of node_id + project_dir from the PostToolUse payload:
  - the runner emits an envelope whose data carries `node_id`; the tool_response
    (or tool_input) is searched for `node_id` and an output path.
  - project_dir is derived from the artifact path (.../projects/<name>/artifacts/...)
    or taken from the payload / --project-dir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional


def _log(msg: str) -> None:
    print(f"[on_artifact_landed] {msg}", file=sys.stderr)


def _project_dir_from_path(path: str) -> Optional[str]:
    """projects/<name>/artifacts/<node>/<attempt>.ext → projects/<name>."""
    parts = os.path.abspath(path).split(os.sep)
    if "artifacts" in parts:
        i = parts.index("artifacts")
        if i >= 1:
            return os.sep.join(parts[:i])
    return None


def _find(d, key):
    """Depth-first search for the first value of `key` in a nested dict/list."""
    if isinstance(d, dict):
        if key in d and d[key]:
            return d[key]
        for v in d.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(d, list):
        for v in d:
            r = _find(v, key)
            if r is not None:
                return r
    return None


_GEN_MARKER = "manju.skills.generating.runner"


def _is_generation_event(payload: dict) -> bool:
    """True iff this PostToolUse fired for the generation tool (the runner).

    The runner runs via Bash, so the matcher is `Bash`; we self-filter on the
    command so unrelated Bash calls are a clean no-op. A direct (non-Bash)
    generation tool would carry the runner envelope shape instead — also accepted.
    """
    cmd = _find(payload, "command")
    if isinstance(cmd, str) and _GEN_MARKER in cmd:
        return True
    # non-Bash generation tool: an envelope with output_files + data.node_id.
    if _find(payload, "output_files") and _find(payload, "node_id"):
        return True
    return False


def _resolve_from_payload(payload: dict) -> tuple[Optional[str], Optional[str]]:
    """Pull (node_id, project_dir) out of a PostToolUse payload."""
    node_id = _find(payload, "node_id")
    project_dir = _find(payload, "project_dir")
    if not project_dir:
        # derive from any output file path in the payload.
        out = _find(payload, "output_files")
        path = out[0] if isinstance(out, list) and out else _find(payload, "artifact_path")
        if path:
            project_dir = _project_dir_from_path(path)
    return node_id, project_dir


def _land_and_judge(node_id: str, project_dir: str) -> None:
    """Mark the node landed (if it isn't) then judge it. Tolerant + idempotent."""
    from manju.ledger import load
    from manju.overlord.control import judge_one

    ledger = load(project_dir)
    if node_id not in ledger._index:
        _log(f"node {node_id!r} not in ledger; nothing to do")
        return
    asset = ledger._index[node_id][1] == "asset"
    run = ledger.node(node_id)["run"]
    cur = run.get("ref_status") if asset else run.get("status")

    # a sync generator just produced a file → move the node into the landed gate.
    try:
        if asset:
            if cur == "drafting":
                ledger.set_status(node_id, "judging", "overlord")
                ledger.save()
        else:
            if cur == "generating":
                ledger.set_status(node_id, "landed", "overlord")
                ledger.save()
    except Exception as e:  # noqa: BLE001 — already landed/judging is fine
        _log(f"land transition skipped for {node_id}: {e}")

    judge_one(node_id, project_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="overlord PostToolUse hook")
    ap.add_argument("--node-id", help="node id (testability; skips stdin)")
    ap.add_argument("--project-dir", help="project dir (testability)")
    args = ap.parse_args(argv)

    node_id = args.node_id
    project_dir = args.project_dir

    if not node_id or not project_dir:
        raw = ""
        if not sys.stdin.isatty():
            try:
                raw = sys.stdin.read()
            except Exception:  # noqa: BLE001
                raw = ""
        if raw.strip():
            try:
                payload = json.loads(raw)
                if not _is_generation_event(payload):
                    return 0  # not a generation event — clean no-op
                pnode, pdir = _resolve_from_payload(payload)
                node_id = node_id or pnode
                project_dir = project_dir or pdir
            except Exception as e:  # noqa: BLE001 — a hook never crashes the agent
                _log(f"bad PostToolUse payload: {e}")

    if not node_id or not project_dir:
        _log("no node_id/project_dir resolved; nothing to judge (exit 0)")
        return 0

    try:
        _land_and_judge(node_id, project_dir)
    except Exception as e:  # noqa: BLE001 — swallow so the hook always exits 0
        _log(f"judge_one failed for {node_id}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
