"""Self-test for composing_scenes (Phase 2). Run:
    python -m manju.skills.composing_scenes._selftest

Copies projects/demo -> projects/_scratch_sb (gitignored), drafts dual-anchor refs
then force-locks them via the kernel, storyboards every shot, and asserts:
  - each shot gets shot_NN.spec.json with SEPARATED background + characters layers
  - each spec carries a nine_grid (9宫格) block
  - the keyframe.png exists, opens (PNG signature + ffprobe dims), is 16:9
  - placement DIFFERS between a 近景 (close-up) and a 全景 (wide) shot — the layout
    policy is keyed by 景别
  - idempotency: re-storyboarding reuses the keyframe (no rebuild) + same spec
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from manju.ledger import load
from manju.skills.referencing.referencer import draft_refs
from manju.skills.composing_scenes.storyboarder import (
    storyboard_all, storyboard_shot, keyframe_for,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DEMO = os.path.join(_REPO, "projects", "demo")
_SCRATCH = os.path.join(_REPO, "projects", "_scratch_sb")


def _setup() -> None:
    if os.path.exists(_SCRATCH):
        shutil.rmtree(_SCRATCH)
    shutil.copytree(_DEMO, _SCRATCH)


def _png_ok(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def _ffprobe_dims(path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", path],
        check=True, capture_output=True, text=True,
    )
    s = json.loads(out.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def _lock_all_refs(led) -> None:
    """Step every drafted asset ref through judging → locked via the kernel."""
    for a in led.nodes(kind="asset"):
        if a["run"].get("ref_status") == "drafting":
            led.set_status(a["id"], "judging", "overlord")
            led.set_status(a["id"], "locked", "overlord")
    led.save()


def main() -> None:
    _setup()

    # 1. draft refs, then force-lock them via the kernel (no full pipeline needed).
    led = load(_SCRATCH)
    draft_refs(led, _SCRATCH)
    led = load(_SCRATCH)
    _lock_all_refs(led)
    led = load(_SCRATCH)
    for a in led.nodes(kind="asset"):
        assert a["run"]["ref_status"] == "locked", (a["id"], a["run"]["ref_status"])
    print("PASS setup: refs drafted + locked")

    # 2. storyboard every shot.
    specs = storyboard_all(led, _SCRATCH)
    shot_ids = [s["id"] for s in led.nodes(kind="shot")]
    assert set(specs) == set(shot_ids), (set(specs), set(shot_ids))

    for sid in shot_ids:
        ep, sc, sh = sid.split(".")
        name = f"shot_{sh.replace('sh', '')}"
        spec_path = os.path.join(_SCRATCH, "storyboard", ep, sc, f"{name}.spec.json")
        assert os.path.isfile(spec_path), spec_path
        spec = json.load(open(spec_path, encoding="utf-8"))

        # separated layers: background + characters[]
        layers = spec["layers"]
        assert "background" in layers and "characters" in layers, layers
        assert layers["background"] is not None or layers["characters"], sid
        for c in layers["characters"]:
            assert c["role"] == "character" and c["asset_id"], c
            pl = c["placement"]
            assert {"x", "y", "scale", "z"} <= set(pl), pl

        # nine_grid block
        ng = spec["nine_grid"]
        assert ng["grid"] == [3, 3] and "subject_anchor" in ng, ng
        assert 0 <= ng["subject_cell"] <= 8, ng

        # keyframe still exists, opens, is 16:9
        kf = spec["keyframe_still"]
        assert kf and _png_ok(kf), (sid, kf)
        w, h = _ffprobe_dims(kf)
        assert (w, h) == (1280, 720), (sid, w, h)
        assert keyframe_for(_SCRATCH, sid) == kf, sid
    print(f"PASS storyboards: {len(shot_ids)} specs, separated layers + nine_grid + 1280x720 keyframe")

    # 3. placement DIFFERS between a 近景 (sh02) and a 全景 (sh01) shot.
    sp_wide = json.load(open(os.path.join(
        _SCRATCH, "storyboard", "ep01", "sc01", "shot_01.spec.json"), encoding="utf-8"))
    sp_close = json.load(open(os.path.join(
        _SCRATCH, "storyboard", "ep01", "sc01", "shot_02.spec.json"), encoding="utf-8"))
    wide_scale = sp_wide["layers"]["characters"][0]["placement"]["scale"]
    close_scale = sp_close["layers"]["characters"][0]["placement"]["scale"]
    assert sp_wide["camera"]["shot_size"] == "全景", sp_wide["camera"]
    assert sp_close["camera"]["shot_size"] == "近景", sp_close["camera"]
    assert close_scale > wide_scale, (
        f"近景 scale {close_scale} should exceed 全景 scale {wide_scale}")
    print(f"PASS layout policy: 全景 char scale={wide_scale} < 近景 char scale={close_scale}")

    # 4. idempotency: re-storyboard reuses the keyframe + emits the same spec.
    kf_before = keyframe_for(_SCRATCH, "ep01.sc01.sh01")
    mtime_before = os.path.getmtime(kf_before)
    spec_before = json.load(open(os.path.join(
        _SCRATCH, "storyboard", "ep01", "sc01", "shot_01.spec.json"), encoding="utf-8"))
    storyboard_shot(load(_SCRATCH), "ep01.sc01.sh01", _SCRATCH)
    spec_after = json.load(open(os.path.join(
        _SCRATCH, "storyboard", "ep01", "sc01", "shot_01.spec.json"), encoding="utf-8"))
    assert os.path.getmtime(kf_before) == mtime_before, "keyframe rebuilt (not skip-if-exists)"
    assert spec_before == spec_after, "spec changed on re-run"
    print("PASS idempotency: keyframe reused, spec stable")

    print("\nALL SELF-TESTS PASSED")


if __name__ == "__main__":
    main()
