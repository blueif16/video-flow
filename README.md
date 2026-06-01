# 漫剧 autonomous pipeline (manju) — V1

An autonomous Chinese animated-short-drama (漫剧) generation pipeline. A swappable **爽剧 brain**
writes a Plan into one resumable **ledger**; genre-blind **tooling** turns it into reference sheets,
storyboards, prompts, and generated shots; a code **overlord** + stateless **vision judge** run a
sequential 抽卡 re-roll loop until every artifact passes a rubric; **compose** assembles the final video.

**Status: runs end-to-end today on a deterministic mock provider. The only thing left is plugging in
real image/video/judge API keys.** Every layer is built, wired, and self-tested (7 suites green).

```
BRAIN (爽剧, swappable) ─Plan→ LEDGER (ledger.json, the one contract) ─reads→
  TOOLING  referencing · composing_scenes · building_prompts · generating · composing
      └ every artifact lands → OVERLORD (code control plane + stateless vision judge)
                                 → verdict → re-roll / approve → OBJECTIVE: quality
```
Locked rules: style ⊥ story · judge is perception not code · control plane can't fake quality ·
抽卡 = sequential lazy re-roll · nodes idempotent · memory lives in the ledger, not a context window.

## Run it

```bash
# author a Plan with the brain, then run the whole pipeline to a final.mp4 (mock assets)
python -m manju.run_pipeline --from-brain "被逐少年归来复仇" \
    --集数N 1 --主爽点类型 "身份碾压" --style-id "国漫暗黑" \
    --project-dir projects/myshow

# or run an already-authored project (resumable: re-run picks up where it left off)
python -m manju.run_pipeline --project-dir projects/myshow
```
Output: `projects/myshow/` → `ref_sheet/`, `storyboard/`, `prompts/`, `artifacts/`, `render/final.mp4`.

## See the run

```bash
python -m http.server 8000          # from the repo root
# open http://localhost:8000/manju/ledger/view/viewer.html
```
Read-only node graph over the ledger: one box per asset/shot, colored by status, thumbnail from
`current_artifact`, attempt-count badge (visualizes 抽卡 cost), edges = deps, click → plan + take
filmstrip. A populated demo project lives at `projects/demo_run/`.

## Plug in real keys (the only remaining work)

| What | Where | How |
|---|---|---|
| **Image / video gen** | `manju/skills/generating/adapters/{fal,replicate}.py` | implement `generate(req, project_dir)` (mock.py is the reference); `export FAL_API_KEY` / `REPLICATE_API_KEY`; set `"model":"fal"` in the request |
| **Vision judge** | `manju/overlord/judge.py` (`_judge_gemini` / `_judge_claude`) | `export MANJU_JUDGE_BACKEND=gemini` + `GEMINI_API_KEY` (or `claude` + `ANTHROPIC_API_KEY`) |

Nothing upstream changes — the canonical runner request, the judge context-sheet, and the ledger
contract are provider-agnostic. The mock provider content-addresses every request and copies a sample
asset (`assets/sample/{ref_face.png,shot.mp4,voice.wav}`), so a real adapter is a one-file drop-in.

## Layout

```
CONTRACTS.md                     # THE seam contract — read this when confused about any boundary
manju/ledger/                    # Phase 0 — schema + ledger.py (writer-tag enforced) + viewer.html
manju/brain/                     # Phase 1 — 爽剧 brain: dramaturgy + show-don't-tell gate + style axis
manju/skills/referencing/        # Phase 2 — dual-anchor ref sheets + locked seeds + drift inputs (moat)
manju/skills/composing_scenes/   # Phase 2 — storyboard spec + 9宫格 keyframe still (i2v seed)
manju/skills/building_prompts/   # Phase 3 — 5-part time-coded prompt + negative floor
manju/skills/generating/         # Phase 3 — the canonical runner (the reused gen primitive)
manju/overlord/                  # Phase 4 — control plane + judge + re-roll loop + hook + poller + rubrics
manju/skills/composing/          # Phase 5 — ffprobe-truth assemble + handoff to TTS/ASR/hyperframes stack
manju/run_pipeline.py            # the one entrypoint
projects/demo/ledger.json        # the golden fixture (kept pristine)
```

## Test

```bash
python tests/test_kernel.py        python tests/test_e2e.py        python tests/test_brain.py
python -m manju.overlord._selftest
python -m manju.skills.referencing._selftest
python -m manju.skills.composing.selftest
python -m manju.skills.composing_scenes._selftest
```

Requires Python 3.12 + ffmpeg. Standard library only — no pip dependencies.
Full design rationale: `research/manju-v1-primitive-layers-plan-2026-05-31.md`.
