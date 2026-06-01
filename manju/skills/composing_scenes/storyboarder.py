"""composing_scenes (Phase 2, Layer-2 item 2) — the storyboard / keyframe-still layer.

For each SHOT this reads the BRAIN-owned plan (景别 shot_size / 运镜 movement /
lens_mm / action / ref_ids) + the LOCKED ref images of the referenced assets, and
emits a per-shot storyboard spec with the background and the character(s) as
SEPARATED layers, a 9宫格 (3×3 rule-of-thirds) composition block, and a literal
keyframe still composited with ffmpeg (the i2v seed image: keyframe still →
image-to-video).

Layer policy (deterministic, keyed by 景别 shot_size, ramped by 运镜 movement):
  scene asset            → the `background` layer
  character/villain/prop → a `characters[]` layer, each with placement {x,y,scale,z}
  placement (x,y in [0,1] normalized canvas coords; scale = fraction of canvas
  height the subject occupies; z = paint order) is derived from shot_size so a
  近景/close-up puts the subject large & centered while a 全景/wide makes it small
  with more background. 运镜 push-in (推进) adds a scale-ramp hint.

Reads:  shots[].plan (camera{shot_size,movement,lens_mm}, action, ref_ids), the ref
        assets' run.ref_image_paths (locked sheets).
Writes: NOTHING in the ledger (plan.* / run.* are owned by brain/overlord). Emits
        only artifacts under projects/<n>/storyboard/<ep>/<sc>/:
          shot_NN.spec.json    — separated layers + nine_grid + keyframe_still path
          shot_NN.keyframe.png  — the composited i2v seed still

Public:
  storyboard_shot(ledger, shot_id, project_dir) -> dict   # the spec (also written)
  storyboard_all(ledger, project_dir)           -> dict   # {shot_id: spec, ...}

stdlib only + ffmpeg (compositing). Idempotent + skip-if-exists. Tolerant of
not-yet-locked refs: a shot with no usable refs still gets a spec (no still).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# canvas the keyframe still is composited onto (16:9, matches the runner default).
CANVAS_W = 1280
CANVAS_H = 720

# 景别 (shot_size) → subject layout policy. scale = subject height as a fraction of
# the canvas height; (cx, cy) = subject centre in normalized [0,1] coords. Wider
# shots → smaller subject + more background; tighter shots → larger & higher.
# Keys are matched by substring so synonyms (大远景/远景, 中近景, …) still resolve.
_SHOT_SIZE_POLICY: dict[str, dict] = {
    "大远景": {"scale": 0.22, "cx": 0.5, "cy": 0.72},
    "远景":   {"scale": 0.30, "cx": 0.5, "cy": 0.70},
    "全景":   {"scale": 0.42, "cx": 0.5, "cy": 0.66},
    "中景":   {"scale": 0.62, "cx": 0.5, "cy": 0.60},
    "中近景": {"scale": 0.74, "cx": 0.5, "cy": 0.56},
    "近景":   {"scale": 0.86, "cx": 0.5, "cy": 0.50},
    "特写":   {"scale": 1.05, "cx": 0.5, "cy": 0.46},
    "大特写": {"scale": 1.25, "cx": 0.5, "cy": 0.44},
}
# substring match order: longest/most-specific keys first so 中近景 beats 中景/近景.
_SIZE_KEYS = sorted(_SHOT_SIZE_POLICY, key=len, reverse=True)
_DEFAULT_POLICY = {"scale": 0.6, "cx": 0.5, "cy": 0.58}

# 运镜 (movement) → a scale-ramp hint over the shot's duration (start→end factor on
# the subject scale). push-in grows the subject; pull-out shrinks it; the rest hold.
_MOVEMENT_RAMP: list[tuple[tuple[str, ...], tuple[float, float]]] = [
    (("推进", "推近", "push", "推镜", "推"), (0.88, 1.12)),   # push-in: subject grows
    (("拉远", "拉镜", "pull", "拉"),         (1.12, 0.88)),   # pull-out: subject shrinks
]


def _resolve_policy(shot_size: str) -> dict:
    """Pick the layout policy for a 景别 by longest-substring match (else default)."""
    s = shot_size or ""
    for key in _SIZE_KEYS:
        if key in s:
            return dict(_SHOT_SIZE_POLICY[key])
    return dict(_DEFAULT_POLICY)


def _scale_ramp(movement: str) -> dict:
    """Subject scale ramp {start,end} derived from 运镜 (运镜 push-in → grows)."""
    m = movement or ""
    for needles, (start, end) in _MOVEMENT_RAMP:
        if any(n in m for n in needles):
            return {"start": start, "end": end}
    return {"start": 1.0, "end": 1.0}


# ── 9宫格 (rule-of-thirds) ─────────────────────────────────────────────────────
_THIRDS = (1.0 / 3.0, 2.0 / 3.0)


def _nearest_third(v: float) -> float:
    """Snap a normalized coord to the nearer rule-of-thirds line (1/3 or 2/3)."""
    return min(_THIRDS, key=lambda t: abs(t - v))


def _grid_cell(cx: float, cy: float) -> int:
    """Row-major 3×3 cell index (0..8) the subject centre falls in."""
    col = 0 if cx < 1 / 3 else (1 if cx < 2 / 3 else 2)
    row = 0 if cy < 1 / 3 else (1 if cy < 2 / 3 else 2)
    return row * 3 + col


def _nine_grid(cx: float, cy: float) -> dict:
    """The 9宫格 composition block: rule-of-thirds anchor for the subject."""
    ax, ay = _nearest_third(cx), _nearest_third(cy)
    return {
        "convention": "9宫格 (rule-of-thirds, micro-drama)",
        "grid": [3, 3],
        "thirds_x": list(_THIRDS),
        "thirds_y": list(_THIRDS),
        "subject_anchor": {"x": round(ax, 4), "y": round(ay, 4)},
        "subject_cell": _grid_cell(cx, cy),  # 0..8 row-major (4 = centre)
        "intersections": [{"x": round(x, 4), "y": round(y, 4)}
                          for y in _THIRDS for x in _THIRDS],
    }


# ── ref gathering ──────────────────────────────────────────────────────────────
def _ref_asset_ids(shot: dict) -> list[str]:
    """Referenced asset ids: plan.ref_ids, falling back to asset deps (no-dot ids)."""
    ids = list(shot.get("plan", {}).get("ref_ids", []) or [])
    if not ids:
        ids = [d for d in shot.get("deps", []) if "." not in d]
    return ids


def _first_image(asset: dict) -> str | None:
    """The first locked ref image of an asset that exists on disk (else None)."""
    for p in asset.get("run", {}).get("ref_image_paths", []) or []:
        if p and os.path.isfile(p):
            return p
    return None


def _is_scene(asset: dict) -> bool:
    return asset.get("kind") == "scene"


# ── path helpers ───────────────────────────────────────────────────────────────
def _shot_path_parts(shot_id: str) -> tuple[str, str, str]:
    """ep01.sc01.sh01 -> ('ep01', 'sc01', 'shot_01')."""
    ep, sc, sh = shot_id.split(".")
    return ep, sc, f"shot_{sh.replace('sh', '')}"


def _storyboard_dir(project_dir: str, shot_id: str) -> str:
    ep, sc, _ = _shot_path_parts(shot_id)
    return os.path.join(project_dir, "storyboard", ep, sc)


def _log(msg: str) -> None:
    print(f"[composing_scenes] {msg}", file=sys.stderr)


# ── keyframe still compositing (ffmpeg) ────────────────────────────────────────
def _png_ok(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def _compose_keyframe(background: str | None, characters: list[dict], out_path: str) -> bool:
    """Composite the character ref(s) over the scene-ref background → out_path (PNG).

    Background is scaled to cover the 16:9 canvas; each character ref is scaled to its
    layer `scale` (fraction of canvas height) and overlaid at its (x,y) centre, in z
    order. No scene ref → the character alone on a black canvas. No refs at all → skip
    (returns False; the spec is still emitted). Idempotent: skip-if-exists.
    """
    chars = [c for c in characters if c.get("image") and os.path.isfile(c["image"])]
    if background is None and not chars:
        return False  # nothing to composite — caller emits the spec without a still
    if _png_ok(out_path):
        return True  # skip-if-exists (a reused composite)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    inputs: list[str] = []
    parts: list[str] = []

    # base canvas: the scaled+cropped background, or a solid black 16:9 plate.
    if background is not None:
        inputs += ["-i", background]
        parts.append(
            f"[0:v]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
            f"crop={CANVAS_W}:{CANVAS_H},setsar=1[bg]"
        )
        base = "bg"
        idx = 1
    else:
        inputs += ["-f", "lavfi", "-i", f"color=c=black:s={CANVAS_W}x{CANVAS_H}"]
        parts.append("[0:v]setsar=1[bg]")
        base = "bg"
        idx = 1

    # paint characters bottom-anchored at their (x,y) centre in z order.
    cur = base
    for c in sorted(chars, key=lambda c: c.get("z", 0)):
        inputs += ["-i", c["image"]]
        h = max(1, int(round(CANVAS_H * float(c["scale"]))))
        cx, cy = float(c["x"]), float(c["y"])
        slabel = f"c{idx}"
        # scale by height, preserve aspect; centre at (cx,cy) on the canvas.
        parts.append(f"[{idx}:v]scale=-1:{h}[{slabel}]")
        x_expr = f"{cx}*{CANVAS_W}-overlay_w/2"
        y_expr = f"{cy}*{CANVAS_H}-overlay_h/2"
        nxt = f"o{idx}"
        parts.append(f"[{cur}][{slabel}]overlay=x='{x_expr}':y='{y_expr}'[{nxt}]")
        cur = nxt
        idx += 1

    filtergraph = ";".join(parts)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", filtergraph, "-map", f"[{cur}]",
           "-frames:v", "1", out_path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not _png_ok(out_path):
        _log(f"keyframe composite failed for {out_path}: {res.stderr[-500:]}")
        return False
    return True


# ── the storyboarder ───────────────────────────────────────────────────────────
def storyboard_shot(ledger, shot_id: str, project_dir: str) -> dict:
    """Build (and write) the storyboard spec + keyframe still for one shot.

    Returns the spec dict. Idempotent: re-running reuses an existing keyframe.png and
    overwrites the spec.json with the same content. Tolerant of unlocked refs — a shot
    whose refs are not yet on disk still gets a spec (keyframe_still=None).
    """
    shot = ledger.node(shot_id)
    plan = shot.get("plan", {})
    cam = plan.get("camera", {}) or {}
    shot_size = cam.get("shot_size", "")
    movement = cam.get("movement", "")

    policy = _resolve_policy(shot_size)
    ramp = _scale_ramp(movement)

    # split referenced assets into the scene (background) and the characters.
    background_layer: dict | None = None
    bg_image: str | None = None
    character_layers: list[dict] = []
    z = 1
    for aid in _ref_asset_ids(shot):
        try:
            asset = ledger.node(aid)
        except KeyError:
            continue
        img = _first_image(asset)
        if _is_scene(asset):
            if background_layer is None:
                background_layer = {
                    "role": "background",
                    "asset_id": aid,
                    "ref_tag": asset.get("run", {}).get("ref_tag") or f"@{aid}",
                    "image": img,
                    "placement": {"x": 0.5, "y": 0.5, "scale": 1.0, "z": 0},
                    "locked": asset.get("run", {}).get("ref_status") == "locked",
                }
                bg_image = img
        else:
            character_layers.append({
                "role": "character",
                "asset_id": aid,
                "ref_tag": asset.get("run", {}).get("ref_tag") or f"@{aid}",
                "image": img,
                "placement": {
                    "x": round(policy["cx"], 4),
                    "y": round(policy["cy"], 4),
                    "scale": round(policy["scale"], 4),
                    "z": z,
                    "scale_ramp": ramp,   # 运镜-derived start→end scale hint
                },
                "locked": asset.get("run", {}).get("ref_status") == "locked",
            })
            z += 1

    # the 9宫格 anchor follows the (primary) subject centre, else canvas centre.
    if character_layers:
        cx, cy = policy["cx"], policy["cy"]
    else:
        cx, cy = 0.5, 0.5

    sb_dir = _storyboard_dir(project_dir, shot_id)
    _, _, name = _shot_path_parts(shot_id)
    keyframe_path = os.path.join(sb_dir, f"{name}.keyframe.png")

    # composite the literal keyframe still (the i2v seed). char layers carry x/y/scale.
    comp_chars = [
        {"image": c["image"], "x": c["placement"]["x"], "y": c["placement"]["y"],
         "scale": c["placement"]["scale"], "z": c["placement"]["z"]}
        for c in character_layers if c["image"]
    ]
    has_still = _compose_keyframe(bg_image, comp_chars, keyframe_path)

    spec = {
        "version": "1.0.0",
        "shot_id": shot_id,
        "canvas": {"width": CANVAS_W, "height": CANVAS_H, "aspect_ratio": "16:9"},
        "camera": {"shot_size": shot_size, "movement": movement,
                   "lens_mm": cam.get("lens_mm")},
        "layout_policy": {"keyed_by": "shot_size", "shot_size": shot_size,
                          **policy, "scale_ramp": ramp},
        "layers": {
            "background": background_layer,   # the scene ref (separated layer)
            "characters": character_layers,   # each char ref (separated layers)
        },
        "nine_grid": _nine_grid(cx, cy),
        "keyframe_still": keyframe_path if has_still else None,
        "is_i2v_seed": bool(has_still),
    }

    os.makedirs(sb_dir, exist_ok=True)
    spec_path = os.path.join(sb_dir, f"{name}.spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    spec["spec_path"] = spec_path
    return spec


def storyboard_all(ledger, project_dir: str) -> dict:
    """Storyboard every shot whose refs are ready (tolerant of not-yet-locked refs).

    Idempotent + skip-if-exists (per-shot). Returns {shot_id: spec}. Safe to call per
    tick: a shot with no usable ref images yet still gets a spec (no keyframe still)
    and will gain the still once its refs lock and it is re-storyboarded.
    """
    out: dict[str, dict] = {}
    for shot in ledger.nodes(kind="shot"):
        out[shot["id"]] = storyboard_shot(ledger, shot["id"], project_dir)
    return out


def keyframe_for(project_dir: str, shot_id: str) -> str | None:
    """The keyframe still path for a shot if it exists on disk (the i2v seed), else None.

    The builder seam (building_prompts.request_for_shot) calls this to decide whether a
    storyboard keyframe should anchor the i2v request as its primary reference image.
    """
    _, _, name = _shot_path_parts(shot_id)
    path = os.path.join(_storyboard_dir(project_dir, shot_id), f"{name}.keyframe.png")
    return path if _png_ok(path) else None
