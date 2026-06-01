"""Self-test for composing (Phase 5). Run: python -m manju.skills.composing.selftest

Copies projects/demo → projects/_scratch_compose (gitignored), simulates upstream
by marking both shots approved with a current_artifact pointing at a copy of
assets/sample/shot.mp4, then runs compose() and asserts:
  - render/final.mp4 is a valid clip with video+audio, duration ≈ Σ(probed shots)
  - render/script-cues.json has a cue for sh02's dialogue, frames set, pacing
    within-or-warned 3.2–5.5 chars/sec, no overlap
  - render/render-manifest.json records gate PASS + the handoff plan
Never touches projects/demo.
"""
from __future__ import annotations

import json
import os
import shutil

from manju.ledger import load
from manju.skills.composing.composer import compose, handoff_plan, probe

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEMO = os.path.join(ROOT, "projects", "demo")
SCRATCH = os.path.join(ROOT, "projects", "_scratch_compose")
SAMPLE_SHOT = os.path.join(ROOT, "assets", "sample", "shot.mp4")


def _setup() -> "object":
    if os.path.exists(SCRATCH):
        shutil.rmtree(SCRATCH)
    shutil.copytree(DEMO, SCRATCH)
    led = load(SCRATCH)
    # simulate upstream: copy sample clip into each shot's content-addressed slot,
    # append an attempt (sets current_artifact), then approve via the state machine.
    art_root = os.path.join(SCRATCH, "artifacts")
    for sh in led.nodes(kind="shot"):
        sid = sh["id"]
        attempt_id = f"seed7-{sid}"
        dst_dir = os.path.join(art_root, sid)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, f"{attempt_id}.mp4")
        shutil.copyfile(SAMPLE_SHOT, dst)
        led.append_attempt(sid, {
            "attempt_id": attempt_id, "ts": "2026-05-31T00:00:00Z", "seed": 7,
            "model": "mock", "prompt": "(mock)", "artifact_path": dst,
            "thumb_path": None, "verdict": None, "lesson_ref": None,
        })
        # pending → generating → landed → judging → approved
        for st in ("generating", "landed", "judging", "approved"):
            led.set_status(sid, st, "generating")
    led.save()
    return led


def main() -> int:
    led = _setup()
    result = compose(led, SCRATCH)

    # 1. final.mp4 valid: video+audio, duration ≈ Σ probed shots (4 + 4 = 8s)
    p = probe(result["final"])
    expected = sum(probe(led.current_artifact(s["id"])["path"])["duration_s"]
                   for s in led.nodes(kind="shot"))
    assert p["has_video"] and p["has_audio"], f"missing streams: {p['streams']}"
    assert abs(p["duration_s"] - expected) <= 0.25, \
        f"duration {p['duration_s']} != expected {expected}"
    print(f"OK final.mp4: {p['duration_s']}s (expected {expected}s), "
          f"streams={p['streams']} {p['width']}x{p['height']}")

    # 2. script-cues.json: cue for sh02's dialogue, frames set, pacing, no overlap
    with open(result["cues"], encoding="utf-8") as f:
        cues = json.load(f)
    sh02 = [c for c in cues["cues"] if c["shot_id"] == "ep01.sc01.sh02"]
    assert sh02, "no cue for sh02"
    cue = sh02[0]
    assert cue["text"] == "我回来了。", f"bad text: {cue['text']!r}"
    assert cue["startFrame"] >= 0 and cue["endFrame"] > cue["startFrame"], \
        f"bad frames: {cue['startFrame']}..{cue['endFrame']}"
    # pacing: within range OR explicitly warned
    assert cue["pacing_ok"] or cue["pacing_warning"], "pacing neither ok nor warned"
    # no overlap across spoken cues
    spoken = cues["cues"]
    for a, b in zip(spoken, spoken[1:]):
        assert b["startSec"] >= a["endSec"] + cues["overlap_guard_s"] - 1e-9, \
            f"overlap {a['cue_id']} → {b['cue_id']}"
    print(f"OK script-cues.json: {len(spoken)} cue(s); sh02 "
          f"frames {cue['startFrame']}..{cue['endFrame']} "
          f"cps={cue['chars_per_sec']} ok={cue['pacing_ok']} "
          f"warn={cue['pacing_warning'] or '-'}")

    # 3. render-manifest.json: gate PASS + handoff
    with open(result["manifest"], encoding="utf-8") as f:
        man = json.load(f)
    assert man["render_gate"]["pass"], f"gate not PASS: {man['render_gate']}"
    assert man["handoff"]["sequence"][0] == "cue-plan-author"
    assert len(man["handoff"]["steps"]) == 5
    print(f"OK render-manifest.json: gate PASS, handoff "
          f"{' → '.join(man['handoff']['sequence'])}")

    # 4. handoff_plan() callable standalone
    hp = handoff_plan(led, SCRATCH)
    assert hp["steps"][2]["skill"] == "asr-cue-aligner"
    print("OK handoff_plan() seam")

    print("\nALL CHECKS PASSED")
    print(f"  final:    {result['final']}")
    print(f"  cues:     {result['cues']}")
    print(f"  manifest: {result['manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
