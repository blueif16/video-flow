"""The stateless judge (CONTRACTS §4, Layer 3).

Two halves, cleanly split so the control plane CANNOT fake quality:

  build_context_sheet(ledger, node_id, project_dir) -> dict
      assembles the judge's entire input FROM THE LEDGER ONLY (replayable):
      intent + the actual prompt used, the rubric verbatim, prior lessons,
      ref_role_map + bible reference image paths, and the artifact(s).
      - image: generated image + bible ref image(s).
      - video: a 3x3 keyframe contact-sheet (9 frames at slice-centers
        t = dur*(k+0.5)/n) + first+last frame + probe.json, built with ffmpeg.

  JUDGE(sheet) -> verdict
      ONE stateless inference per artifact. V1 is a deterministic MOCK that is
      perception-SHAPED but code-deterministic. A JUDGE_BACKEND indirection
      (mock | gemini | claude) makes a real vision model a one-config swap;
      gemini/claude are STUBS that raise until a key is wired.

Standard library only + ffmpeg/ffprobe. No pip installs.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Optional

# ── style/景别 → rubric file resolution ───────────────────────────────────────
_RUBRIC_DIR = os.path.join(os.path.dirname(__file__), "rubrics")

# 景别 (shot_size) → rubric filename stem. Anything unmapped falls back to default.
_SHOT_TYPE_BY_SIZE = {
    "近景": "close_up",
    "特写": "close_up",
    "中近景": "close_up",
    "全景": "wide",
    "远景": "wide",
    "大全景": "wide",
}

# contact-sheet geometry: 3x3 grid of slice-center keyframes.
_GRID = 3
_N_FRAMES = _GRID * _GRID  # 9


# ── rubric loading ────────────────────────────────────────────────────────────
def _shot_type_for(node: dict, kind: str) -> str:
    """Map a node to its rubric shot_type stem. Assets use 'default'."""
    if kind == "asset":
        return "default"
    size = (node.get("plan", {}).get("camera", {}) or {}).get("shot_size", "")
    return _SHOT_TYPE_BY_SIZE.get(size, "default")


def load_rubric(style_id: str, shot_type: str) -> dict:
    """Load rubrics/<style>/<shot_type>.json verbatim; fall back to default.json.

    Returns the rubric dict plus a `_rubric_path` breadcrumb (which file was read).
    """
    for stem in (shot_type, "default"):
        path = os.path.join(_RUBRIC_DIR, style_id, f"{stem}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rubric = json.load(f)
            rubric["_rubric_path"] = path
            return rubric
    # no rubric on disk for this style — a minimal inline floor so the judge still runs.
    return {
        "style_id": style_id,
        "shot_type": shot_type,
        "pass_threshold": 0.72,
        "axes": [],
        "negative_floor": [],
        "_rubric_path": None,
        "_missing": True,
    }


# ── ffmpeg helpers (video contact-sheet) ──────────────────────────────────────
def _ffprobe_duration(src: str) -> float:
    """Best-effort clip duration in seconds via ffprobe (0.0 on failure)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", src],
            check=True, capture_output=True, text=True,
        )
        return float(json.loads(out.stdout).get("format", {}).get("duration", 0.0))
    except Exception:  # noqa: BLE001 — probe is advisory
        return 0.0


def _probe_json(src: str) -> dict:
    """Full ffprobe streams+format (the judge's probe.json)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", src],
            check=True, capture_output=True, text=True,
        )
        return json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return {"streams": [], "format": {}}


def _extract_frame(src: str, t: float, dst: str) -> bool:
    """Extract a single frame at time t (seconds) to dst. True on success."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", src,
             "-frames:v", "1", "-q:v", "3", dst],
            check=True,
        )
        return os.path.exists(dst)
    except Exception:  # noqa: BLE001
        return False


def build_contact_sheet(src_video: str, out_png: str, duration_s: Optional[float] = None) -> dict:
    """Build a 3x3 keyframe contact-sheet PNG from src_video.

    9 frames at slice-centers t = dur*(k+0.5)/n, tiled 3x3 (montage via ffmpeg
    tile filter). Returns {contact_sheet, first_frame, last_frame, slice_times}.
    Frames are written next to out_png in a sibling tmp dir, then tiled.
    """
    dur = duration_s if (duration_s and duration_s > 0) else _ffprobe_duration(src_video)
    if not dur or dur <= 0:
        dur = 4.0  # safe default so the sheet always builds (mock sample is short)

    base = os.path.splitext(out_png)[0]
    frame_dir = base + "_frames"
    os.makedirs(frame_dir, exist_ok=True)

    slice_times = [dur * (k + 0.5) / _N_FRAMES for k in range(_N_FRAMES)]
    frame_paths = []
    for k, t in enumerate(slice_times):
        fp = os.path.join(frame_dir, f"f{k:02d}.png")
        if not os.path.exists(fp):
            _extract_frame(src_video, t, fp)
        frame_paths.append(fp)

    # tile the 9 frames into one 3x3 PNG. Concat-demuxer feeds them in order.
    listfile = os.path.join(frame_dir, "frames.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for fp in frame_paths:
            if os.path.exists(fp):
                f.write(f"file '{os.path.abspath(fp)}'\n")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", listfile, "-vf", f"scale=320:-1,tile={_GRID}x{_GRID}",
             "-frames:v", "1", out_png],
            check=True,
        )
    except Exception:  # noqa: BLE001 — sheet is best-effort; first/last still useful
        pass

    # first + last frame (continuity endpoints).
    first_frame = base + "_first.png"
    last_frame = base + "_last.png"
    _extract_frame(src_video, 0.0, first_frame)
    _extract_frame(src_video, max(dur - 0.05, 0.0), last_frame)

    return {
        "contact_sheet": out_png if os.path.exists(out_png) else None,
        "first_frame": first_frame if os.path.exists(first_frame) else None,
        "last_frame": last_frame if os.path.exists(last_frame) else None,
        "slice_times": [round(t, 3) for t in slice_times],
        "grid": f"{_GRID}x{_GRID}",
        "n_frames": _N_FRAMES,
        "duration_s": round(dur, 3),
    }


# ── ref-role map (drift-comparison inputs) ────────────────────────────────────
def _ref_role_map(ledger, node: dict, kind: str) -> tuple[dict, list[str]]:
    """Build "[Image1]=face" role labels + the bible reference image paths.

    Drift inputs come from referencing: each ref asset exposes ref_image_paths +
    禁止变化项. We label the FIRST reference image of each ref asset (Image1, ...).
    """
    role_map: dict[str, str] = {}
    ref_paths: list[str] = []
    if kind == "asset":
        ref_ids = [node["id"]]  # an asset is judged against its own draft vs bible intent
    else:
        ref_ids = node.get("plan", {}).get("ref_ids", []) or node.get("deps", [])

    idx = 1
    for rid in ref_ids:
        try:
            ref_node = ledger.node(rid)
        except KeyError:
            continue
        if ledger._index[rid][1] != "asset":  # only assets carry reference images
            continue
        rk = ref_node.get("kind", "ref")
        imgs = ref_node.get("run", {}).get("ref_image_paths", []) or []
        forbidden = ref_node.get("plan", {}).get("禁止变化项", [])
        if imgs:
            role_map[f"[Image{idx}]"] = f"{rk}:{rid}"
            ref_paths.append(imgs[0])
            idx += 1
        # even with no locked image yet, surface the forbidden-change list for the judge.
        role_map.setdefault(f"<{rid}>", {"kind": rk, "禁止变化项": forbidden})
    return role_map, ref_paths


# ── the context-sheet (assembled FROM THE LEDGER ONLY) ────────────────────────
def build_context_sheet(ledger, node_id: str, project_dir: str) -> dict:
    """Assemble the stateless judge's input for one node. Replayable; ledger-only.

    Returns a dict with: node_id, kind, modality, intent, prompt, rubric (verbatim),
    prior_lessons, ref_role_map, ref_image_paths, artifact, attempt (1-based), and
    for video a contact_sheet block (3x3 PNG + first/last + probe).
    """
    node = ledger.node(node_id)
    kind = ledger._index[node_id][1]  # "asset" | "shot"
    plan = node.get("plan", {})
    run = node.get("run", {})

    attempts = run.get("attempts", [])
    attempt_n = len(attempts)  # 1-based count of takes so far
    last = attempts[-1] if attempts else {}

    artifact = run.get("current_artifact") or {}
    artifact_path = artifact.get("path") or last.get("artifact_path")

    # modality: assets draw images; shots default to video (i2v) per the pipeline.
    if kind == "asset":
        modality = "image"
    else:
        modality = "image" if (artifact_path or "").lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp")) else "video"

    style_id = plan.get("style_id", "")
    shot_type = _shot_type_for(node, kind)
    rubric = load_rubric(style_id, shot_type)

    model = last.get("model", "mock")
    asset_kind = node.get("kind") if kind == "asset" else None
    category = shot_type if kind == "shot" else "drift"
    scope = {"category": category, "model": model, "style_id": style_id}
    if asset_kind:
        scope["asset_kind"] = asset_kind
    prior_lessons = ledger.lessons_for(scope)

    role_map, ref_paths = _ref_role_map(ledger, node, kind)

    sheet: dict[str, Any] = {
        "node_id": node_id,
        "kind": kind,
        "modality": modality,
        "attempt": attempt_n,
        "intent": plan.get("intent") or plan.get("descriptor", ""),
        "prompt": last.get("prompt", ""),
        "seed": last.get("seed"),
        "model": model,
        "rubric": rubric,
        "prior_lessons": prior_lessons,
        "ref_role_map": role_map,
        "ref_image_paths": ref_paths,
        "禁止变化项": plan.get("禁止变化项", []),
        "固定特征词": plan.get("固定特征词", []),
        "artifact": {"path": artifact_path, "attempt_id": artifact.get("attempt_id")},
    }

    if modality == "video" and artifact_path and os.path.exists(artifact_path):
        attempt_id = artifact.get("attempt_id") or last.get("attempt_id") or "sheet"
        sheets_dir = os.path.join(project_dir, "judge_sheets", node_id)
        os.makedirs(sheets_dir, exist_ok=True)
        out_png = os.path.join(sheets_dir, f"{attempt_id}.contact.png")
        duration_s = plan.get("duration_s")
        cs = build_contact_sheet(artifact_path, out_png, duration_s)
        # probe.json — reuse the runner's probe if it left one, else generate.
        probe_path = os.path.splitext(artifact_path)[0] + ".probe.json"
        if os.path.exists(probe_path):
            with open(probe_path, encoding="utf-8") as f:
                cs["probe"] = json.load(f)
        else:
            cs["probe"] = _probe_json(artifact_path)
        sheet["contact_sheet"] = cs

    return sheet


# ── JUDGE_BACKEND indirection (mock | gemini | claude) ────────────────────────
JUDGE_BACKEND = os.environ.get("MANJU_JUDGE_BACKEND", "mock")

# A specific node is SEEDED to fail its first attempt(s) so the re-roll / lesson /
# drift / escalation paths are all demonstrably exercised by the self-test. Format:
#   node_id -> {"until_attempt": int, "failure_mode": str, "drift": bool}
# the node FAILS while attempt <= until_attempt, then PASSES. drift=True routes to
# the ref-regen path. Everything else defaults to a high-scoring pass.
SEEDED_FAILURES: dict[str, dict] = {
    # close-up shot: fails attempt 1 as a generic 'fail' (off-prompt), then passes →
    # exercises lesson append + re-roll + eventual pass.
    "ep01.sc01.sh02": {"until_attempt": 1, "failure_mode": "off-prompt", "drift": False},
}

# A node seeded to emit a DRIFT verdict on its first attempt → exercises the
# ref-regen / blocked_on_ref path. Kept separate so a test can opt a node in.
SEEDED_DRIFT: dict[str, dict] = {
    # wide establishing shot: drift on attempt 1 (its ref drifted), then passes.
    "ep01.sc01.sh01": {"until_attempt": 1, "failure_mode": "drift"},
}


def _pseudo_score(node_id: str, attempt: int, prompt: str) -> float:
    """Stable pseudo-score in [0,1) from a hash of (node_id, attempt, prompt).

    Deterministic: same inputs → same score. Used only to SHAPE the mock like a
    perception model (a real judge returns a real score here).
    """
    h = hashlib.sha256(f"{node_id}|{attempt}|{prompt}".encode("utf-8")).hexdigest()
    return (int(h[:8], 16) % 1000) / 1000.0


def _judge_mock(sheet: dict) -> dict:
    """Deterministic MOCK judge — perception-SHAPED, code-deterministic.

    Defaults artifacts to a high-scoring `pass`. SEEDED nodes fail (one as a
    generic fail, one as drift) on early attempts then pass, so the re-roll,
    lesson, drift and escalation paths are all hit by the self-test.
    """
    node_id = sheet["node_id"]
    attempt = sheet.get("attempt", 1)
    prompt = sheet.get("prompt", "")
    modality = sheet.get("modality", "image")
    threshold = float(sheet.get("rubric", {}).get("pass_threshold", 0.72))

    base = {"node_id": node_id, "modality": modality, "attempt": attempt,
            "drift": False, "evidence": {}}

    # seeded DRIFT path (ref drifted vs bible).
    d = SEEDED_DRIFT.get(node_id)
    if d and attempt <= d["until_attempt"]:
        return {**base, "score": 0.41, "pass": False, "failure_mode": "drift",
                "drift": True,
                "fix_hint": "reference drifted from bible (禁止变化项 violated); regen the reference, then re-judge.",
                "evidence": {"reason": "seeded-drift", "ref_role_map": sheet.get("ref_role_map", {})}}

    # seeded generic FAIL path (re-roll + lesson).
    f = SEEDED_FAILURES.get(node_id)
    if f and attempt <= f["until_attempt"]:
        fm = f["failure_mode"]
        return {**base, "score": 0.38, "pass": False, "failure_mode": fm, "drift": False,
                "fix_hint": f"{fm}: tighten the prompt and re-roll a new seed; "
                            f"inject 固定特征词 and honor the negative floor.",
                "evidence": {"reason": "seeded-fail", "axis": fm}}

    # default: a high pseudo-score pass (clamped above threshold).
    score = max(threshold + 0.12, _pseudo_score(node_id, attempt, prompt) * 0.25 + 0.74)
    return {**base, "score": round(min(score, 0.99), 3), "pass": True,
            "failure_mode": "pass", "drift": False,
            "fix_hint": "", "evidence": {"reason": "mock-pass"}}


def _judge_gemini(sheet: dict) -> dict:
    """Gemini-3-pro-vision backend — STUB. One-config swap: set MANJU_JUDGE_BACKEND=gemini.

    A real impl uploads sheet['artifact']['path'] (+ contact_sheet + ref_image_paths)
    as multi-image input, sends the rubric verbatim + prior_lessons + ref_role_map as
    the prompt, and parses the model's JSON back into the verdict shape below.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("set GEMINI_API_KEY")
    raise RuntimeError("gemini judge backend not implemented — see _judge_mock for the verdict shape")


def _judge_claude(sheet: dict) -> dict:
    """Claude-vision backend — STUB. One-config swap: set MANJU_JUDGE_BACKEND=claude."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("set ANTHROPIC_API_KEY")
    raise RuntimeError("claude judge backend not implemented — see _judge_mock for the verdict shape")


_BACKENDS = {"mock": _judge_mock, "gemini": _judge_gemini, "claude": _judge_claude}


def JUDGE(sheet: dict) -> dict:
    """One stateless inference per artifact → a verdict (CONTRACTS §4).

    Backend is selected by JUDGE_BACKEND (env MANJU_JUDGE_BACKEND, default 'mock').
    V1 ships the deterministic mock; gemini/claude are one-config swaps (stubs until
    a key is wired). The control plane only assembles the sheet + records this output.
    """
    backend = _BACKENDS.get(JUDGE_BACKEND)
    if backend is None:
        raise RuntimeError(f"unknown JUDGE_BACKEND {JUDGE_BACKEND!r}; known: {sorted(_BACKENDS)}")
    return backend(sheet)
