"""Self-test for Phase 1 — the 爽剧 BRAIN. Run: python tests/test_brain.py

Proves the spec's four self-test claims:
  1. plan(...) writes a ledger.json that passes load(...).validate() and has the
     fixture node shape (≥1 char + ≥1 scene asset; ≥1 ep→sc→shots with a full
     plan + empty run; deps wired to asset ids).
  2. showtell_check flags an interiority line and accepts the filmable rewrite.
  3. the 爽点 self-check rejects a 爽点 with no prior 压抑 setup.
  4. re-emitting under a second style_id changes ONLY style fields, not story.
"""
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manju.ledger import ledger as L  # noqa: E402
from manju.brain import brain as B  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(REPO, "projects", "_scratch_brain")
DEMO = os.path.join(REPO, "projects", "demo")

SEED = "被逐少年归来复仇"
KNOBS = {"题材": "都市玄幻", "集数N": 1, "时长": 60, "主爽点类型": "身份碾压", "style_id": "国漫暗黑"}


def _story_fields(led: L.Ledger) -> dict:
    """Everything EXCEPT style fields — used to prove the style axis is orthogonal."""
    import copy
    doc = copy.deepcopy(led.doc)
    # normalize the project identity (derives from project_dir, not from style)
    doc["project"]["id"] = "<<PROJ>>"
    doc["project"]["title"] = "<<PROJ>>"
    # blank out every style_id and the styles[] preset (the only style-axis surface)
    doc["styles"] = "<<STYLE>>"
    doc["project"]["default_style_id"] = "<<STYLE>>"
    doc["project"]["knobs"]["style_id"] = "<<STYLE>>"
    for bucket in ("characters", "scenes", "props", "villains"):
        for a in doc["bible"].get(bucket, []):
            a["plan"]["style_id"] = "<<STYLE>>"
    for ep in doc["episodes"]:
        for sc in ep["scenes"]:
            for sh in sc["shots"]:
                sh["plan"]["style_id"] = "<<STYLE>>"
    return doc


class BrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(SCRATCH, ignore_errors=True)
        cls.path = B.plan(SEED, dict(KNOBS), SCRATCH)
        cls.led = L.load(SCRATCH)

    @classmethod
    def tearDownClass(cls):
        # leave SCRATCH for inspection (gitignored); harmless to keep
        pass

    # 1 — output validates + matches the fixture node shape
    def test_validates_and_matches_fixture_shape(self):
        self.assertTrue(os.path.isfile(self.path))
        self.led.validate()  # raises SchemaError on any shape violation

        chars = self.led.nodes(kind="asset")
        self.assertGreaterEqual(len([a for a in chars if a["kind"] == "character"]), 1)
        self.assertGreaterEqual(len([a for a in chars if a["kind"] == "scene"]), 1)

        shots = self.led.nodes(kind="shot")
        self.assertGreaterEqual(len(shots), 1)

        # every asset: full plan keys + EMPTY run (ref_status none, no attempts)
        for a in self.led.nodes(kind="asset"):
            self.assertEqual(set(a["plan"]), L.ASSET_PLAN_FIELDS)
            self.assertEqual(a["run"]["ref_status"], "none")
            self.assertEqual(a["run"]["attempts"], [])
            self.assertIsNone(a["run"]["current_artifact"])

        # every shot: full required plan + EMPTY run (pending, no attempts);
        # deps wired to asset ids; showtell_pass True
        asset_ids = {a["id"] for a in self.led.nodes(kind="asset")}
        for sh in shots:
            for req in ("intent", "camera", "action", "ref_ids", "style_id", "duration_s"):
                self.assertIn(req, sh["plan"])
            self.assertTrue(sh["plan"]["showtell_pass"])
            self.assertEqual(sh["run"]["status"], "pending")
            self.assertEqual(sh["run"]["attempts"], [])
            # deps include at least one asset id (the dual anchor) for every shot
            self.assertTrue(set(sh["deps"]) & asset_ids,
                            f"{sh['id']} deps {sh['deps']} cite no asset")
            # ref_ids must be real asset ids
            for r in sh["plan"]["ref_ids"]:
                self.assertIn(r, asset_ids)

    # 1b — frontier behaves: assets runnable, shots blocked until refs locked
    def test_frontier_consistent_with_kernel(self):
        fr = set(self.led.runnable_frontier())
        self.assertIn("char_lin", fr)
        self.assertIn("scene_throne", fr)
        first_shot = self.led.nodes(kind="shot")[0]["id"]
        self.assertNotIn(first_shot, fr)  # deps not locked yet

    # 2 — SHOW-DON'T-TELL gate flags interiority, accepts the filmable rewrite
    def test_showtell_gate(self):
        ok, reason = B.showtell_check("她感到背叛")
        self.assertFalse(ok, reason)
        rewrite = B.physicalize("她感到背叛")
        self.assertEqual(rewrite, "他的酒杯在微微颤抖，指节因用力而发白")
        ok2, _ = B.showtell_check(rewrite)
        self.assertTrue(ok2)
        # explicit V.O. is allowed even though it narrates
        ok3, _ = B.showtell_check("画外音：那一夜，他失去了一切。")
        self.assertTrue(ok3)
        # empty dialogue is fine (nothing to film)
        self.assertTrue(B.showtell_check("")[0])

    # 3 — the 爽点 self-check rejects a 释放 with no prior 压抑 setup
    def test_satisfaction_self_check_rejects_orphan(self):
        # orphan: a 释放 whose pays_off is empty
        with self.assertRaises(B.SatisfactionError):
            B.satisfaction_self_check([
                {"id": "r1", "type": "释放", "pays_off": []},
            ])
        # forward-ref: cites a setup that doesn't appear earlier
        with self.assertRaises(B.SatisfactionError):
            B.satisfaction_self_check([
                {"id": "r1", "type": "释放", "pays_off": ["s_future"]},
                {"id": "s_future", "type": "压抑"},
            ])
        # valid: setup precedes the release that cites it
        B.satisfaction_self_check([
            {"id": "s1", "type": "压抑"},
            {"id": "r1", "type": "释放", "pays_off": ["s1"]},
        ])  # no raise

    # 3b — the villain gate rejects a 隐藏反派 with <3 foreshadows
    def test_hidden_villain_gate(self):
        with self.assertRaises(B.VillainError):
            B.validate_hidden_villain({"id": "v", "foreshadows": [
                {"episode": "ep01", "line_ref": "ep01.sc01.sh01"}]})
        B.validate_hidden_villain({"id": "v", "foreshadows": [
            {"episode": "ep01", "line_ref": "ep01.sc01.sh01"},
            {"episode": "ep02", "line_ref": "ep02.sc01.sh01"},
            {"episode": "ep03", "line_ref": "ep03.sc01.sh01"}]})  # no raise

    # 4 — style axis: re-emit under a different style_id; ONLY style fields change
    def test_style_axis_orthogonal(self):
        alt_dir = os.path.join(REPO, "projects", "_scratch_brain_alt")
        shutil.rmtree(alt_dir, ignore_errors=True)
        alt_knobs = dict(KNOBS, style_id="水墨武侠")
        B.plan(SEED, alt_knobs, alt_dir)
        alt = L.load(alt_dir)
        alt.validate()

        # story (everything minus style fields) must be byte-identical
        self.assertEqual(_story_fields(self.led), _story_fields(alt),
                         "story changed when only style_id was swapped")
        # and the style fields actually differ
        self.assertNotEqual(self.led.doc["styles"], alt.doc["styles"])
        self.assertEqual(alt.doc["styles"][0]["id"], "水墨武侠")
        self.assertEqual(alt.node("char_lin")["plan"]["style_id"], "水墨武侠")
        shutil.rmtree(alt_dir, ignore_errors=True)

    # 5 — multi-episode run exercises stages, cliffhangers, and the hidden villain
    def test_multi_episode_dramaturgy(self):
        me_dir = os.path.join(REPO, "projects", "_scratch_brain_multi")
        shutil.rmtree(me_dir, ignore_errors=True)
        B.plan(SEED, dict(KNOBS, 集数N=4, 主爽点类型="打脸复仇"), me_dir)
        me = L.load(me_dir)
        me.validate()
        eps = me.doc["episodes"]
        self.assertEqual(len(eps), 4)
        # the 隐藏反派 exists in the bible
        vids = {v["id"] for v in me.doc["bible"]["villains"]}
        self.assertIn("villain_hidden", vids)
        shutil.rmtree(me_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
