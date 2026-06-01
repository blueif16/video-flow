# 爽剧 autonomous pipeline — V1 primitive-layers plan
_generated 2026-05-31 • the unified build spec • synthesizes 4 parallel architect passes over 14 audited repos • supersedes the design discussion in `manju-product-layered-design-2026-05-31.md` (which holds the repo evidence)_

## The design in one screen
```
  BRAIN (swappable, 爽剧 = V1's only one)  ── emits Plan columns ─┐
     owns: story + style + bible                                 │
                                                                 ▼
  LEDGER (ledger.json) — the ONE data contract, live & resumable, node-graph renderable
     brain writes plan.*  ·  overlord writes run.*  (no field overlap)
                                                                 │ tooling reads plan.*
                                                                 ▼
  TOOLING (universal, genre-blind, single-purpose gerund skills)
     referencing · composing-scenes · building-prompts · generating · composing
                                                                 │ each artifact lands →
                                                                 ▼
  OVERLORD (thin event-driven CODE control plane + STATELESS vision judge + ledger-as-memory)
     trigger(hook|poller) → sequential lazy re-roll → judge ONE artifact → verdict → act
                                                                 │
                                                                 ▼
  OBJECTIVE: overall quality, embodied by the judge vs a fixed rubric + the bible.
```
Rules that make it work: **style is a separate axis from story** · **the judge is perception (vision inference), never code** · **the control plane is code (can't fake quality — it doesn't judge)** · **抽卡 = sequential lazy re-roll (gen one → judge → one more), never batch-K** · **every node idempotent** · **memory lives in the ledger as data, never a context window** · **human touches only: one-time rubric calibration + escalations.**

---

## Layer 0 — THE LEDGER (`ledger.json`, the kernel)
One JSON document per project. A tree of typed **nodes**; every executable unit (each shot, each bible asset) carries a `plan` block (BRAIN-owned) and a `run` block (OVERLORD-owned). No field overlaps → no write conflict, enforced by a writer-tag, not locks.

**Tree:** `project → styles[] → bible{characters[],scenes[],props[],villains[]} → episodes[] → scenes[] → shots[]`

**ASSET node** (bible entry — its ref images are generated+judged like shots):
- plan (BRAIN): `id, kind, descriptor, ai_draw_keywords[], 固定特征词[], 禁止变化项[], style_id`
- run (OVERLORD): `ref_image_paths[], ref_status(none|drafting|judging|locked|rejected), seed, attempts[], current_artifact, final_verdict`

**SHOT node** (atomic unit):
- `id` (stable path id `ep03.sc02.sh05`, immutable, never reorder) · `deps[]` (asset ids + prev shot → graph edges)
- **plan (BRAIN):** `intent, dialogue, camera{shot_size,movement,lens_mm}, action, ref_ids[], style_id, duration_s, showtell_pass`
- **run (OVERLORD):** `status, attempts[], current_attempt_id, current_artifact, final_verdict, cost_usd`
- `attempts[]` (append-only 抽卡 history): `{attempt_id, ts, seed, model, prompt, artifact_path, thumb_path, verdict, lesson_ref}`

**Status state-machine (canonical):**
`pending → generating → landed → judging → (approved | needs_regen | paused | blocked_on_ref | skipped)`
- `needs_regen → generating` (re-roll: new seed, deps unchanged) — the lazy sequential re-entry
- `blocked_on_ref → pending` (after the drifted ref is re-locked)
- `* → paused → pending` (budget/human/error fence + resume)
- `approved` terminal **unless** BRAIN edits `plan` → invalidates `approved → pending` and cascades to dependents
- asset `ref_status`: `locked` gates dependent shots (a shot with an unlocked `ref_id` stays `pending`)

**Idempotency / resume / isolation:**
- a node's output is a pure function of `(plan, deps' current_artifact, seed, model)`; re-run with identical inputs = no-op (skip-if-`approved`); `seed` is the only re-roll knob; artifacts content-addressed by `attempt_id`, never overwritten.
- **resume = scan for `pending` nodes whose deps are all `approved|locked`** = the runnable frontier; interrupted `generating|judging` reset to `pending`.
- a `failed`/`paused` node blocks only its transitive dependents; all independent frontier nodes proceed in parallel. Failure is local data, never a halting exception.

**Node-graph front-end (free, read-only over the ledger):** each asset+shot id → a node; thumbnail = `run.current_artifact.thumb_path`; color = `status`; attempt-count badge = `attempts.length` (visualizes 抽卡 cost); edges = `deps[]`; click → `plan` + `attempts[]` filmstrip with per-take seed/model/verdict.

**Lesson memory (in-ledger, retrievable):** `ledger.lessons[] = {lesson_id, scope:{category,model,style_id?,asset_kind?}, symptom, fix, prompt_delta, hit_count}` — indexed by `(category, model)` for O(1) retrieval; the generator queries it before composing the next attempt. *Not* an ever-growing markdown re-read whole (the explicit fix to ai-video-skill).

---

## Layer 1 — THE BRAIN (爽剧, swappable)
`IN = (seed_idea, knobs{题材,集数N,时长,主爽点类型,style_id})` → `OUT = the plan columns of the ledger` (full episode→scene→shot Plan, top-down). The brain never calls a model.

**Dramaturgy modules it MUST encode** (ported from `0xsline/short-drama`, MIT — ignore its 出海/合规/paywall):
1. **爽点 matrix** — 压抑→释放, 5 archetypes (身份碾压/打脸复仇/逆袭翻盘/情感爆发/悬念揭秘), intensity escalating; every 爽点 must cite ≥1 prior 压抑 setup or fail self-check. (`satisfaction-matrix.md`)
2. **Rhythm curve** — per-ep micro-3-act `{hook_30s, escalation_90s, payload_30s}` + whole-series waveform 起势/攀升/风暴/决战 with per-stage density/强度/加速:减速. (`rhythm-curve.md`)
3. **Hook design** — every ep except finale gets an end-cliffhanger. (`hook-design.md`)
4. **Villain** — 4-tier escalating (小/中/大/隐藏); 隐藏反派 requires `foreshadows[] ≥3 {episode,line_ref}` or is rejected. (`villain-design.md`)
5. **Cold-open** — ep1 uses one of 6 opening templates; 前30秒立冲突, no 旁白 dump. (`opening-rules.md`)

**SHOW-DON'T-TELL hard gate** (blocking before Plan commit): every `dialogue`/`action` must be camera-filmable — no interiority except explicit `画外音(V.O.)`. "she felt betrayed" → "她的酒杯在微微颤抖". Writes `showtell_pass`.

**Style as a separate axis:** `style_id` (default `国漫暗黑`) resolves to a preset (palette/film-vocab/negative-floor) consumed only by tooling. Swapping style = zero story edits.

**Swap contract:** any future brain (悬疑/治愈/…) emits the **identical Plan column set**; genre dramaturgy lives *inside* the brain; tooling never knows which brain wrote the Plan and never changes.

---

## Layer 2 — THE TOOLING (5 universal single-purpose skills)
Each: gerund name · IN (ledger reads) · OUT (ledger writes/artifacts) · the one consensus best-practice · source.

1. **`referencing`** · IN: `bible.*` (固定特征词/禁止变化项), `style_id` · OUT: `ref_sheet/{char|scene}/NN/*.png` (numbered dual-anchor folders = source-of-truth), `bible.*.ref_tag` (`@char_lin`), `locked_seed`; exposes 禁止变化项+ref_tag as **Overlord drift-check inputs**. · **dual-anchor (角色+场景) + locked seeds + 固定特征词 injected into every downstream prompt** — kills drift, the #1 failure. · micro-drama `(@tag)` + hestudy dual-anchor.
2. **`composing-scenes`** · IN: `shots[]` (景别/运镜/refs) · OUT: `storyboard/.../shot_NN.spec.json` (per-shot keyframe and/or 9-grid composite; **background/character separated** layers). · papaya/micro-drama 9宫格.
3. **`building-prompts`** · IN: shot intent+dialogue+emotion+ref_tags+style · OUT: `prompts/.../shot_NN.txt` (**5-part Subject·Action·Camera·Style·Constraints + time-coded `[00:00-00:0X]` blocks + negative-prompt floor** as positive constraints; per-model adapter). · ai-video-skill `prompt-logic.md` + micro-drama negative floor.
4. **`generating`** (the runner) · IN: canonical `{prompt, reference_images[≤9], reference_videos, reference_audios, duration, resolution, aspect_ratio, generate_audio, seed}` · OUT: `output_files[]` + status, via **presence-router → lossy per-model adapter → CLI envelope** (`{model,output_files,data}` stdout / logs stderr); provider-agnostic (fal/replicate/vendor); **ComfyUI only as an optional backend behind the runner**; validate-before-spend + skip-if-exists. · ai-video-skill `generate.py` + producer-plugin `runners/`.
5. **`composing`** (timing/voice/render — HANDOFF ONLY, do not rebuild) · IN: `output_files[]`+dialogue+duration · OUT: routes to the user's **existing** skills: `cue-plan-author → tts-voice-direction → asr-cue-aligner → hyperframes/remotion composer → machine render-gate` (ffprobe=truth, −0.01s overlap guard, 3.2–5.5 chars/sec; Chinese ASR → Volcano first; never `format=srt`).

---

## Layer 3 — THE OVERLORD (control plane + stateless judge)
**Trigger (zero idle inference):**
- **PostToolUse hook** for synchronous generators (returns a file) → mark `landed` → `judge_one`.
- **Async poller** for fire-and-forget jobs (fal/Replicate/Veo return a `request_id`): hook writes `{request_id, provider, status=submitted}` and exits; an idempotent `poller.py` (driven by `/loop 30s`) polls, downloads on `done`, flips to `landed`, calls the same `judge_one`. Idle cost = cheap HTTP GETs, self-terminates when no `submitted` rows.

**Sequential lazy re-roll loop** (one entrypoint, idempotent; many nodes in-flight in parallel):
```
def judge_one(node_id):
    row = ledger.lock(node_id);  if row.status != landed: return   # idempotent no-op
    v = JUDGE(build_context_sheet(row))        # ONE stateless inference
    ledger.append_verdict(node_id, v)
    if v.drift:        ledger.set(row.ref_node, status=needs_regen); ledger.set(node_id, blocked_on_ref)
    elif v.pass:       ledger.set(node_id, approved, final_artifact=row.artifact); wake_dependents(node_id)
    else:
        ledger.append_lesson(row.style, row.shot_type, v.failure_mode, v.fix_hint)
        if row.attempt >= N_MAX(=4): ledger.set(node_id, paused_for_human, flag=v)   # human touch #2
        else: ledger.set(node_id, needs_regen, attempt+1, inject_lessons=lessons_for(row)); enqueue_generation(node_id)
    ledger.unlock(node_id)
```

**Stateless judge** `JUDGE(sheet) -> verdict` — one inference per artifact, no cross-call memory; everything assembled into the sheet from the ledger (replayable, cannot be faked by the control plane which only assembles inputs + records outputs).
- common sheet: `intent + actual prompt, rubric (verbatim), prior_lessons (top-k by (style,shot_type,last_failure)), ref_role_map ("[Image1]=face")`.
- **image:** generated image + the bible reference image(s) for this char/scene → multi-image drift comparison.
- **video:** keyframe contact-sheet (9 frames at slice-centers `t=dur·(k+0.5)/n`, 3×3) + first+last frame + `probe.json`; **OR native video understanding (Gemini)** when available (contact-sheet is the universal floor).

**Verdict + action policy:**
```
verdict = {node_id, modality, attempt, score, pass:bool,
  failure_mode ∈ {drift|anatomy|off-prompt|artifact|motion-incoherent|continuity|text-garbled|pass},
  fix_hint, drift:bool, evidence}
```
| verdict | ledger mutation | next action |
|---|---|---|
| `pass` | `approved`, write `final_artifact` | wake dependents |
| `fail`, attempt < N_MAX | `needs_regen`, attempt++, append lesson, set `inject_lessons` | re-roll **one** candidate |
| `fail`, attempt ≥ N_MAX | `paused_for_human` + verdict+sheet | escalate (human) |
| `drift=true` | `ref_node → needs_regen`; node → `blocked_on_ref` | regen the **reference**, re-judge dependents |
| malformed artifact | `error` | poller re-submits (idempotent) |

**Rubric + calibration:** `rubrics/<style>/<shot_type>.json` (axes mined from OpenMontage `slideshow_risk`/`delivery_promise`/`final_review` + ai-video `review.py`; pass threshold; per-style negative-floor + 禁止变化项). **One-time human calibration**: a human scores ~10 seed artifacts per (style, shot_type) → sets threshold + seeds lessons. Then autonomous.

**Judge model:** **Gemini-3-pro-vision** default (best at many-image-in-one-prompt drift comparison + native video); Claude-vision as the swappable substitute (config one-liner).

**Claude Code feasibility:** PostToolUse hook in `.claude/settings.json` (matcher on the gen tool → `on_artifact_landed.py`) for sync; `poller.py` via `/loop 30s` for async. Both real today.

---

## The consensus floor vs the moat
**The 12 V1-required primitives (replication = battle-test weight; ship these, nothing more):**
1. `ledger.json` scene/shot graph + scaffolding (status enum per node) — the bus.
2. 爽剧 brain → typed storyboard/shot-list (the Plan).
3. style preset + art-direction lock (separate axis).
4. character/scene/prop **reference sheets + reference-tagging** (consistency anchor — half of "70").
5. keyframe still → **image-to-video** (ref-driven, never t2v).
6. per-shot **model routing** via one canonical schema (lossy adapters behind the runner contract).
7. **negative-prompt/quality floor** in every shot prompt.
8. **validate-before-spend** (schema+exclusivity, blocks paid gen).
9. **sequential lazy re-roll + idempotent skip-if-exists** (the 抽卡 loop in code).
10. **QC gate: stateless vision judge per artifact → lesson**.
11. **ASR word-level timing → self-assembled cues** (Chinese→Volcano; never `format=srt`).
12. **ffprobe-truth compose + captions + one-voice TTS + assemble** (= the user's existing hyperframes/remotion/asr stack — wire, don't rebuild).
*Items 1–6 + 12 = the replicated backbone (≈70). 7–11 are the cheap high-replication mechanisms that make the re-roll loop actually converge.*

**The 5 differentiators (our moat — each appears as a half, in ≤2 repos, never fused for 漫剧):**
1. machine-readable episode→scene→shot graph as the bus → free node-graph viz + resume.
2. consistency as a **blocking code gate** (drift-vs-bible before spend), not a prompt tip.
3. closed-loop QC: stateless vision judge + **retrievable lesson store keyed by (category, model)**.
4. canonical schema routed **lossily at series altitude** (not single-clip).
5. **runner contract** (stdout `{output_files,data}` envelope) as the clean provider boundary that pairs with the code control plane.

---

## Build order (the only sequence that respects the dependencies)
- **Phase 0 — Kernel:** `ledger.json` schema + writer-tag ownership + the read-only node-graph view. *(everything writes here)*
- **Phase 1 — Brain→Plan:** 爽剧 brain (port 0xsline dramaturgy + show-don't-tell gate; style axis) emitting the Plan columns.
- **Phase 2 — Reference layer:** `referencing` (dual-anchor ref sheets + locked seeds + ref_tags + drift inputs). *Build before generation — it's the moat.*
- **Phase 3 — Generation path:** `building-prompts` → `generating` (canonical schema + router + validate-before-spend + negative floor).
- **Phase 4 — Overlord:** trigger (hook→sync first, poller→async next) + sequential lazy re-roll + stateless judge (image first, then video) + verdict/action + rubric calibration + lessons.
- **Phase 5 — Compose:** handoff to the existing skill stack + machine render-gate.

Differentiators 1/2/3 fall out of Phases 0/2/4 respectively. Quality is "directional" until the lesson store warms up; hero quality needs the calibration pass + a few episodes of accumulated lessons.

## Parking lot (decide later, not V1)
- 2nd brain (悬疑/治愈) — proves the swap contract.
- self-host ComfyUI backend behind the runner (only if cost-at-scale).
- episode-level coherence pass (wider-scope stateless judge over the whole-episode contact sheet).
- best-of-K upgrade (only if sequential re-roll proves too slow).
