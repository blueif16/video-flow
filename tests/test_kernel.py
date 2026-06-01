"""Self-test for the ledger kernel. Run: python tests/test_kernel.py

Proves: schema validates the fixture; writer-tag enforcement raises on
cross-writes; an illegal status transition raises; runnable_frontier() is
correct before/after locking asset refs; lesson append+retrieve works;
atomic save round-trips.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from manju.ledger import ledger as L  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(REPO, "projects", "demo")
SH1 = "ep01.sc01.sh01"
SH2 = "ep01.sc01.sh02"


class KernelTest(unittest.TestCase):
    def setUp(self):
        # work on a throwaway copy so saves don't mutate the committed fixture
        self.tmp = tempfile.mkdtemp(prefix="manju_test_")
        shutil.copy(os.path.join(DEMO, "ledger.json"), os.path.join(self.tmp, "ledger.json"))
        self.led = L.load(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # 1 — schema validates the fixture
    def test_schema_validates_fixture(self):
        self.led.validate()  # raises SchemaError on failure
        # negative control: a broken doc must fail
        self.led.doc["episodes"][0]["scenes"][0]["shots"][0]["plan"].pop("intent")
        with self.assertRaises(L.SchemaError):
            self.led.validate()

    # 2 — writer-tag ownership enforcement
    def test_writer_tag_enforcement(self):
        # wrong writer
        with self.assertRaises(L.WriterError):
            self.led.write_plan(SH1, "overlord", intent="x")
        with self.assertRaises(L.WriterError):
            self.led.write_run(SH1, "brain", cost_usd=1.0)
        # plan field smuggled via write_run (and vice-versa) → the no-overlap guarantee
        with self.assertRaises(L.WriterError):
            self.led.write_run(SH1, "overlord", intent="x")
        with self.assertRaises(L.WriterError):
            self.led.write_plan(SH1, "brain", status="approved")
        # happy paths
        self.led.write_plan(SH1, "brain", intent="updated intent")
        self.assertEqual(self.led.node(SH1)["plan"]["intent"], "updated intent")
        self.led.write_run(SH1, "generating", cost_usd=0.42)
        self.assertEqual(self.led.node(SH1)["run"]["cost_usd"], 0.42)

    # 3 — illegal status transition raises; legal ones pass
    def test_status_machine(self):
        with self.assertRaises(L.StatusError):
            self.led.set_status(SH1, "approved", "overlord")  # pending→approved illegal
        with self.assertRaises(L.WriterError):
            self.led.set_status(SH1, "generating", "brain")    # brain can't set status
        # legal chain
        for s in ("generating", "landed", "judging", "approved"):
            self.led.set_status(SH1, s, "overlord")
        self.assertEqual(self.led.node(SH1)["run"]["status"], "approved")
        # approved is terminal via set_status
        with self.assertRaises(L.StatusError):
            self.led.set_status(SH1, "generating", "overlord")
        # but a plan edit demotes approved → pending
        self.led.write_plan(SH1, "brain", intent="re-planned")
        self.assertEqual(self.led.node(SH1)["run"]["status"], "pending")

    # 4 — runnable_frontier before/after locking the asset refs
    def test_runnable_frontier(self):
        # initially: assets are runnable (ref_status none); shots blocked on unlocked refs
        fr = set(self.led.runnable_frontier())
        self.assertIn("char_lin", fr)
        self.assertIn("scene_throne", fr)
        self.assertNotIn(SH1, fr)  # deps char_lin/scene_throne not locked

        # lock both refs → sh01 becomes runnable, sh02 still waits on sh01
        for aid in ("char_lin", "scene_throne"):
            for s in ("drafting", "judging", "locked"):
                self.led.set_status(aid, s, "overlord")
        fr = set(self.led.runnable_frontier())
        self.assertIn(SH1, fr)
        self.assertNotIn(SH2, fr)  # sh02 depends on sh01 (not yet approved)

        # approve sh01 → sh02 frontier-ready
        for s in ("generating", "landed", "judging", "approved"):
            self.led.set_status(SH1, s, "overlord")
        fr = set(self.led.runnable_frontier())
        self.assertIn(SH2, fr)

    # 4b — reset_interrupted crash recovery
    def test_reset_interrupted(self):
        self.led.set_status(SH1, "generating", "overlord")
        reset = self.led.reset_interrupted()
        self.assertIn(SH1, reset)
        self.assertEqual(self.led.node(SH1)["run"]["status"], "pending")

    # 5 — lesson append + retrieve (hit_count increments, ordering)
    def test_lesson_store(self):
        self.led.append_lesson({
            "lesson_id": "L1", "scope": {"category": "drift", "model": "veo3", "style_id": "国漫暗黑"},
            "symptom": "hair color shifted", "fix": "inject 固定特征词", "prompt_delta": "+银灰色眼睛"})
        self.led.append_lesson({
            "lesson_id": "L2", "scope": {"category": "drift", "model": "veo3"},
            "symptom": "generic drift", "fix": "re-anchor", "prompt_delta": ""})
        self.led.append_lesson({
            "lesson_id": "L3", "scope": {"category": "anatomy", "model": "veo3"},
            "symptom": "extra fingers", "fix": "negative floor", "prompt_delta": "-extra fingers"})

        got = self.led.lessons_for({"category": "drift", "model": "veo3", "style_id": "国漫暗黑"}, k=3)
        ids = [g["lesson_id"] for g in got]
        self.assertEqual(ids[0], "L1")          # style-specific ranks first
        self.assertNotIn("L3", ids)             # different category excluded
        self.assertEqual(got[0]["hit_count"], 1)  # retrieval is a hit
        # retrieving again bumps hit_count
        again = self.led.lessons_for({"category": "drift", "model": "veo3"}, k=3)
        self.assertEqual(self.led.doc["lessons"][0]["hit_count"], 2)
        self.assertEqual(len(again), 2)

    # 6 — atomic save round-trips
    def test_atomic_save_roundtrip(self):
        self.led.write_run(SH1, "generating", cost_usd=1.23)
        self.led.append_lesson({"lesson_id": "LX", "scope": {"category": "drift", "model": "m"},
                                "symptom": "s", "fix": "f"})
        self.led.save()
        reloaded = L.load(self.tmp)
        self.assertEqual(reloaded.node(SH1)["run"]["cost_usd"], 1.23)
        self.assertEqual(reloaded.doc["lessons"][-1]["lesson_id"], "LX")
        reloaded.validate()  # still schema-valid after a write cycle
        # no leftover temp files
        leftovers = [f for f in os.listdir(self.tmp) if f.startswith(".ledger.")]
        self.assertEqual(leftovers, [])

    # 7 — attempt history + content-addressed artifact path
    def test_attempt_and_artifact_path(self):
        ap = L.artifact_path(self.tmp, SH1, "a1b2c3", "mp4")
        self.assertTrue(ap.endswith(os.path.join("artifacts", SH1, "a1b2c3.mp4")))
        self.led.append_attempt(SH1, {"attempt_id": "a1b2c3", "seed": 7, "model": "veo3",
                                      "artifact_path": ap, "thumb_path": ap + ".png"})
        self.assertEqual(self.led.current_artifact(SH1)["attempt_id"], "a1b2c3")
        self.led.append_verdict(SH1, {"node_id": SH1, "modality": "video", "attempt": 1,
                                      "score": 0.9, "pass": True, "failure_mode": "pass"})
        self.assertTrue(self.led.node(SH1)["run"]["attempts"][-1]["verdict"]["pass"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
