"""composing (Phase 5) — WIRE, DON'T REBUILD.

Assemble approved shot clips into a final video and emit the exact handoff
artifacts the richer skill stack consumes. V1 is a self-contained ffmpeg render
(the concrete floor) PLUS the canonical `script-cues.json` / `render-manifest.json`
that `cue-plan-author → tts-voice-direction → asr-cue-aligner → hyperframes/remotion
composer → render-gate` run against later.

Contract: CONTRACTS.md §5 (IN: output_files[] + dialogue + duration_s;
OUT: projects/<n>/render/). Rules (research plan, Layer-2 item 5):
  - ffprobe = truth (never trust planned duration_s for cutting)
  - 3.2–5.5 chars/sec pacing guard (warn out-of-range)
  - −0.01s overlap guard (adjacent cues never overlap)
  - Chinese ASR → Volcano first (documented in handoff, not run here)
  - never `format=srt` — captions are real burned-in overlays

Standard library only + ffmpeg/ffprobe. No Claude Code skills are invoked here;
`handoff_plan()` documents the seam for the human orchestrator.

Caption rasterization note: the local ffmpeg has no drawtext/libass, so captions
are rendered to transparent RGBA PNGs via macOS AppKit (JXA, ships with the OS,
no pip) and burned in with ffmpeg's `overlay` + `enable='between(t,..)'`. This is
a real burned-in caption track, not a lossy `format=srt` hardsub.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

# ── tunables / guards (research plan, Layer-2 item 5) ─────────────────────────
FPS = 25                       # stated cue fps
CPS_MIN = 3.2                  # chars/sec pacing floor
CPS_MAX = 5.5                  # chars/sec pacing ceiling
OVERLAP_GUARD_S = 0.01         # adjacent cues kept ≥ this far apart
DURATION_TOL_S = 0.25          # render-gate: |out − Σshots| tolerance
CAPTION_FONT = "STHeiti"       # CJK-capable system font
VOICE_STANDIN = os.path.join("assets", "sample", "voice.wav")  # V1 narration stand-in

# documented next-step handoff (the existing skill stack)
HANDOFF_SEQUENCE = [
    "cue-plan-author",
    "tts-voice-direction",
    "asr-cue-aligner",
    "hyperframes/remotion composer",
    "machine render-gate",
]

_ID_RE = re.compile(r"^ep(\d+)\.sc(\d+)\.sh(\d+)$")


def _log(msg: str) -> None:
    print(f"[composing] {msg}", file=sys.stderr)


def _repo_root() -> str:
    # .../manju/skills/composing/composer.py → repo root is 3 dirs up
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ── ffprobe = truth ───────────────────────────────────────────────────────────
def probe(path: str) -> dict:
    """Real duration + stream kinds + frame size of a media file.

    ffprobe is the single source of truth for cutting — never the planned
    duration_s.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True,
    )
    d = json.loads(out.stdout)
    streams = [s.get("codec_type") for s in d.get("streams", [])]
    dur = float(d["format"]["duration"])
    width = next((s.get("width") for s in d["streams"] if s.get("codec_type") == "video"), None)
    height = next((s.get("height") for s in d["streams"] if s.get("codec_type") == "video"), None)
    return {"path": path, "duration_s": dur,
            "has_video": "video" in streams, "has_audio": "audio" in streams,
            "streams": streams, "width": width, "height": height}


# ── shot collection (shot-order, approved only) ───────────────────────────────
def _shot_sort_key(node_id: str) -> tuple:
    m = _ID_RE.match(node_id)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (9999, 9999, 9999)


def collect_shots(ledger) -> list[dict]:
    """Approved shots in stable id order with their clip path + dialogue + planned dur.

    Non-approved shots are skipped (logged). Approved shots missing a usable
    current_artifact are also skipped (logged) — they cannot be assembled.
    """
    shots = sorted(ledger.nodes(kind="shot"), key=lambda s: _shot_sort_key(s["id"]))
    rows: list[dict] = []
    for sh in shots:
        sid = sh["id"]
        status = sh["run"].get("status")
        if status != "approved":
            _log(f"skip {sid}: status={status!r} (not approved)")
            continue
        art = ledger.current_artifact(sid)
        clip = (art or {}).get("path")
        if not clip or not os.path.isfile(clip):
            _log(f"skip {sid}: approved but no usable current_artifact ({clip!r})")
            continue
        plan = sh["plan"]
        rows.append({
            "shot_id": sid,
            "clip": clip,
            "dialogue": (plan.get("dialogue") or "").strip(),
            "planned_duration_s": plan.get("duration_s"),
        })
    return rows


# ── script-cues.json (canonical CuePlan input to the narration kit) ───────────
def build_cues(rows: list[dict], fps: int = FPS) -> dict:
    """Compute the CuePlan from PROBED shot durations.

    One row per shot; spoken shots carry text + frames. Timeline is the running
    sum of probed clip durations. Enforces the −0.01s overlap guard and warns on
    cues outside 3.2–5.5 chars/sec. Cue-row schema:
      {cue_id, shot_id, text, startSec, endSec, startFrame, endFrame,
       chars, chars_per_sec, pacing_ok, pacing_warning}
    """
    cues = []
    warnings = []
    t = 0.0
    spoken = 0
    for row in rows:
        pr = probe(row["clip"])
        start = t
        end = t + pr["duration_s"]
        t = end
        text = row["dialogue"]
        if not text:
            continue
        spoken += 1
        # overlap guard: never start before the previous spoken cue's (guarded) end
        if cues:
            prev_end = cues[-1]["endSec"]
            if start < prev_end + OVERLAP_GUARD_S:
                start = prev_end + OVERLAP_GUARD_S
        if end <= start:
            end = start + OVERLAP_GUARD_S
        span = end - start
        chars = len(text)
        cps = chars / span if span > 0 else 0.0
        pacing_ok = CPS_MIN <= cps <= CPS_MAX
        warn = "" if pacing_ok else (
            f"{cps:.2f} chars/sec out of [{CPS_MIN},{CPS_MAX}] for {chars} chars over {span:.2f}s"
        )
        if warn:
            warnings.append({"shot_id": row["shot_id"], "warning": warn})
            _log(f"PACING WARN {row['shot_id']}: {warn}")
        cues.append({
            "cue_id": f"cue{spoken:02d}",
            "shot_id": row["shot_id"],
            "text": text,
            "startSec": round(start, 3),
            "endSec": round(end, 3),
            "startFrame": int(round(start * fps)),
            "endFrame": int(round(end * fps)),
            "chars": chars,
            "chars_per_sec": round(cps, 3),
            "pacing_ok": pacing_ok,
            "pacing_warning": warn,
        })
    return {
        "version": "1.0.0",
        "fps": fps,
        "pacing": {"chars_per_sec_min": CPS_MIN, "chars_per_sec_max": CPS_MAX},
        "overlap_guard_s": OVERLAP_GUARD_S,
        "cues": cues,
        "warnings": warnings,
    }


# ── caption rasterization (JXA AppKit → transparent RGBA PNG) ─────────────────
_JXA_CAPTION = r"""
ObjC.import('AppKit');
ObjC.import('Foundation');
function run(argv) {
  var text = argv[0];
  var W = parseInt(argv[1]), H = parseInt(argv[2]);
  var fontSize = parseFloat(argv[3]);
  var fontName = argv[4];
  var outPath = argv[5];
  var rep = $.NSBitmapImageRep.alloc.initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
    $(), W, H, 8, 4, true, false, $.NSCalibratedRGBColorSpace, 0, 0);
  var ctx = $.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext(ctx);
  var ps = $.NSMutableParagraphStyle.alloc.init;
  ps.setAlignment($.NSTextAlignmentCenter);
  var font = $.NSFont.fontWithNameSize(fontName, fontSize);
  if (!font.js) font = $.NSFont.systemFontOfSize(fontSize);
  var attrs = $.NSMutableDictionary.alloc.init;
  attrs.setObjectForKey(font, $.NSFontAttributeName);
  attrs.setObjectForKey($.NSColor.whiteColor, $.NSForegroundColorAttributeName);
  attrs.setObjectForKey(ps, $.NSParagraphStyleAttributeName);
  attrs.setObjectForKey($.NSColor.blackColor, $.NSStrokeColorAttributeName);
  attrs.setObjectForKey($.NSNumber.numberWithDouble(-4.0), $.NSStrokeWidthAttributeName);
  var ns = $.NSString.alloc.initWithUTF8String(text);
  var size = ns.sizeWithAttributes(attrs);
  var rect = $.NSMakeRect(0, (H - size.height) / 2, W, size.height);
  ns.drawInRectWithAttributes(rect, attrs);
  $.NSGraphicsContext.restoreGraphicsState;
  var png = rep.representationUsingTypeProperties($.NSBitmapImageFileTypePNG, $.NSDictionary.dictionary);
  png.writeToFileAtomically($(outPath), true);
  return "ok";
}
"""


def _render_caption_png(text: str, width: int, out_path: str, font_size: int = 56,
                        height: int = 160, font: str = CAPTION_FONT) -> str:
    """Rasterize one caption line to a transparent RGBA PNG (macOS AppKit, no pip)."""
    fd, script = tempfile.mkstemp(suffix=".js")
    os.close(fd)
    try:
        with open(script, "w", encoding="utf-8") as f:
            f.write(_JXA_CAPTION)
        subprocess.run(
            ["osascript", "-l", "JavaScript", script,
             text, str(width), str(height), str(font_size), font, out_path],
            capture_output=True, text=True, check=True,
        )
    finally:
        os.unlink(script)
    if not os.path.isfile(out_path):
        raise RuntimeError(f"caption render failed for {text!r}")
    return out_path


# ── ffmpeg assembly (concat + caption overlay + narration mux) ────────────────
def assemble(rows: list[dict], cues: dict, render_dir: str, voice_wav: str) -> dict:
    """Concat clips, burn captions timed from cues, lay narration under, → final.mp4.

    Per-clip PTS reset → concat filter → per-cue overlay(enable=between) →
    narration apad/atrim to the full video length. Returns the probed output.
    """
    os.makedirs(render_dir, exist_ok=True)
    total = sum(probe(r["clip"])["duration_s"] for r in rows)
    width = probe(rows[0]["clip"])["width"] if rows else 1280

    # render one caption PNG per cue
    cap_dir = os.path.join(render_dir, "captions")
    os.makedirs(cap_dir, exist_ok=True)
    cue_pngs = []
    for cue in cues["cues"]:
        png = os.path.join(cap_dir, f"{cue['cue_id']}.png")
        _render_caption_png(cue["text"], width, png)
        cue_pngs.append((png, cue["startSec"], cue["endSec"]))

    # build the filter graph
    inputs = ["-y"]
    for r in rows:
        inputs += ["-i", r["clip"]]
    n = len(rows)
    for png, _, _ in cue_pngs:
        inputs += ["-i", png]
    inputs += ["-i", voice_wav]
    voice_idx = n + len(cue_pngs)

    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
    parts.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    # chain caption overlays
    cur = "vc"
    for k, (_, start, end) in enumerate(cue_pngs):
        cap_in = n + k
        nxt = f"vo{k}"
        parts.append(
            f"[{cur}][{cap_in}:v]overlay=x=0:y=H-h-48:"
            f"enable='between(t,{start},{end})'[{nxt}]"
        )
        cur = nxt
    parts.append(
        f"[{voice_idx}:a]apad,atrim=0:{total:.3f},asetpts=PTS-STARTPTS[a]"
    )
    filtergraph = ";".join(parts)

    final = os.path.join(render_dir, "final.mp4")
    cmd = ["ffmpeg"] + inputs + [
        "-filter_complex", filtergraph,
        "-map", f"[{cur}]", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "+faststart", final,
    ]
    _log(f"ffmpeg assemble: {n} clips, {len(cue_pngs)} captions, target {total:.3f}s")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        _log(res.stderr[-2000:])
        raise RuntimeError("ffmpeg assembly failed")
    out = probe(final)
    out["expected_duration_s"] = round(total, 3)
    return out


# ── render-gate (machine, ffprobe-truth) ──────────────────────────────────────
def render_gate(out_probe: dict, expected_s: float) -> dict:
    """Assert the render has video+audio and duration ≈ Σ(probed shot durations)."""
    checks = {
        "has_video": out_probe["has_video"],
        "has_audio": out_probe["has_audio"],
        "duration_within_tol": abs(out_probe["duration_s"] - expected_s) <= DURATION_TOL_S,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "out_duration_s": round(out_probe["duration_s"], 3),
        "expected_duration_s": round(expected_s, 3),
        "tolerance_s": DURATION_TOL_S,
        "delta_s": round(out_probe["duration_s"] - expected_s, 3),
    }


# ── the handoff seam (document, don't execute) ────────────────────────────────
def handoff_plan(ledger, project_dir: str) -> dict:
    """Ordered list of existing-skill invocations + their input artifact paths.

    The human orchestrator runs the richer narration/render stack later against
    these artifacts. We DO NOT invoke the skills here (they are Claude Code skills,
    not importable Python).
    """
    render_dir = os.path.join(project_dir, "render")
    cues = os.path.join(render_dir, "script-cues.json")
    rows = collect_shots(ledger)
    clips = [{"shot_id": r["shot_id"], "clip": r["clip"]} for r in rows]
    return {
        "sequence": HANDOFF_SEQUENCE,
        "steps": [
            {"skill": "cue-plan-author",
             "consumes": cues,
             "produces": "refined script-cues.json (per-cue TTS rows)",
             "note": "the CuePlan we emit is its canonical input"},
            {"skill": "tts-voice-direction",
             "consumes": cues,
             "produces": "voice block (voice id, prompt template, clip budget) + narration WAV",
             "note": "Chinese narration; one voice for the series"},
            {"skill": "asr-cue-aligner",
             "consumes": "narration WAV from tts-voice-direction",
             "produces": "per-cue startFrame/endFrame written back onto script-cues.json",
             "note": "Chinese ASR → Volcano first; sherpa-onnx fallback. Re-times cues to real speech."},
            {"skill": "hyperframes/remotion composer",
             "consumes": [cues, {"clips": clips}],
             "produces": "final composition (captions synced to aligned cues, never format=srt)",
             "note": "replaces this V1 ffmpeg floor with the richer composer"},
            {"skill": "machine render-gate",
             "consumes": os.path.join(render_dir, "final.mp4"),
             "produces": "ffprobe-truth gate verdict",
             "note": "same gate this V1 already runs; re-asserts streams + duration"},
        ],
    }


# ── entry ─────────────────────────────────────────────────────────────────────
def compose(ledger, project_dir: str) -> dict:
    """Assemble approved shots → render/final.mp4 + emit handoff artifacts.

    Returns {"final","cues","manifest","probe"}. Fails loudly if the render-gate fails.
    """
    render_dir = os.path.join(project_dir, "render")
    os.makedirs(render_dir, exist_ok=True)

    rows = collect_shots(ledger)
    if not rows:
        raise RuntimeError("no approved shots with usable artifacts to compose")

    # 1. cues from probed durations (CuePlan input to the narration kit)
    cues = build_cues(rows)
    cues_path = os.path.join(render_dir, "script-cues.json")
    with open(cues_path, "w", encoding="utf-8") as f:
        json.dump(cues, f, ensure_ascii=False, indent=2)

    # 2. narration stand-in (abs path under repo root)
    voice = os.path.join(_repo_root(), VOICE_STANDIN)
    if not os.path.isfile(voice):
        raise RuntimeError(f"narration stand-in missing: {voice}")

    # 3. assemble (concat + burned captions + narration)
    out_probe = assemble(rows, cues, render_dir, voice)

    # 4. render-gate (machine, ffprobe-truth) — fail loudly
    gate = render_gate(out_probe, out_probe["expected_duration_s"])

    # 5. manifest (inputs→output, gate, handoff)
    manifest = {
        "version": "1.0.0",
        "project_dir": os.path.abspath(project_dir),
        "inputs": [{"shot_id": r["shot_id"], "clip": r["clip"],
                    "dialogue": r["dialogue"],
                    "planned_duration_s": r["planned_duration_s"],
                    "probed_duration_s": round(probe(r["clip"])["duration_s"], 3)}
                   for r in rows],
        "narration_standin": voice,
        "output": {"final": os.path.abspath(out_probe["path"]),
                   "probe": {k: out_probe[k] for k in
                             ("duration_s", "has_video", "has_audio", "width", "height")}},
        "cues": os.path.abspath(cues_path),
        "render_gate": gate,
        "handoff": handoff_plan(ledger, project_dir),
        "caption_method": "macOS AppKit (JXA) → transparent PNG overlay (NOT format=srt)",
        "fps": FPS,
    }
    manifest_path = os.path.join(render_dir, "render-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if not gate["pass"]:
        _log(f"RENDER-GATE FAIL: {gate}")
        raise RuntimeError(f"render-gate failed: {gate['checks']}")
    _log(f"render-gate PASS: out={gate['out_duration_s']}s expected={gate['expected_duration_s']}s")

    return {
        "final": os.path.abspath(out_probe["path"]),
        "cues": os.path.abspath(cues_path),
        "manifest": os.path.abspath(manifest_path),
        "probe": out_probe,
    }
