"""The control plane — sequential lazy re-roll loop (CONTRACTS §4, Layer 3).

This is CODE. It cannot fake quality: it only assembles the context-sheet, calls
the stateless JUDGE, records the verdict, and drives the status machine per the
verdict+action policy. Perception lives entirely in judge.JUDGE.

Entrypoints:
  enqueue_generation(node_id, project_dir) — build the canonical request (reuse
      building_prompts.request_for_shot if importable, else a minimal request),
      call the generating runner through the seam, append the attempt, set landed.
  judge_one(node_id, project_dir) — the idempotent re-roll step:
      load → if status != landed: no-op → build sheet → JUDGE → append_verdict →
      branch on the verdict+action policy (pass / drift / fail<N_MAX / fail>=N_MAX).
  tick(project_dir) — resumable driver over runnable_frontier(): generate pending
      frontier nodes → land → judge_one each.

Seams (CONTRACTS §6) — real import first, documented stub on ImportError:
  generating runner: run_request(req, project_dir) -> envelope
  building_prompts:  request_for_shot(ledger, node_id) -> canonical request  (optional)

Standard library only.
"""
from __future__ import annotations

import datetime
import os
import random
from typing import Any, Optional

from manju.ledger import load, Ledger

from . import judge as _judge

# ── seam: the generating runner (re-gen goes THROUGH this, never reimplemented) ─
try:
    from manju.skills.generating.runner import run_request  # real
except ImportError:  # pragma: no cover
    from manju.skills.generating._stub import run_request  # documented mock envelope

# ── seam: building_prompts — request_for_shot(ledger, shot_id, project_dir, seed,
#    model="mock") -> canonical request. The rich 5-part time-coded prompt lives in
#    the `builder` module (NOT the package root); import it from there so a SHOT's
#    request is the real one, with _minimal_request only as a last-resort fallback. ─
try:
    from manju.skills.building_prompts.builder import request_for_shot as _request_for_shot  # real
except ImportError:  # pragma: no cover — builder always present in this repo
    _request_for_shot = None  # we fall back to a minimal request below

# ── seam: referencing (the MOAT) — draft_refs(ledger, project_dir, asset_id) drafts
#    the dual-anchor ref sheet (locked_seed + ref_tag + ref_sheet folders) and steps
#    the asset none→drafting. The overlord judge then flips drafting→judging→locked. ─
try:
    from manju.skills.referencing.referencer import draft_refs as _draft_refs  # real
except ImportError:  # pragma: no cover — referencer always present in this repo
    _draft_refs = None

N_MAX = 4  # max re-roll attempts before human escalation (CONTRACTS §4)
WRITER = "overlord"

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _is_asset(ledger: Ledger, node_id: str) -> bool:
    return ledger._index[node_id][1] == "asset"


# ── request construction (reuse building_prompts, else a minimal request) ──────
def _minimal_request(ledger: Ledger, node_id: str, seed: int) -> dict:
    """A minimal-but-valid canonical request when building_prompts isn't wired.

    Assets → kind:image (draw the reference). Shots → kind:video (i2v), anchored on
    the locked reference images of their ref assets. Prompt is assembled from the
    plan + style negative floor so the request validates and content-addresses.
    """
    node = ledger.node(node_id)
    plan = node.get("plan", {})
    kind = "image" if _is_asset(ledger, node_id) else "video"

    # gather reference images from this node's ref assets (locked ref sheets).
    ref_images: list[str] = []
    ref_ids = plan.get("ref_ids", []) if not _is_asset(ledger, node_id) else []
    for rid in ref_ids:
        try:
            rnode = ledger.node(rid)
        except KeyError:
            continue
        if ledger._index[rid][1] == "asset":
            ref_images.extend(rnode.get("run", {}).get("ref_image_paths", []) or [])
    ref_images = ref_images[:9]

    # style negative floor → positive constraints in the prompt tail.
    style_id = plan.get("style_id", "")
    neg = []
    for st in ledger.doc.get("styles", []):
        if st.get("id") == style_id:
            neg = st.get("negative_floor", [])
            break

    if _is_asset(ledger, node_id):
        subject = plan.get("descriptor", node_id)
        kw = "，".join(plan.get("ai_draw_keywords", []) + plan.get("固定特征词", []))
        prompt = f"{subject}. {kw}. style={style_id}. avoid: {', '.join(neg)}".strip()
        duration_s = None
    else:
        intent = plan.get("intent", "")
        action = plan.get("action", "")
        cam = plan.get("camera", {}) or {}
        camera = f"{cam.get('shot_size','')} {cam.get('movement','')} {cam.get('lens_mm','')}mm"
        prompt = (f"Subject·{intent} | Action·{action} | Camera·{camera} | "
                  f"Style·{style_id} | Constraints·avoid {', '.join(neg)}").strip()
        duration_s = plan.get("duration_s")

    req: dict[str, Any] = {
        "kind": kind,
        "prompt": prompt or f"{node_id} placeholder prompt",
        "reference_images": ref_images,
        "duration_s": duration_s,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
        "seed": seed,
        "model": "mock",
        "node_id": node_id,
    }
    return req


def _build_request(ledger: Ledger, node_id: str, seed: int, project_dir: str,
                   model: str = "mock") -> dict:
    """Build the canonical runner request for a SHOT via the real builder seam.

    A SHOT's request comes from building_prompts.request_for_shot — the rich 5-part
    time-coded prompt anchored on the referenced assets' locked ref images. We thread
    `project_dir` + `seed` + `model` through per its real signature
    `request_for_shot(ledger, shot_id, project_dir, seed, model="mock")`. We force
    this node's `seed` + `node_id` so the re-roll knob and content addressing stay
    under the overlord's control (a new seed ⇒ a new attempt_id). `_minimal_request`
    is the genuine last-resort fallback only (builder missing or a build error).
    """
    if _request_for_shot is not None and not _is_asset(ledger, node_id):
        try:
            req = _request_for_shot(ledger, node_id, project_dir, seed, model)
            req["seed"] = seed                 # overlord owns the re-roll knob
            req.setdefault("node_id", node_id)
            req.setdefault("model", model)
            return req
        except Exception:  # noqa: BLE001 — fall back rather than fail the loop
            pass
    return _minimal_request(ledger, node_id, seed)


# ── asset path: referencing.draft_refs (the MOAT) → drafting → judging ─────────
def _enqueue_asset(node_id: str, project_dir: str) -> dict:
    """Draft a bible asset's dual-anchor reference sheet via referencing.draft_refs.

    referencing owns the asset run block: it builds the dual-anchor prompt, assigns
    the deterministic locked_seed + ref_tag, drafts into ref_sheet/{char,scene}/NN/,
    appends the attempt, writes ref_image_paths, and steps ref_status none→drafting.
    We then step drafting→judging so judge_one can flip judging→locked (which wakes
    dependent shots). draft_refs is idempotent (skip-if-exists), so a node already
    past `none` just re-judges. Returns a synthetic envelope for the tick summary.
    """
    if _draft_refs is None:  # pragma: no cover — referencer always present here
        return _enqueue_via_runner(node_id, project_dir, None)

    ledger = load(project_dir)
    cur = ledger.node(node_id)["run"].get("ref_status", "none")
    # draft_refs only acts on a fresh `none` ref; it sets none→drafting + writes run.
    if cur == "none":
        res = _draft_refs(ledger, project_dir, node_id)  # saves internally
    else:
        res = {node_id: {"skipped": True}}

    # step drafting→judging so judge_one can lock it (idempotent if already judging).
    ledger = load(project_dir)
    if ledger.node(node_id)["run"].get("ref_status") == "drafting":
        ledger.set_status(node_id, "judging", WRITER)
        ledger.save()

    run = load(project_dir).node(node_id)["run"]
    out = run.get("ref_image_paths", [])
    return {"model": "mock", "output_files": out,
            "data": {"attempt_id": run.get("current_attempt_id"),
                     "ref": res.get(node_id, {})}}


# ── shot path: building_prompts request → runner → append_attempt → landed ─────
def _enqueue_via_runner(node_id: str, project_dir: str, seed: Optional[int]) -> dict:
    """Generate (or reuse) one SHOT take via the builder request + runner seam."""
    ledger = load(project_dir)

    # choose a seed: explicit > deterministic per-attempt > random.
    if seed is None:
        attempts = ledger.node(node_id)["run"].get("attempts", [])
        seed = (ledger.node(node_id)["run"].get("locked_seed")
                or random.Random(f"{node_id}|{len(attempts)}").randint(1, 2**31 - 1))

    # move into the generating state (validates pending|needs_regen → generating).
    cur = ledger.node(node_id)["run"].get("status")
    if cur in ("pending", "needs_regen"):
        ledger.set_status(node_id, "generating", WRITER)
        ledger.save()

    req = _build_request(ledger, node_id, seed, project_dir)
    envelope = run_request(req, project_dir)

    data = envelope.get("data", {})
    out_files = envelope.get("output_files", [])
    artifact_path = out_files[0] if out_files else None
    attempt_id = data.get("attempt_id")

    # re-load (the runner may have touched disk; ledger writes are short critical sections).
    ledger = load(project_dir)
    ledger.append_attempt(node_id, {
        "attempt_id": attempt_id,
        "ts": _now(),
        "seed": seed,
        "model": envelope.get("model", "mock"),
        "prompt": req.get("prompt", ""),
        "artifact_path": artifact_path,
        "thumb_path": data.get("thumb_path"),
        "verdict": None,
        "lesson_ref": None,
    })
    ledger.set_status(node_id, "landed", WRITER)  # generating → landed
    ledger.save()
    return envelope


# ── enqueue_generation — dispatch asset → referencing, shot → builder+runner ───
def enqueue_generation(node_id: str, project_dir: str, seed: Optional[int] = None) -> dict:
    """Generate (or reuse) one take and move the node into its landed gate.

    Dispatch: an ASSET drafts its ref sheet via referencing.draft_refs (→ judging);
    a SHOT builds the rich 5-part request and runs it via the runner seam (→ landed).
    The mock is synchronous, so we land immediately. Returns the runner envelope.
    Re-roll (shots): pass a fresh `seed` ⇒ new attempt_id ⇒ new content-addressed path.
    """
    if _is_asset(load(project_dir), node_id):
        return _enqueue_asset(node_id, project_dir)
    return _enqueue_via_runner(node_id, project_dir, seed)


# ── judge_one — the idempotent sequential lazy re-roll step ────────────────────
def _landed_state(ledger: Ledger, node_id: str, asset: bool) -> str:
    return (ledger.node(node_id)["run"].get("ref_status") if asset
            else ledger.node(node_id)["run"].get("status"))


def judge_one(node_id: str, project_dir: str) -> Optional[dict]:
    """Judge ONE landed artifact and act on the verdict (CONTRACTS §4). Idempotent.

    Pseudocode (verbatim):
        row = load(node);  if status != landed: return         # no-op
        v = JUDGE(build_context_sheet(row))                     # one inference
        append_verdict(node, v)
        if v.drift:  ref_node→needs_regen; node→blocked_on_ref
        elif v.pass: node→approved + write final_artifact; wake_dependents
        else:        append_lesson; if attempt>=N_MAX: paused+escalate
                     else: needs_regen + re-roll ONE candidate (new seed) → land

    Assets use the analogous path: a passing ref judge flips ref_status
    judging→locked and wakes dependent shots. Returns the verdict (or None on no-op).
    """
    ledger = load(project_dir)
    if node_id not in ledger._index:
        return None
    asset = _is_asset(ledger, node_id)

    # the "landed" gate. shots: status==landed. assets: ref_status==judging.
    state = _landed_state(ledger, node_id, asset)
    landed_state = "judging" if asset else "landed"
    if state != landed_state:
        return None  # idempotent no-op

    # shot landed → judging (asset is already judging).
    if not asset:
        ledger.set_status(node_id, "judging", WRITER)
        ledger.save()

    # build the sheet FROM THE LEDGER and run ONE stateless inference.
    sheet = _judge.build_context_sheet(ledger, node_id, project_dir)
    verdict = _judge.JUDGE(sheet)

    # re-load before the short write critical section (hook/poller/judge may race).
    ledger = load(project_dir)
    ledger.append_verdict(node_id, verdict)
    ledger.save()

    attempt = verdict.get("attempt", sheet.get("attempt", 1))

    # ── branch on the verdict+action policy table ─────────────────────────────
    if verdict.get("drift"):
        # drift: the shot drifted from its bible reference (禁止变化项 violated).
        # Policy: regen the REFERENCE, fence the shot on it (blocked_on_ref). But a
        # ref that is already `locked` is TERMINAL — there is no re-draftable ref to
        # wait on, so a plain block would WEDGE the shot forever. In that case the
        # drift can only be resolved by re-rolling the SHOT on a fresh seed (a new
        # take that no longer drifts). We append the drift lesson, then either:
        #   • re-draftable ref present → reject the ref + block the shot (it re-locks
        #     and wakes the shot), or
        #   • all refs terminally locked → re-roll the shot itself (drift recovery).
        ledger = load(project_dir)
        _append_fail_lesson(ledger, node_id, verdict, sheet)
        ledger.save()

        ledger = load(project_dir)
        ref_id = _drift_ref(ledger, node_id)
        ref_redraftable = False
        if ref_id is not None:
            rstate = ledger.node(ref_id)["run"].get("ref_status")
            if rstate in ("judging", "drafting"):
                ledger.set_status(ref_id, "rejected", WRITER)
                ref_redraftable = True

        if asset:
            # an asset that drifts from its own bible just gets rejected → re-draft.
            ledger.set_status(node_id, "rejected", WRITER)
            ledger.save()
            return verdict

        if ref_redraftable:
            # a re-draftable ref exists → fence the shot until it re-locks.
            ledger.set_status(node_id, "blocked_on_ref", WRITER)
            ledger.save()
            return verdict

        # all refs terminally locked → resolve the drift by re-rolling the SHOT.
        if attempt >= N_MAX:
            ledger.set_status(node_id, "paused", WRITER)  # judging → paused (human fence)
            _attach_escalation(ledger, node_id, verdict, sheet)
            ledger.save()
            return verdict
        # judging → needs_regen → re-roll one fresh take (the drift seed clears).
        ledger.set_status(node_id, "needs_regen", WRITER)
        ledger.save()
        enqueue_generation(node_id, project_dir, seed=_reroll_seed(node_id, attempt))
        return verdict

    if verdict.get("pass"):
        ledger = load(project_dir)
        if asset:
            ledger.set_status(node_id, "locked", WRITER)  # wakes dependents in the kernel
            # lock the winning seed (the take that passed).
            attempts = ledger.node(node_id)["run"].get("attempts", [])
            if attempts and attempts[-1].get("seed") is not None:
                ledger.write_run(node_id, WRITER, locked_seed=attempts[-1]["seed"])
            woken = ledger.wake_dependents(node_id)
        else:
            ledger.set_status(node_id, "approved", WRITER)  # wakes dependents in the kernel
            art = ledger.current_artifact(node_id)
            if art:
                ledger.write_run(node_id, WRITER, current_artifact=art)  # final_artifact == current
            woken = ledger.wake_dependents(node_id)
        ledger.save()
        verdict = dict(verdict)
        verdict["_woke"] = woken
        return verdict

    # ── fail ──────────────────────────────────────────────────────────────────
    # append a lesson keyed by (category, model, style_id, asset_kind).
    ledger = load(project_dir)
    _append_fail_lesson(ledger, node_id, verdict, sheet)
    ledger.save()

    if attempt >= N_MAX:
        # human escalation: pause + attach the verdict + the sheet.
        ledger = load(project_dir)
        if asset:
            # assets have no 'paused' ref_status; reject → re-draft is the human fence.
            cur = ledger.node(node_id)["run"].get("ref_status")
            if cur in ("judging", "drafting"):
                ledger.set_status(node_id, "rejected", WRITER)
        else:
            ledger.set_status(node_id, "paused", WRITER)
        _attach_escalation(ledger, node_id, verdict, sheet)
        ledger.save()
        return verdict

    # fail & attempt < N_MAX → needs_regen + re-roll ONE candidate (new seed).
    ledger = load(project_dir)
    if asset:
        ledger.set_status(node_id, "rejected", WRITER)   # judging → rejected
        ledger.save()
        ledger = load(project_dir)
        ledger.set_status(node_id, "drafting", WRITER)   # rejected → drafting (re-roll)
        ledger.save()
        enqueue_generation(node_id, project_dir, seed=_reroll_seed(node_id, attempt))
    else:
        ledger.set_status(node_id, "needs_regen", WRITER)
        ledger.save()
        enqueue_generation(node_id, project_dir, seed=_reroll_seed(node_id, attempt))
    return verdict


def _reroll_seed(node_id: str, attempt: int) -> int:
    """A fresh, deterministic seed per re-roll ⇒ a new attempt_id ⇒ a new artifact."""
    return random.Random(f"{node_id}|reroll|{attempt}").randint(1, 2**31 - 1)


def _drift_ref(ledger: Ledger, node_id: str) -> Optional[str]:
    """The reference asset to blame for a drift verdict (first ref asset of the shot)."""
    plan = ledger.node(node_id).get("plan", {})
    for rid in plan.get("ref_ids", []) or ledger.node(node_id).get("deps", []):
        if rid in ledger._index and ledger._index[rid][1] == "asset":
            return rid
    return None


def _append_fail_lesson(ledger: Ledger, node_id: str, verdict: dict, sheet: dict) -> None:
    """Append a retrievable lesson scoped by (category, model, style_id, asset_kind)."""
    asset = _is_asset(ledger, node_id)
    plan = ledger.node(node_id).get("plan", {})
    style_id = plan.get("style_id", "")
    model = sheet.get("model", "mock")
    category = verdict.get("failure_mode", "fail")
    scope = {"category": category, "model": model, "style_id": style_id}
    if asset:
        scope["asset_kind"] = ledger.node(node_id).get("kind")
    n = len(ledger.doc.get("lessons", []))
    lesson = {
        "lesson_id": f"L{n + 1}",
        "scope": scope,
        "symptom": verdict.get("fix_hint", "") or f"{category} on {node_id} attempt {verdict.get('attempt')}",
        "fix": verdict.get("fix_hint", "") or "tighten prompt; inject 固定特征词; re-roll a new seed",
        "prompt_delta": "+" + "，".join(plan.get("固定特征词", [])[:2]) if plan.get("固定特征词") else "",
        "hit_count": 0,
    }
    ledger.append_lesson(lesson)
    # back-reference the lesson on the failing attempt.
    attempts = ledger.node(node_id)["run"].get("attempts", [])
    if attempts:
        attempts[-1]["lesson_ref"] = lesson["lesson_id"]


def _attach_escalation(ledger: Ledger, node_id: str, verdict: dict, sheet: dict) -> None:
    """On N_MAX escalation, write the verdict+sheet pointer to a human-review file."""
    esc_dir = os.path.join(ledger.project_dir, "escalations")
    os.makedirs(esc_dir, exist_ok=True)
    import json
    with open(os.path.join(esc_dir, f"{node_id}.json"), "w", encoding="utf-8") as f:
        json.dump({"node_id": node_id, "verdict": verdict, "sheet": sheet}, f,
                  ensure_ascii=False, indent=2)


# ── tick — the resumable driver over the frontier ─────────────────────────────
def _drain_landed(project_dir: str, judged: list[str], max_steps: int = 64) -> None:
    """Judge every shot left `landed` (a re-roll) / asset left `judging` until none.

    A failing shot's `judge_one` re-rolls ONE take and leaves it `landed` (idempotent,
    single-step). This drains those re-rolled takes through the judge so a node drives
    to a TERMINAL state (approved / paused) within the tick. Bounded by max_steps
    (N_MAX re-rolls per node ⋅ a small frontier) so a wedge can never spin forever.
    """
    for _ in range(max_steps):
        led = load(project_dir)
        pending_judge = [s["id"] for s in led.nodes(kind="shot")
                         if s["run"].get("status") == "landed"]
        pending_judge += [a["id"] for a in led.nodes(kind="asset")
                          if a["run"].get("ref_status") == "judging"]
        if not pending_judge:
            return
        for nid in pending_judge:
            judge_one(nid, project_dir)
            judged.append(nid)


def tick(project_dir: str) -> dict:
    """Process the whole runnable frontier once: generate → land → judge → drain.

    Resumable: re-running picks up wherever the ledger left off. For each frontier
    node we generate (asset → ref draft; shot → builder request + runner) then judge.
    Re-rolls leave a shot `landed`; we then drain all `landed`/`judging` nodes so each
    reaches a terminal state this tick. Returns a summary of what advanced.
    """
    ledger = load(project_dir)
    ledger.reset_interrupted()  # crash recovery before we touch the frontier
    ledger.save()

    generated: list[str] = []
    judged: list[str] = []

    frontier = load(project_dir).runnable_frontier()
    for node_id in frontier:
        enqueue_generation(node_id, project_dir)  # → landed (shot) / judging (asset)
        generated.append(node_id)
        judge_one(node_id, project_dir)           # → approved/locked | needs_regen(+re-roll) | drift | paused
        judged.append(node_id)

    # drain any re-rolled `landed` shots + `judging` assets to a terminal state.
    _drain_landed(project_dir, judged)

    return {"frontier": frontier, "generated": generated, "judged": judged}
