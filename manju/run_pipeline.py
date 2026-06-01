"""The ONE top-level driver — brain → overlord loop → compose, end-to-end.

This is the single "plug in keys and go" entrypoint. It is THIN: it orchestrates
the existing layer entrypoints and reimplements none of them.

  run(project_dir, max_ticks=50) -> summary
      reset_interrupted → loop tick(project_dir) until the runnable frontier is empty
      (or stops advancing, guarded by max_ticks) → compose(load(project_dir), ...).
      Returns {assets_locked, shots_approved, shots_total, lessons, reroll_count,
               final_mp4, ticks}.

CLI:
  python -m manju.run_pipeline --project-dir projects/<n>
  python -m manju.run_pipeline --from-brain "<seed_idea>" --project-dir projects/<n> \
      [--题材 ...] [--集数N 1] [--时长 60] [--主爽点类型 身份碾压] [--style-id 国漫暗黑]
      → authors the ledger via brain.plan(...) first, then runs.

Seams reused (never reimplemented here):
  manju.brain.brain.plan                  — authors plan.* + tree
  manju.overlord.control.tick / .reset    — referencing + builder + runner + judge loop
  manju.skills.composing.composer.compose — final render + handoff artifacts

Standard library only.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from manju.ledger import load
from manju.overlord import control
from manju.skills.composing.composer import compose

# ── composing_scenes seam (CONTRACTS §6) — storyboards/keyframe stills. A missing
# module never breaks the driver; storyboarding is idempotent + tolerant of refs
# that are not yet locked (a shot only gains a keyframe still once its refs exist).
try:
    from manju.skills.composing_scenes.storyboarder import storyboard_all as _storyboard_all
except Exception:  # noqa: BLE001 — layer absent: run the pipeline without storyboards
    _storyboard_all = None


def _emit_storyboards(project_dir: str) -> None:
    """Emit per-shot storyboards for shots whose refs are ready (skip-if-exists).

    Called after refs lock and BEFORE shot generation each pass so the builder can
    seed i2v on the keyframe still. Tolerant: a shot whose refs are not yet locked
    still gets a spec (no still) and re-gains the still on a later pass. Never raises.
    """
    if _storyboard_all is None:
        return
    try:
        _storyboard_all(load(project_dir), project_dir)
    except Exception as e:  # noqa: BLE001 — storyboarding is best-effort, never fatal
        print(f"[run_pipeline] storyboard pass skipped: {e}", file=sys.stderr)

# terminal states a node may legitimately rest in (per CONTRACTS §1.3).
_SHOT_TERMINAL = {"approved", "skipped", "paused"}
_ASSET_TERMINAL = {"locked", "rejected"}


def _reroll_count(ledger) -> int:
    """Total re-rolls = Σ(attempts−1) over every node that has ≥1 attempt.

    A node that landed on the first take has 1 attempt (0 re-rolls); each extra
    attempt is one re-roll (a new seed ⇒ a new content-addressed take).
    """
    n = 0
    for node, _kind in ledger._index.values():
        attempts = node.get("run", {}).get("attempts", [])
        if attempts:
            n += len(attempts) - 1
    return n


def _progress_key(ledger) -> tuple:
    """A cheap fingerprint of overall progress; used to detect a stalled loop.

    Counts terminal nodes + total attempts. If two consecutive ticks leave this
    unchanged AND the frontier is empty, the loop has quiesced and we stop.
    """
    assets_locked = sum(1 for a in ledger.nodes(kind="asset")
                        if a["run"].get("ref_status") == "locked")
    shots_approved = sum(1 for s in ledger.nodes(kind="shot")
                         if s["run"].get("status") == "approved")
    attempts = sum(len(n.get("run", {}).get("attempts", []))
                   for n, _ in ledger._index.values())
    return (assets_locked, shots_approved, attempts)


def run(project_dir: str, max_ticks: int = 50) -> dict:
    """Drive the whole pipeline: overlord loop to quiescence, then compose.

    Loops tick(project_dir) until the runnable frontier is empty or progress stops
    advancing (guarded by max_ticks). Then composes the approved shots into a final
    render. Returns a summary dict. Idempotent: a finished project just re-composes.
    """
    # crash recovery before we start (tick also does this each pass).
    led = load(project_dir)
    led.reset_interrupted()
    led.save()

    ticks = 0
    last_key: Optional[tuple] = None
    for _ in range(max_ticks):
        frontier = load(project_dir).runnable_frontier()
        if not frontier:
            break
        # emit storyboards for shots whose refs are ready BEFORE shot generation, so
        # the builder seeds i2v on the keyframe still. Idempotent + skip-if-exists.
        _emit_storyboards(project_dir)
        control.tick(project_dir)
        ticks += 1
        key = _progress_key(load(project_dir))
        # stall guard: frontier non-empty but nothing advanced two ticks running.
        if key == last_key:
            break
        last_key = key

    led = load(project_dir)
    assets = led.nodes(kind="asset")
    shots = led.nodes(kind="shot")
    assets_locked = sum(1 for a in assets if a["run"].get("ref_status") == "locked")
    shots_approved = sum(1 for s in shots if s["run"].get("status") == "approved")
    lessons = len(led.doc.get("lessons", []))
    reroll_count = _reroll_count(led)

    # compose only when there is at least one approved shot with a usable artifact.
    final_mp4: Optional[str] = None
    composable = any(
        s["run"].get("status") == "approved" and (s["run"].get("current_artifact") or {}).get("path")
        for s in shots
    )
    if composable:
        result = compose(load(project_dir), project_dir)
        final_mp4 = result["final"]

    return {
        "assets_locked": assets_locked,
        "shots_approved": shots_approved,
        "shots_total": len(shots),
        "lessons": lessons,
        "reroll_count": reroll_count,
        "final_mp4": final_mp4,
        "ticks": ticks,
    }


# ── CLI ────────────────────────────────────────────────────────────────────────
def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="python -m manju.run_pipeline",
        description="The one driver: (optionally author via brain) → overlord loop → compose.",
    )
    ap.add_argument("--project-dir", required=True, help="project dir (projects/<n>)")
    ap.add_argument("--max-ticks", type=int, default=50, help="loop guard (default 50)")
    ap.add_argument("--from-brain", metavar="SEED_IDEA",
                    help="author the ledger first via brain.plan(seed_idea, knobs, project_dir)")
    # knob flags (only consulted with --from-brain). Chinese keys are literal.
    ap.add_argument("--题材", dest="题材", default="都市玄幻")
    ap.add_argument("--集数N", dest="集数N", type=int, default=1)
    ap.add_argument("--时长", dest="时长", type=int, default=60)
    ap.add_argument("--主爽点类型", dest="主爽点类型", default="身份碾压")
    ap.add_argument("--style-id", dest="style_id", default="国漫暗黑")
    return ap.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if args.from_brain:
        # author the plan columns first (the brain never calls a model/network).
        from manju.brain.brain import plan as brain_plan
        knobs = {
            "题材": args.题材,
            "集数N": args.集数N,
            "时长": args.时长,
            "主爽点类型": args.主爽点类型,
            "style_id": args.style_id,
        }
        path = brain_plan(args.from_brain, knobs, args.project_dir)
        print(f"[run_pipeline] authored ledger: {path}", file=sys.stderr)

    if not os.path.isfile(os.path.join(args.project_dir, "ledger.json")):
        print(f"[run_pipeline] no ledger.json in {args.project_dir!r} "
              f"(use --from-brain to author one first)", file=sys.stderr)
        return 2

    summary = run(args.project_dir, max_ticks=args.max_ticks)
    print(f"[run_pipeline] summary: {summary}", file=sys.stderr)
    # one clean line on stdout: the summary as JSON for downstream tooling.
    import json
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
