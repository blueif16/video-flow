"""End-to-end pipeline proof (the INTEGRATION test). Run: python tests/test_e2e.py

On a FRESH project (projects/_scratch_e2e, gitignored — never touches projects/demo):
  1. brain.plan(...) authors the ledger (plan.* + tree).
  2. run_pipeline.run(...) drives the WHOLE pipeline on the mock provider:
     referencing drafts dual-anchor refs → judge locks them → building_prompts builds
     the rich 5-part request → runner generates → judge approves (with re-rolls +
     lessons) → composer renders final.mp4.
  3. Assert the whole thing actually converged and produced a valid film:
     - validate() still passes
     - every ASSET ref_status == "locked" with non-empty ref_image_paths
     - every SHOT status == "approved" with a real current_artifact mp4 ON DISK
     - ≥1 lesson appended AND ≥1 re-roll happened (the loop converged, not first-try)
     - render/final.mp4 exists; ffprobe shows video+audio; duration ≈ Σ probed shots
     - each approved shot's current_artifact.thumb_path exists (viewer thumbnails)

Proves the only remaining work is plugging in real API keys.
"""
from __future__ import annotations

import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manju.ledger import load                              # noqa: E402
from manju.brain import brain as B                          # noqa: E402
from manju.run_pipeline import run                          # noqa: E402
from manju.skills.composing.composer import probe           # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(REPO, "projects", "_scratch_e2e")
DEMO = os.path.join(REPO, "projects", "demo")

SEED = "被逐少年归来复仇"
KNOBS = {"题材": "都市玄幻", "集数N": 1, "时长": 60,
         "主爽点类型": "身份碾压", "style_id": "国漫暗黑"}

DURATION_TOL_S = 0.25  # render-gate tolerance (matches composer.DURATION_TOL_S)


class E2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # never touch projects/demo; build on a fresh gitignored scratch project.
        assert os.path.abspath(SCRATCH) != os.path.abspath(DEMO)
        shutil.rmtree(SCRATCH, ignore_errors=True)
        B.plan(SEED, dict(KNOBS), SCRATCH)
        cls.summary = run(SCRATCH)
        cls.led = load(SCRATCH)

    def test_demo_fixture_untouched(self):
        # the golden fixture must stay pristine.
        demo = load(DEMO)
        for a in demo.nodes(kind="asset"):
            self.assertEqual(a["run"]["ref_status"], "none", f"{a['id']} demo mutated")
        for s in demo.nodes(kind="shot"):
            self.assertEqual(s["run"]["status"], "pending", f"{s['id']} demo mutated")

    def test_validates(self):
        self.led.validate()  # raises SchemaError on any shape violation

    def test_every_asset_locked_with_refs(self):
        assets = self.led.nodes(kind="asset")
        self.assertGreaterEqual(len(assets), 2)
        for a in assets:
            self.assertEqual(a["run"]["ref_status"], "locked",
                             f"{a['id']} ref_status={a['run']['ref_status']!r} (want locked)")
            paths = a["run"].get("ref_image_paths", [])
            self.assertTrue(paths, f"{a['id']} has no ref_image_paths")
            for p in paths:
                self.assertTrue(os.path.isfile(p), f"{a['id']} ref image missing on disk: {p}")

    def test_every_shot_approved_with_mp4(self):
        shots = self.led.nodes(kind="shot")
        self.assertGreaterEqual(len(shots), 2)
        for s in shots:
            self.assertEqual(s["run"]["status"], "approved",
                             f"{s['id']} status={s['run']['status']!r} (want approved)")
            art = s["run"].get("current_artifact") or {}
            clip = art.get("path")
            self.assertTrue(clip and os.path.isfile(clip),
                            f"{s['id']} has no real current_artifact mp4 ({clip!r})")
            self.assertTrue(clip.endswith(".mp4"), f"{s['id']} artifact is not an mp4: {clip}")
            # viewer thumbnail
            thumb = art.get("thumb_path")
            self.assertTrue(thumb and os.path.isfile(thumb),
                            f"{s['id']} current_artifact.thumb_path missing ({thumb!r})")

    def test_loop_converged_lessons_and_rerolls(self):
        # ≥1 lesson appended AND ≥1 re-roll (the loop converged, not first-try pass).
        self.assertGreaterEqual(self.summary["lessons"], 1,
                                f"no lesson appended: {self.summary}")
        self.assertGreaterEqual(self.summary["reroll_count"], 1,
                                f"no re-roll happened: {self.summary}")
        # cross-check the reroll count against the actual attempt history.
        rerolled = [n["id"] for n, _ in self.led._index.values()
                    if len(n.get("run", {}).get("attempts", [])) >= 2]
        self.assertTrue(rerolled, "no node has ≥2 attempts despite reroll_count")

    def test_final_mp4_valid_video_audio_duration(self):
        final = self.summary["final_mp4"]
        self.assertTrue(final and os.path.isfile(final), f"final.mp4 missing: {final!r}")
        p = probe(final)
        self.assertTrue(p["has_video"], "final.mp4 has no video stream")
        self.assertTrue(p["has_audio"], "final.mp4 has no audio stream")
        # duration ≈ Σ probed approved-shot clip durations (ffprobe truth, in id order).
        expected = sum(
            probe((s["run"]["current_artifact"] or {})["path"])["duration_s"]
            for s in self.led.nodes(kind="shot")
            if s["run"].get("status") == "approved"
        )
        self.assertLessEqual(abs(p["duration_s"] - expected), DURATION_TOL_S,
                             f"final duration {p['duration_s']} != Σ shots {expected}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
