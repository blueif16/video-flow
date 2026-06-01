"""building_prompts (CONTRACTS §5) — the 5-part time-coded prompt builder.

Reads a SHOT's plan (intent + dialogue + action + camera + style_id) and the
referenced assets' bible plan (固定特征词 / 禁止变化项 / ref_tag), and emits the
canonical prompt:

  Subject · Action · Camera · Style · Constraints

with time-coded [00:00-00:0X] blocks spanning duration_s, and the negative-prompt
floor expressed as POSITIVE constraints (style.negative_floor + each referenced
asset's 禁止变化项). 固定特征词 and each ref's @ref_tag are injected so generation
stays anchored to the bible.

Public:
  build_prompt(ledger, shot_id, model="mock") -> str
  write_prompt(ledger, shot_id, project_dir, model="mock") -> str   # path
  request_for_shot(ledger, shot_id, project_dir, seed, model="mock") -> dict
"""
from __future__ import annotations

import os

# ── composing_scenes seam (CONTRACTS §6) — a missing module never breaks the builder.
# If a storyboard keyframe still exists for a shot, it is the i2v seed image (the
# keyframe the video is generated FROM) and anchors the request as the PRIMARY ref.
try:
    from manju.skills.composing_scenes.storyboarder import keyframe_for as _keyframe_for
except Exception:  # noqa: BLE001 — module absent / import error: keep current behavior
    _keyframe_for = None


# ── style lookup ──────────────────────────────────────────────────────────────
def _style(ledger, style_id: str) -> dict:
    for s in ledger.doc.get("styles", []):
        if s.get("id") == style_id:
            return s
    return {}


def _ref_asset_ids(shot: dict) -> list[str]:
    """Referenced assets for a shot: plan.ref_ids, falling back to asset deps."""
    plan = shot.get("plan", {})
    ids = list(plan.get("ref_ids", []) or [])
    if not ids:
        ids = [d for d in shot.get("deps", []) if "." not in d]  # asset ids have no dots
    return ids


# ── time-coded action blocks ──────────────────────────────────────────────────
def _time_blocks(action: str, duration_s: int) -> list[str]:
    """Split the action across [00:00-00:0X] slices spanning duration_s.

    Up to 3 beats; each beat gets an equal time slice. With a single beat the whole
    duration is one block. Ensures at least one [00:00-...] block always appears.
    """
    dur = max(int(duration_s or 1), 1)
    # beats: split the action on Chinese/Latin sentence punctuation
    beats = [b.strip() for b in _split_beats(action) if b.strip()] or [action.strip() or "—"]
    beats = beats[:3]
    n = len(beats)
    blocks = []
    for i, beat in enumerate(beats):
        start = round(dur * i / n)
        end = round(dur * (i + 1) / n)
        blocks.append(f"[{_mmss(start)}-{_mmss(end)}] {beat}")
    return blocks


def _split_beats(action: str) -> list[str]:
    out, cur = [], []
    for ch in action or "":
        cur.append(ch)
        if ch in "，。,.；;":
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _mmss(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


# ── per-model phrasing hook (mock = identity) ─────────────────────────────────
def _model_adapt(text: str, model: str) -> str:
    """Small per-model phrasing tweak. mock = identity; real models can override."""
    return text


# ── the builder ───────────────────────────────────────────────────────────────
def build_prompt(ledger, shot_id: str, model: str = "mock") -> str:
    """Assemble the 5-part time-coded prompt for a shot (str)."""
    shot = ledger.node(shot_id)
    plan = shot.get("plan", {})
    style_id = plan.get("style_id", "")
    style = _style(ledger, style_id)
    cam = plan.get("camera", {}) or {}

    ref_ids = _ref_asset_ids(shot)
    ref_tags: list[str] = []
    fixed_words: list[str] = []        # 固定特征词
    forbidden: list[str] = []          # 禁止变化项
    subjects: list[str] = []
    for aid in ref_ids:
        try:
            asset = ledger.node(aid)
        except KeyError:
            continue
        ap, ar = asset.get("plan", {}), asset.get("run", {})
        tag = ar.get("ref_tag") or f"@{aid}"
        ref_tags.append(tag)
        desc = ap.get("descriptor", aid)
        subjects.append(f"{tag} ({desc})")
        fixed_words += ap.get("固定特征词", []) or []
        forbidden += ap.get("禁止变化项", []) or []

    # ── Subject ──
    subject_line = "; ".join(subjects) if subjects else (plan.get("intent", "") or "subject")
    fixed_line = ("固定特征词: " + ", ".join(_dedupe(fixed_words))) if fixed_words else ""

    # ── Action (time-coded) ──
    blocks = _time_blocks(plan.get("action", ""), plan.get("duration_s", 1))

    # ── Camera ──
    cam_bits = [b for b in (cam.get("shot_size"), cam.get("movement")) if b]
    if cam.get("lens_mm"):
        cam_bits.append(f"{cam['lens_mm']}mm")
    camera_line = "景别/运镜: " + ", ".join(cam_bits) if cam_bits else "景别/运镜: 标准"

    # ── Style ──
    style_bits = []
    if style.get("descriptor"):
        style_bits.append(style["descriptor"])
    if style.get("film_vocabulary"):
        style_bits.append("film: " + ", ".join(style["film_vocabulary"]))
    style_line = " | ".join(style_bits) if style_bits else (style_id or "default style")

    # ── Constraints (negative floor as POSITIVE constraints) ──
    floor = style.get("negative_floor", []) or []
    constraints: list[str] = []
    if floor:
        constraints.append("avoid: " + ", ".join(floor))
    if forbidden:
        constraints.append("keep consistent (禁止变化项): " + ", ".join(_dedupe(forbidden)))

    # ── assemble ──
    lines = ["Subject: " + subject_line]
    if fixed_line:
        lines.append(fixed_line)
    if ref_tags:
        lines.append("references: " + " ".join(ref_tags))
    lines.append("")
    lines.append("Action:")
    lines += ["  " + b for b in blocks]
    lines.append("")
    lines.append("Camera: " + camera_line)
    lines.append("Style: " + style_line)
    if plan.get("dialogue"):
        lines.append('Dialogue: "' + plan["dialogue"] + '"')
    lines.append("Constraints: " + " | ".join(constraints) if constraints else "Constraints: —")

    return _model_adapt("\n".join(lines), model)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ── writer ────────────────────────────────────────────────────────────────────
def _shot_path_parts(shot_id: str) -> tuple[str, str, str]:
    """ep01.sc01.sh01 -> ('ep01', 'sc01', 'shot_01')."""
    ep, sc, sh = shot_id.split(".")
    num = sh.replace("sh", "")
    return ep, sc, f"shot_{num}"


def write_prompt(ledger, shot_id: str, project_dir: str, model: str = "mock") -> str:
    """Write the prompt to projects/<n>/prompts/<ep>/<sc>/shot_NN.txt and return the path."""
    ep, sc, name = _shot_path_parts(shot_id)
    out_dir = os.path.join(project_dir, "prompts", ep, sc)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_prompt(ledger, shot_id, model) + "\n")
    return path


# ── canonical runner request for a shot ───────────────────────────────────────
def request_for_shot(ledger, shot_id: str, project_dir: str, seed: int, model: str = "mock") -> dict:
    """Assemble the canonical generating-runner request for a shot.

    Gathers the 5-part prompt + the referenced assets' ref images + camera/duration
    so the shot-generation path is one call:  run_request(request_for_shot(...), ...).
    A shot is generated as a `video` (i2v: anchored on the refs' images).
    """
    shot = ledger.node(shot_id)
    plan = shot.get("plan", {})

    # gather referenced assets' locked ref images as image anchors (i2v)
    asset_refs: list[str] = []
    for aid in _ref_asset_ids(shot):
        try:
            asset = ledger.node(aid)
        except KeyError:
            continue
        asset_refs += asset.get("run", {}).get("ref_image_paths", []) or []

    # storyboard keyframe still → the PRIMARY (first) reference image (the keyframe
    # the video is generated FROM), with the asset refs following. No keyframe ⇒ the
    # current behavior exactly (anchor on the ref images). Seam-guarded: a missing
    # composing_scenes module leaves _keyframe_for None and changes nothing.
    keyframe = _keyframe_for(project_dir, shot_id) if _keyframe_for is not None else None
    ordered = ([keyframe] if keyframe else []) + asset_refs
    reference_images = _dedupe(ordered)[:9]

    return {
        "kind": "video",
        "prompt": build_prompt(ledger, shot_id, model),
        "reference_images": reference_images,
        "reference_videos": [],
        "reference_audios": [],
        "duration_s": plan.get("duration_s", 4),
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "generate_audio": bool(plan.get("dialogue")),
        "seed": seed,
        "model": model,
        "node_id": shot_id,
    }
