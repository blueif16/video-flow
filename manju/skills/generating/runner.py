"""The generating runner — THE reusable image/video primitive (CONTRACTS §2).

Chain (in order):
  1. validate-before-spend  — reject bad requests BEFORE any provider call.
  2. presence-router        — pick the adapter from model + kind + reference fields.
  3. lossy per-model adapter— map the canonical schema down to one model's params.
  4. provider               — does the work.

Two entrypoints, one behavior:
  - run_request(req, project_dir) -> envelope   (in-process; what B/D import & reuse)
  - python -m manju.skills.generating.runner --input <req.json>   (also reads stdin)
    stdout = EXACTLY one JSON line (the envelope). All logs -> stderr.
    Nonzero exit on failure. Never emits a partial envelope.

Canonical request (CONTRACTS §2):
  { "kind": "image"|"video", "prompt": str,
    "reference_images": [abs,...]  (<=9), "reference_videos": [...], "reference_audios": [...],
    "duration_s": int, "resolution": "720p", "aspect_ratio": "16:9",
    "generate_audio": bool, "seed": int, "model": "mock",
    "node_id": str  (optional; content-addressing bucket) }
"""
from __future__ import annotations

import argparse
import json
import sys

from .adapters import ADAPTERS

MAX_REFERENCE_IMAGES = 9
_KINDS = {"image", "video"}

# canonical schema: field -> normalized default. Order here is the canonical order.
_DEFAULTS: dict = {
    "kind": None,
    "prompt": None,
    "reference_images": [],
    "reference_videos": [],
    "reference_audios": [],
    "duration_s": None,
    "resolution": None,
    "aspect_ratio": None,
    "generate_audio": False,
    "seed": None,
    "model": "mock",
}
# what each model can actually take (lossy adapter map). A field absent here is dropped.
_MODEL_CAPS: dict[str, set[str]] = {
    "mock": set(_DEFAULTS) | {"node_id"},  # mock takes everything
    "fal": {"kind", "prompt", "reference_images", "reference_videos", "reference_audios",
            "duration_s", "resolution", "aspect_ratio", "generate_audio", "seed", "model", "node_id"},
    "replicate": {"kind", "prompt", "reference_images", "reference_videos", "reference_audios",
                  "duration_s", "resolution", "aspect_ratio", "generate_audio", "seed", "model", "node_id"},
}


class RequestError(ValueError):
    """Raised by validate-before-spend; no provider call happens."""


# ── 1. validate-before-spend ──────────────────────────────────────────────────
def _validate(req: dict) -> None:
    """Validate the canonical input + exclusivity BEFORE spending. Raise RequestError."""
    if not isinstance(req, dict):
        raise RequestError("request must be a JSON object")

    kind = req.get("kind")
    if kind not in _KINDS:
        raise RequestError(f"kind must be one of {sorted(_KINDS)}, got {kind!r}")

    prompt = req.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise RequestError("prompt is required and must be a non-empty string")

    for f in ("reference_images", "reference_videos", "reference_audios"):
        v = req.get(f, [])
        if v is None:
            continue
        if not isinstance(v, list) or any(not isinstance(p, str) for p in v):
            raise RequestError(f"{f} must be a list of path strings")

    imgs = req.get("reference_images") or []
    if len(imgs) > MAX_REFERENCE_IMAGES:
        raise RequestError(f"reference_images > {MAX_REFERENCE_IMAGES} ({len(imgs)} given)")

    # exclusivity: a kind:image request can't carry video refs (and vice-versa).
    if kind == "image" and (req.get("reference_videos") or []):
        raise RequestError("reference_videos present on a kind:image request")
    if kind == "video" and (req.get("reference_images") is None):
        pass  # videos may be image-anchored (i2v) — images allowed on video

    model = req.get("model", "mock")
    if model not in ADAPTERS:
        raise RequestError(f"unknown model {model!r}; known: {sorted(ADAPTERS)}")

    if "duration_s" in req and req["duration_s"] is not None:
        d = req["duration_s"]
        if not isinstance(d, (int, float)) or isinstance(d, bool) or d <= 0:
            raise RequestError(f"duration_s must be a positive number, got {d!r}")


# ── normalization (canonical, deterministic, content-addressable) ─────────────
def _normalize(req: dict) -> dict:
    """Project the request onto the canonical schema with defaults filled, key order fixed."""
    norm = {}
    for key, default in _DEFAULTS.items():
        val = req.get(key, default)
        if val is None and key in ("reference_images", "reference_videos", "reference_audios"):
            val = []
        norm[key] = val
    # node_id is the content-addressing bucket, not part of the model schema proper
    if req.get("node_id"):
        norm["node_id"] = req["node_id"]
    return norm


# ── 2. presence-router + 3. lossy adapter map ─────────────────────────────────
def _route(norm: dict):
    """Pick the adapter module from model (+ kind/refs already validated)."""
    return ADAPTERS[norm["model"]]


def _to_model_params(norm: dict) -> dict:
    """Lossy map: keep only what the target model can take; drop the rest."""
    caps = _MODEL_CAPS.get(norm["model"], set(_DEFAULTS))
    params = {k: v for k, v in norm.items() if k in caps}
    # the adapter content-addresses on `_node_id`; pass it through under that name.
    params["_node_id"] = norm.get("node_id")
    return params


# ── the in-process entrypoint everyone reuses ─────────────────────────────────
def run_request(req: dict, project_dir: str) -> dict:
    """Validate -> route -> lossy-adapt -> provider. Returns the envelope.

    Raises RequestError on an invalid request (no provider call). Returns
    {"model": str, "output_files": [abs...], "data": {...}}.
    """
    _validate(req)                    # 1. before any spend
    norm = _normalize(req)
    adapter = _route(norm)            # 2. presence-router
    params = _to_model_params(norm)   # 3. lossy per-model adapter
    return adapter.generate(params, project_dir)   # 4. provider


# ── CLI wrapper ───────────────────────────────────────────────────────────────
def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="generating runner (canonical request -> envelope)")
    ap.add_argument("--input", help="path to request JSON (default: read stdin)")
    ap.add_argument("--project-dir", help="project dir (default: from request 'project_dir')")
    args = ap.parse_args(argv)

    try:
        raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
        req = json.loads(raw)
    except Exception as e:  # noqa: BLE001 — malformed input is a clean nonzero exit
        _log(f"[runner] bad input: {e}")
        return 2

    project_dir = args.project_dir or req.pop("project_dir", None)
    if not project_dir:
        _log("[runner] project_dir required (--project-dir or request 'project_dir')")
        return 2

    try:
        envelope = run_request(req, project_dir)
    except RequestError as e:
        _log(f"[runner] validate-before-spend rejected: {e}")  # no file written
        return 1
    except Exception as e:  # noqa: BLE001 — provider/adapter failure
        _log(f"[runner] generation failed: {e}")
        return 1

    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
