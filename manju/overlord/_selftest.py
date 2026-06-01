"""Overlord self-test — deterministic, runs against projects/_scratch_ovl.

Proves (per the Phase-4 spec):
  1. a landed shot with a passing verdict → approved + wake_dependents advances frontier
  2. the seeded failing node runs the re-roll: lesson appended, attempt++, re-gens, then passes
  3. the drift path: a drift verdict flips the ref node to needs_regen and the shot to blocked_on_ref
  4. build_context_sheet for a video node produces a real 3x3 contact-sheet PNG via ffmpeg
  5. judge_one is idempotent (second call on a non-landed node is a no-op)
  6. on_artifact_landed works from a --node-id arg

Usage: python -m manju.overlord._selftest   (copies projects/demo → projects/_scratch_ovl)
Exit 0 = all assertions passed.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DEMO = os.path.join(_REPO, "projects", "demo")
_SCRATCH = os.path.join(_REPO, "projects", "_scratch_ovl")

from manju.ledger import load  # noqa: E402
from manju.overlord import control, judge as judgemod, poller  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ok   {msg}")
    else:
        _FAIL += 1
        print(f"  FAIL {msg}")


def fresh_scratch() -> str:
    if os.path.exists(_SCRATCH):
        shutil.rmtree(_SCRATCH)
    os.makedirs(_SCRATCH)
    shutil.copyfile(os.path.join(_DEMO, "ledger.json"),
                    os.path.join(_SCRATCH, "ledger.json"))
    return _SCRATCH


def lock_assets(project_dir: str) -> None:
    """Generate + judge the bible assets so their refs lock (gates the shots)."""
    for aid in ("char_lin", "scene_throne"):
        control.enqueue_generation(aid, project_dir)
        control.judge_one(aid, project_dir)


def main() -> int:
    pd = fresh_scratch()
    print(f"\n[selftest] scratch = {pd}\n")

    # ── lock the assets first (image path: pass → ref_status locked, wakes shots) ──
    print("[1] asset refs: generate → judge → lock")
    lock_assets(pd)
    led = load(pd)
    check(led.node("char_lin")["run"]["ref_status"] == "locked", "char_lin ref locked")
    check(led.node("scene_throne")["run"]["ref_status"] == "locked", "scene_throne ref locked")
    check(led.node("char_lin")["run"]["locked_seed"] is not None, "char_lin locked_seed set")
    frontier = led.runnable_frontier()
    check("ep01.sc01.sh01" in frontier, "sh01 entered frontier after refs locked (wake_dependents)")

    # ── DRIFT path: sh01 is seeded to drift on attempt 1 ──────────────────────────
    # INTEGRATION CHANGE: the drift verdict still fires + records a drift lesson, but
    # because its ref (char_lin) is already LOCKED (terminal, no re-draftable ref to
    # wait on), the overlord RESOLVES the drift by re-rolling the SHOT itself (a fresh
    # seed; the drift seed clears at attempt 2) rather than WEDGING it forever in
    # blocked_on_ref against a terminal ref. judge_one returns the drift verdict and
    # leaves sh01 `landed` (the re-rolled, drift-free take) for the next judge pass.
    print("\n[2] drift path: sh01 seeded-drift → drift lesson + SHOT re-roll (terminal ref)")
    lessons_before_drift = len(load(pd).doc.get("lessons", []))
    control.enqueue_generation("ep01.sc01.sh01", pd)
    led = load(pd)
    check(led.node("ep01.sc01.sh01")["run"]["status"] == "landed", "sh01 landed after gen")
    v = control.judge_one("ep01.sc01.sh01", pd)
    check(v is not None and v.get("drift") is True, "sh01 drift verdict emitted")
    led = load(pd)
    check(led.node("ep01.sc01.sh01")["run"]["final_verdict"]["failure_mode"] == "drift",
          "drift verdict recorded on the node")
    check(len(led.doc.get("lessons", [])) == lessons_before_drift + 1,
          "drift appended a lesson (the moat learns from the drift)")
    check(len(led.node("ep01.sc01.sh01")["run"]["attempts"]) == 2,
          "sh01 re-rolled a fresh take (attempt 2) to resolve the drift")
    check(led.node("ep01.sc01.sh01")["run"]["status"] == "landed",
          "sh01 re-landed (drift resolved by SHOT re-roll, NOT wedged in blocked_on_ref)")

    # ── judge the re-rolled take: attempt 2 is drift-free → passes → approved ──────
    print("\n[3] sh01 attempt 2 (drift seed cleared) → pass → approved, wakes sh02")
    v = control.judge_one("ep01.sc01.sh01", pd)
    led = load(pd)
    check(v is not None and v.get("pass") is True, "sh01 attempt 2 passes (drift seed cleared)")
    check(led.node("ep01.sc01.sh01")["run"]["status"] == "approved", "sh01 → approved")
    check("ep01.sc01.sh02" in led.runnable_frontier(), "sh02 woken into frontier after sh01 approved")

    # ── RE-ROLL + LESSON path: sh02 seeded to fail attempt 1, then pass ───────────
    print("\n[4] re-roll + lesson: sh02 fails attempt 1 → lesson + re-roll → passes")
    lessons_before = len(load(pd).doc.get("lessons", []))
    control.enqueue_generation("ep01.sc01.sh02", pd)
    led = load(pd)
    check(led.node("ep01.sc01.sh02")["run"]["status"] == "landed", "sh02 landed")
    v = control.judge_one("ep01.sc01.sh02", pd)  # fails attempt 1 → appends lesson, re-rolls, re-lands
    led = load(pd)
    lessons_after = len(led.doc.get("lessons", []))
    check(lessons_after == lessons_before + 1, f"one lesson appended ({lessons_before}→{lessons_after})")
    attempts = led.node("ep01.sc01.sh02")["run"]["attempts"]
    check(len(attempts) == 2, f"sh02 attempt incremented to 2 (re-roll), got {len(attempts)}")
    check(attempts[0].get("lesson_ref"), "failing attempt back-references its lesson")
    check(attempts[0]["attempt_id"] != attempts[1]["attempt_id"], "re-roll produced a NEW attempt_id (new seed)")
    check(led.node("ep01.sc01.sh02")["run"]["status"] == "landed", "sh02 re-landed for the next judge pass")
    # judge the re-roll → passes (attempt 2 > seeded until_attempt 1)
    v2 = control.judge_one("ep01.sc01.sh02", pd)
    led = load(pd)
    check(v2 is not None and v2.get("pass") is True, "sh02 attempt 2 passes")
    check(led.node("ep01.sc01.sh02")["run"]["status"] == "approved", "sh02 → approved")

    # ── verify the appended lesson is retrievable by (category, model) ────────────
    print("\n[5] lesson is retrievable by scope (category, model)")
    led = load(pd)
    got = led.lessons_for({"category": "off-prompt", "model": "mock", "style_id": "国漫暗黑"})
    check(len(got) >= 1, "lessons_for returns the appended off-prompt lesson")

    # ── CONTACT SHEET: build_context_sheet for a video node makes a real 3x3 PNG ──
    print("\n[6] build_context_sheet (video) → real 3x3 contact-sheet PNG via ffmpeg")
    led = load(pd)
    sheet = judgemod.build_context_sheet(led, "ep01.sc01.sh01", pd)  # sh01 is a video node
    check(sheet["modality"] == "video", "sh01 judged as video modality")
    cs = sheet.get("contact_sheet", {})
    csp = cs.get("contact_sheet")
    check(bool(csp) and os.path.exists(csp), f"contact-sheet PNG exists: {csp}")
    check(cs.get("grid") == "3x3" and cs.get("n_frames") == 9, "3x3 / 9 frames")
    check(len(cs.get("slice_times", [])) == 9, "9 slice-center times")
    check(bool(cs.get("first_frame")) and os.path.exists(cs["first_frame"]), "first frame extracted")
    check(bool(cs.get("last_frame")) and os.path.exists(cs["last_frame"]), "last frame extracted")
    check("probe" in cs, "probe.json attached to the sheet")
    # verify the PNG is a real 3x3 tile (width ~3x a single tile via ffprobe)
    try:
        out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                              "-show_streams", csp], capture_output=True, text=True, check=True)
        st = json.loads(out.stdout)["streams"][0]
        check(st["width"] >= 900 and st["height"] >= 300,
              f"contact-sheet is a tiled grid ({st['width']}x{st['height']})")
    except Exception as e:  # noqa: BLE001
        check(False, f"ffprobe on contact-sheet failed: {e}")

    # ── IDEMPOTENCY: judge_one on a non-landed (approved) node is a no-op ─────────
    print("\n[7] judge_one idempotency: second call on a non-landed node is a no-op")
    led = load(pd)
    before = json.dumps(led.node("ep01.sc01.sh01")["run"], sort_keys=True)
    res = control.judge_one("ep01.sc01.sh01", pd)  # already approved → not landed
    led = load(pd)
    after = json.dumps(led.node("ep01.sc01.sh01")["run"], sort_keys=True)
    check(res is None, "judge_one returns None on a non-landed node")
    check(before == after, "ledger run block unchanged by the no-op judge_one")

    # ── HOOK: on_artifact_landed works from a --node-id arg ───────────────────────
    print("\n[8] on_artifact_landed --node-id: lands + judges a fresh node")
    # set up a fresh landed-able node: re-plan would be heavy; reuse a fresh scratch run
    pd2 = os.path.join(_REPO, "projects", "_scratch_ovl_hook")
    if os.path.exists(pd2):
        shutil.rmtree(pd2)
    os.makedirs(pd2)
    shutil.copyfile(os.path.join(_DEMO, "ledger.json"), os.path.join(pd2, "ledger.json"))
    lock_assets(pd2)
    # generate sh01 (lands it), then drive the hook by --node-id (it should judge it).
    control.enqueue_generation("ep01.sc01.sh01", pd2)
    r = subprocess.run([sys.executable, "-m", "manju.overlord.on_artifact_landed",
                        "--node-id", "ep01.sc01.sh01", "--project-dir", pd2],
                       capture_output=True, text=True, cwd=_REPO)
    check(r.returncode == 0, "on_artifact_landed exits 0")
    led2 = load(pd2)
    check(led2.node("ep01.sc01.sh01")["run"]["final_verdict"] is not None,
          "hook produced a verdict on the node (judge_one ran)")
    shutil.rmtree(pd2)

    # ── POLLER: async submit → poll → land → judge (sidecar queue) ────────────────
    print("\n[9] poller: async submit → poll_once drains → judges → self-terminates when idle")
    pd3 = os.path.join(_REPO, "projects", "_scratch_ovl_poll")
    if os.path.exists(pd3):
        shutil.rmtree(pd3)
    os.makedirs(pd3)
    shutil.copyfile(os.path.join(_DEMO, "ledger.json"), os.path.join(pd3, "ledger.json"))
    lock_assets(pd3)
    led3 = load(pd3)
    led3.set_status("ep01.sc01.sh01", "generating", "overlord")  # pending → generating (submitted async)
    led3.save()
    req = control._build_request(load(pd3), "ep01.sc01.sh01", seed=99, project_dir=pd3)
    poller.submit_async("ep01.sc01.sh01", req, pd3)
    summary = poller.poll_once(pd3)
    check("ep01.sc01.sh01" in summary["completed"], "poller drained + judged the submitted job")
    idle = poller.poll_once(pd3)  # nothing left
    check(idle["idle"] is True and idle["submitted"] == 0, "poller self-terminates idle when queue empty")
    shutil.rmtree(pd3)

    # ── tick: resumable driver advances the frontier end-to-end on a clean copy ───
    # INTEGRATION CHANGE: under pure tick() the whole graph now CONVERGES — assets
    # lock, sh01's seeded-drift self-resolves via a SHOT re-roll, sh02's seeded-fail
    # re-rolls + appends a lesson, and both shots reach `approved`. No manual unblock.
    print("\n[10] tick(): resumable driver converges the whole frontier on a clean scratch")
    pd4 = fresh_scratch()
    for _ in range(12):  # bounded loop; each tick advances + re-rolls until quiescent
        summary = control.tick(pd4)
        if not summary["generated"]:
            break
    led4 = load(pd4)
    statuses = {n["id"]: n["run"].get("status") for n in led4.nodes(kind="shot")}
    refstat = {n["id"]: n["run"].get("ref_status") for n in led4.nodes(kind="asset")}
    print(f"      shot statuses: {statuses}")
    print(f"      asset ref_status: {refstat}")
    check(all(s == "locked" for s in refstat.values()), "all asset refs locked by tick")
    check(all(s == "approved" for s in statuses.values()),
          "ALL shots approved by pure tick (drift + fail both self-resolved)")
    check(len(led4.doc.get("lessons", [])) >= 1, "≥1 lesson appended during the tick run")
    rerolled = any(len(n["run"].get("attempts", [])) >= 2 for n in led4.nodes(kind="shot"))
    check(rerolled, "≥1 shot re-rolled (the loop actually converged, not first-try)")

    print(f"\n[selftest] {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
