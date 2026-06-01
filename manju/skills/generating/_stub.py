"""generating runner — neighbor STUB (CONTRACTS §6).

The real runner (Phase 3, Agent C) is `manju.skills.generating.runner.run_request`.
Until it lands, dependents (referencing, the overlord) import THIS through the seam:

    try:
        from manju.skills.generating.runner import run_request   # real
    except ImportError:
        from manju.skills.generating._stub import run_request    # documented mock envelope

The stub does the model-agnostic part of the runner — validate-before-spend +
normalize + route — then delegates to the **mock adapter** (the V1 default, the only
provider that ships today). The mock adapter content-addresses the request, copies
the matching `assets/sample/*` to the artifact path, and is skip-if-exists. So the
returned envelope points at a file that actually exists on disk:

    {"model": "mock", "output_files": [abs...], "data": {...}}

This is the *documented minimal valid output* (CONTRACTS §6) — a real, reusable,
deterministic mock generation. The real runner.run_request supersedes this verbatim.
"""
from __future__ import annotations

from manju.skills.generating.adapters import ADAPTERS

# canonical request keys the adapter content-addresses on (the normalized request).
# node_id is carried as the adapter-private `_node_id`: it scopes the artifact path
# AND is part of the take identity (different assets -> different attempt_ids).
_CANONICAL_KEYS = (
    "kind", "prompt", "reference_images", "reference_videos", "reference_audios",
    "duration_s", "resolution", "aspect_ratio", "generate_audio", "seed", "model",
)


def _normalize(request: dict) -> dict:
    """Project to the canonical shape, drop empty fields, inject the adapter `_node_id`."""
    req: dict = {}
    for key in _CANONICAL_KEYS:
        val = request.get(key)
        if val is not None and val != []:
            req[key] = val
    req["model"] = request.get("model") or "mock"
    req["_node_id"] = request.get("node_id")
    return req


def _validate(req: dict) -> None:
    """validate-before-spend: reject invalid requests before any provider call (§2)."""
    if req.get("kind") not in ("image", "video"):
        raise ValueError(f"kind must be image|video, got {req.get('kind')!r}")
    if not req.get("prompt"):
        raise ValueError("prompt is required")
    if len(req.get("reference_images") or []) > 9:
        raise ValueError(f"reference_images > 9 ({len(req['reference_images'])})")
    if req["kind"] == "image" and (req.get("reference_videos") or req.get("reference_audios")):
        raise ValueError("kind:image may not carry reference_videos / reference_audios")


def run_request(request: dict, project_dir: str) -> dict:
    """Validate → normalize → route to the provider adapter → mock envelope."""
    req = _normalize(request)
    _validate(req)
    adapter = ADAPTERS.get(req["model"])
    if adapter is None:
        raise ValueError(f"unknown model {req['model']!r} (have {sorted(ADAPTERS)})")
    return adapter.generate(req, project_dir)
