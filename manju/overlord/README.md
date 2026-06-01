# overlord (Phase 4) — THE OVERLORD

Thin event-driven CODE control plane + STATELESS vision judge + ledger-as-memory.
The control plane is code (it cannot fake quality — it does not judge); the judge
is perception (one stateless inference per artifact). V1 ships a deterministic MOCK
judge; a real vision model is a one-config swap.

## Modules
- `judge.py` — the stateless judge.
  - `build_context_sheet(ledger, node_id, project_dir) -> dict` assembles the judge
    input FROM THE LEDGER ONLY (replayable): intent + actual prompt, the rubric
    verbatim, `prior_lessons`, `ref_role_map` + bible ref image paths, the artifact.
    Video → a 3×3 keyframe contact-sheet (9 frames at slice-centers `t = dur·(k+0.5)/n`)
    + first/last frame + `probe.json` via ffmpeg.
  - `JUDGE(sheet) -> verdict` — `JUDGE_BACKEND` indirection (`mock` | `gemini` | `claude`),
    env `MANJU_JUDGE_BACKEND` (default `mock`). gemini/claude are STUBS that raise
    until a key is set. The mock is deterministic (hash of node_id/attempt/prompt).
- `control.py` — the sequential lazy re-roll loop.
  - `enqueue_generation(node_id, project_dir, seed=None)` → request (reuses
    `building_prompts.request_for_shot` if importable, else a minimal request) →
    `run_request` (the generating seam) → `append_attempt` → `landed`.
  - `judge_one(node_id, project_dir)` — idempotent; the verdict+action policy
    (pass / drift / fail<N_MAX / fail≥N_MAX). N_MAX=4.
  - `tick(project_dir)` — resumable driver over `runnable_frontier()`.
- `on_artifact_landed.py` — PostToolUse hook (sync). Reads the hook JSON on stdin
  OR `--node-id`/`--project-dir`. Self-filters to generation events. Exit 0 always.
- `poller.py` — idempotent async poller (fire-and-forget). Drains a sidecar job
  queue `<project_dir>/_async_jobs.json`; self-terminates when no submitted rows.
  Drive with `/loop 30s`.
- `rubrics/<style>/<shot_type>.json` — `国漫暗黑/{default,close_up,wide}.json`.

## Self-test
`python -m manju.overlord._selftest` — copies `projects/demo` → `projects/_scratch_ovl`
and proves the pass / drift / re-roll+lesson / escalation / contact-sheet /
idempotency / hook / poller / tick paths. Does NOT touch `projects/demo`.

See `/CONTRACTS.md` §4 + §1.3–1.5 for the verdict/status/lesson contract.
