# composing (Phase 5) — WIRE, DON'T REBUILD

Assemble approved shot clips into `projects/<n>/render/final.mp4` and emit the
handoff artifacts the richer skill stack consumes. See `/CONTRACTS.md` §5.

## Entry
`from manju.skills.composing.composer import compose, handoff_plan`

- `compose(ledger, project_dir) -> {"final","cues","manifest","probe"}`
- `handoff_plan(ledger, project_dir) -> {"sequence","steps"}`  (documents, never executes, the existing-skill seam)

## What it writes (under `projects/<n>/render/`)
- `final.mp4` — concat of approved clips (shot-order) + burned Chinese captions + narration stand-in.
- `script-cues.json` — canonical CuePlan: one row per spoken shot, frames computed from **probed** durations at `fps=25`, with 3.2–5.5 chars/sec pacing guard (warns) and a −0.01s overlap guard.
- `render-manifest.json` — inputs→output, ffprobe-truth render-gate result, the documented handoff sequence.
- `captions/*.png` — per-cue caption rasters (transient inputs).

## Rules honored
- **ffprobe = truth** — cuts/cues use probed durations, never planned `duration_s`.
- **never `format=srt`** — captions are real burned-in overlays (macOS AppKit JXA → transparent PNG → ffmpeg `overlay` + `enable='between(t,..)'`). The local ffmpeg has no drawtext/libass.
- **fail loudly** — `compose()` raises if the render-gate fails.

## Self-test
`python -m manju.skills.composing.selftest`  (uses `projects/_scratch_compose`, gitignored; never touches `projects/demo`).

## Handoff (the human orchestrator runs these later, against the emitted artifacts)
`cue-plan-author → tts-voice-direction → asr-cue-aligner → hyperframes/remotion composer → machine render-gate`
(Chinese ASR → Volcano first.) These are Claude Code skills, not importable Python — this layer documents the seam, it does not invoke them.
