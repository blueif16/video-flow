# Autonomous AI 漫剧 product — layered design (build-our-own, mined from 14 repos)
_generated 2026-05-31 • decision: NOT forking; crafting a Claude-Code-native pipeline, stealing only battle-tested patterns • companion to `manju-architecture-comfyui-vs-code-2026-05-31.md`_

## Battle-test scoreboard (weight steals by this)
| Repo | Verdict | ★ | License | Weight | Why |
|---|---|---|---|---|---|
| **0xsline/short-drama** | **REAL** | 570 | MIT | **HIGH** | Dramaturgy is genuine, dense craft. Steal the script brain. |
| **calesthio/OpenMontage** (real upstream) | **REAL** | 4,182 | AGPL-3.0 ⚠️ | **HIGH (patterns only)** | The autonomous architecture + honesty gates. AGPL = copy ideas, not code. |
| **zhaihao118/Micro-Drama-Skills** | **REAL** (committed artifacts, real Seedance submits) | 182 | none ⚠️ | **HIGH (patterns only)** | The 漫剧 domain anchor: consistency chain + state schema. No license = don't copy code. |
| **jianshuo/claude-skills** | **REAL** (daily-driver, auto-mirrored) | 67 | MIT | **MED-HIGH** | The compose/orchestration *convention*. |
| **claude-remotion-kickstart** | REAL (most-adopted starter) | 101 | MIT | MED | Deterministic Remotion compose + transcript→cue logic. |
| **0xadvait/ai-video-skill** | DEMO/borderline-vapor | 3 | MIT | MED (ideas) | One-schema router + validate-before-spend + QC-loop *pattern*. |
| **fableforge** | REAL-but-light | 3 | MIT | MED (ideas) | Machine render-gate (via HyperFrames, not its own code). |
| **koda-stack** | REAL-but-thin (465 lines md) | 107 | MIT | LOW | `CLAUDE.md`-as-brand-fingerprint idea. |
| **daniel/Producer-Plugin** | DEMO-ONLY (1★,1 commit) | 1 | MIT | LOW (ideas) | Clean runner contract + budget-estimator. |
| **Shanyin screenwriting** | REAL | 389 | MIT | LOW | Film-craft 红线, but too arthouse for 漫剧 virality. |
| **claude-code-video-toolkit** | off-target ✅ (your read confirmed) | 1308 | MIT | LOW | Screen-rec/explainer architecture, not AI-gen. Steal only `project.json` lifecycle. |
| **aividpipeline-skills** | VAPOR (404 repo + paywall) | — | — | SKIP | Marketing site, no source. |

## Replication map → the floor (what EVERY real repo does = your ~70 baseline)
1. **Pipeline backbone:** `script → typed storyboard/shot-list → keyframe image → image-to-video → assemble → (publish)`. One skill per stage; a thin orchestrator that names sub-skills. *(OpenMontage, koda, jianshuo, Micro-Drama, aivp all converge.)*
2. **Storyboard is the load-bearing joint:** a typed, per-shot table (景别/运镜/配音/时长) is the prompt source for gen. Make it a first-class artifact, not prose.
3. **Asset-first consistency:** character/scene/prop **bible → reference sheet → reference-tag in every shot prompt**. *(Micro-Drama `(@ref.png)`, hestudy `@anchor`, every YouTube creator in the earlier brief.)*
4. **State = inspectable files:** a project tree with `status` enums per shot. *(Micro-Drama `video_index.json`, toolkit `project.json`.)* This is what your node-graph front-end renders.
5. **ffprobe duration = source of truth; never estimate timing; word-level ASR → assemble cues yourself; one voice + low BGM bed.** *(jianshuo, fableforge, remotion-kickstart all converge.)*

Hit all five competently and you have a ~70/100 episode. The layers below mark, per stage, the **Floor** (replicated baseline → 70) vs the **Lift** (the unique bet that pushes above average, with the repo to mine).

## The layered design

### L0 — Orchestration substrate (how it runs)
- **Floor:** agent-is-orchestrator (Claude is the brain), one skill per stage, thin orchestrator. *(consensus)*
- **Lift:** declarative **pipeline manifest (YAML DAG)** + per-stage **director skill** + a real machine-readable **`project.json`** (episode→scene→shot graph w/ status) as the bus + **checkpoint-resume**. Mine **OpenMontage** for the pattern (NOT the AGPL code). → your front-end is a read-only viz over `project.json`.

### L1 — Story / 漫剧 script brain
- **Floor:** micro-3-act per episode + mandatory end-hook; script → typed shot-list. *(0xsline, hestudy, koda)*
- **Lift:** steal **0xsline/short-drama** wholesale (MIT): `satisfaction-matrix` (5 爽点 archetypes, 压抑→释放), `rhythm-curve` (per-ep + whole-series 起势/攀升/风暴/决战 waveform), `hook-design`, `villain-design` (4-tier escalating, 隐藏反派 needs ≥3 foreshadows), `opening-rules`. Add **show-don't-tell hard gate** (every line camera-filmable) from Shanyin's 红线. **IGNORE** 0xsline's 出海/合规/paywall plumbing.

### L2 — Asset / consistency (the moat)
- **Floor:** bible → reference sheet → tag into every prompt. *(Micro-Drama, hestudy)*
- **Lift:** Micro-Drama's **bible→ref-sheet→`(@tag)`** + hestudy's **DUAL-ANCHOR** (numbered 角色/场景 folders as source-of-truth + `固定特征词`/`禁止变化项` + locked seeds) + a **blocking completeness→consistency review gate** (hestudy's 5-axis diff: 场景/角色/动作/时间/情绪) *before* any expensive render. This is half of "get to 70" — it kills character drift, the #1 failure.

### L3 — Generation (model calls)
- **Floor:** per-shot routing across closed APIs (Seedance 2 / Kling 3 / Nano-Banana / Veo); reference-to-video not text-to-video; provider abstraction.
- **Lift:** **0xadvait**'s canonical-schema + presence-router + lossy-per-model-adapter — but lift altitude: canonical object = the episode/scene/shot tree, not a single clip. **daniel**'s **runner contract** (stdout `{output_files,data}` JSON envelope / stderr logs) as the provider interface; ComfyUI only as an optional tool behind it (daniel's honest import/export).
- **Floor mechanisms (→70):** validate-before-spend w/ citation-coherence (0xadvait `validate.py`), the hard-coded **negative-prompt floor** + `visual_styles.json` presets (Micro-Drama), idempotent retry/skip-if-exists.

### L4 — Compose / timing / voice (assembly)
- **Floor:** ffprobe = truth; word-level ASR → self-assembled cues; one voice + low BGM. *(consensus)*
- **YOU ALREADY OWN THIS.** Your skill stack — `hyperframes`, `remotion`, `cue-plan-author`, `asr-cue-aligner`, narration kit, `complete-video-pipeline` — is exactly this layer. Add fableforge/HyperFrames' **machine render-gate** (headless `inspect`, −0.01s overlap guard, 3.2–5.5 chars/sec rate gate) and route **Chinese ASR to 豆包/Volcano first** (per `yt-rag-youtube-429-subtitle-fix` memory). jianshuo's anti-`response_format=srt` rule.

### L5 — QC / self-improvement (above-average, over time)
- **Reality:** most repos STOP here at "average" — daniel/toolkit/koda are human-gated, no automated QC. This is the gap.
- **Our differentiator:** OpenMontage's **mechanistic gates** (`slideshow_risk`, `delivery_promise`, `final_review` = ffprobe + frame-sampling) + 0xadvait's **contact-sheet → Claude-as-judge → lesson** — but **close the loop in code**: a structured, retrievable lesson store keyed by (category, model), not an ever-growing markdown re-read whole. Add the dimension **nobody has: cross-panel character/style-consistency scoring.** This is the engine that moves usable-take rate 30%→90% (the real KPI from the first brief).

## The 4 differentiators nobody has built (our actual moat)
1. **Machine-readable `project.json` scene/shot graph** with status enums → free node-graph front-end + resumability. (Everyone uses markdown-glob or gitignored state.)
2. **Consistency as a *blocking gate*, not a prompt tip** — automated 5-axis drift diff vs the character/scene bible before spend. (hestudy gestures at it; nobody automates it cross-panel.)
3. **Closed-loop QC in code** — contact-sheet vision-judge + delivery-promise/slideshow gates + a *retrievable* lesson store that feeds the next prompt. (0xadvait + OpenMontage have halves; nobody fused them for 漫剧.)
4. **One canonical episode/scene/shot schema** routed lossily to many models — at series altitude, not single-clip. (0xadvait has the shape at the wrong altitude.)

## Steal-verbatim (MIT, safe) vs pattern-only (license-blocked)
- **Adapt directly (MIT):** 0xsline dramaturgy reference files; jianshuo gerund-skill + IN→OUT orchestrator convention; remotion-kickstart `segmentTranscript` cue logic; 0xadvait prompt-craft corpus (5-part, time-coded, 15 failure modes) + validate.py shape; koda `CLAUDE.md` brand-fingerprint.
- **Patterns only, DO NOT copy code:** OpenMontage (AGPL — manifest+director+gates *design*); Micro-Drama (no license — consistency chain + state schema *design*).

## Next step
Define `project.json` schema + the stage list (the L0 spine), then port L1 dramaturgy + L2 consistency gate. L4 is largely your existing skills. Build L5 last — it's the moat but needs L0–L4 producing artifacts first.
