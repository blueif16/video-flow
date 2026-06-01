"""Mock provider (V1 default, deterministic).

Content-addresses the normalized request to an attempt_id, places the output at
the content-addressed artifact path, and copies the matching sample asset. It is
the reference implementation of the adapter interface:

    generate(req: dict, project_dir: str) -> envelope

`req` is the canonical, validated request plus the runner-injected `_node_id`.
The envelope is {"model","output_files":[abs...],"data":{...}}.

Determinism + reuse:
- attempt_id = sha256(canonical_json(normalized_request)); same request -> same path.
- skip-if-exists: if the output path already exists we return it WITHOUT copying.
  An existing path IS a reused generation (CONTRACTS §1.6).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess

from manju.ledger import artifact_path

# repo root: .../manju/skills/generating/adapters/mock.py -> up 4
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_SAMPLE_DIR = os.path.join(_REPO_ROOT, "assets", "sample")

# canonical-request kind -> (sample asset, output extension)
_KIND_SAMPLE = {"image": ("ref_face.png", "png"), "video": ("shot.mp4", "mp4")}

# the take-identity schema: hashing canonicalizes onto these keys with these defaults
# so a request hashes identically whether default-valued keys are present or absent
# (lets the real runner and the neighbor stub agree on the content-addressed path).
# `_node_id` is excluded: it already scopes the artifact directory (artifacts/<node_id>/).
_HASH_SCHEMA = {
    "kind": None, "prompt": None,
    "reference_images": [], "reference_videos": [], "reference_audios": [],
    "duration_s": None, "resolution": None, "aspect_ratio": None,
    "generate_audio": False, "seed": None, "model": "mock",
}


def attempt_id_for(req: dict) -> str:
    """Stable content hash of the canonicalized request (the take's identity)."""
    canon = {k: req.get(k, default) for k, default in _HASH_SCHEMA.items()}
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _make_image_thumb(src: str, dst: str) -> None:
    # downscale to max 320 wide, keep aspect
    _ffmpeg(["-i", src, "-vf", "scale=320:-1", dst])


def _make_video_thumb(src: str, dst: str) -> None:
    # first frame, downscaled
    _ffmpeg(["-i", src, "-frames:v", "1", "-vf", "scale=320:-1", dst])


def _probe(src: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", src],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.stdout)


def generate(req: dict, project_dir: str) -> dict:
    """Produce (or reuse) the deterministic mock artifact + thumb (+ probe for video)."""
    kind = req["kind"]
    node_id = req.get("_node_id") or f"_loose/{attempt_id_for(req)[:12]}"
    attempt_id = attempt_id_for(req)

    sample_name, ext = _KIND_SAMPLE[kind]
    out_path = artifact_path(project_dir, node_id, attempt_id, ext)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    reused = os.path.exists(out_path)
    if not reused:
        shutil.copyfile(os.path.join(_SAMPLE_DIR, sample_name), out_path)

    # thumb lives next to the artifact, also content-addressed (skip-if-exists)
    thumb_path = artifact_path(project_dir, node_id, f"{attempt_id}.thumb", "png")
    if not os.path.exists(thumb_path):
        if kind == "image":
            _make_image_thumb(out_path, thumb_path)
        else:
            _make_video_thumb(out_path, thumb_path)

    data: dict = {
        "attempt_id": attempt_id,
        "node_id": node_id,
        "kind": kind,
        "thumb_path": thumb_path,
        "seed": req.get("seed"),
        "reused": reused,
    }

    if kind == "video":
        probe_path = artifact_path(project_dir, node_id, f"{attempt_id}.probe", "json")
        if not os.path.exists(probe_path):
            with open(probe_path, "w", encoding="utf-8") as f:
                json.dump(_probe(out_path), f, ensure_ascii=False, indent=2)
        data["probe_path"] = probe_path
        with open(probe_path, encoding="utf-8") as f:
            data["probe"] = json.load(f)

    return {"model": "mock", "output_files": [out_path], "data": data}
