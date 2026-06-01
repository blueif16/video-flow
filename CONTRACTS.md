# CONTRACTS.md — the single source of truth for every seam

This file is THE contract. Phases 1–5 are built in parallel against it. **If a dev is confused about a field name, a writer, a status, an artifact path, or a CLI envelope — the answer is HERE, not in a Slack thread.** The JSON Schema (`manju/ledger/schema/ledger.schema.json`) is the spec-of-record for document shape; this file is the spec-of-record for *behavior and seams*.

Phase 0 (the ledger kernel) is built and self-tested. Phases 1–5 import `manju.ledger`.

---

## 0. Repo map

```
manju/ledger/ledger.py            # the shared library — THE API everyone imports
manju/ledger/schema/ledger.schema.json   # Draft 2020-12 schema (spec-of-record)
manju/ledger/view/viewer.html     # read-only node-graph (open over http; loads projects/demo/ledger.json)
manju/brain/                      # Phase 1  (stub)
manju/skills/referencing/         # Phase 2  (stub)
manju/skills/composing_scenes/    # Phase 2  (stub)
manju/skills/building_prompts/    # Phase 3  (stub)
manju/skills/generating/          # Phase 3  — the runner (stub)
manju/skills/composing/           # Phase 5  (stub)
manju/overlord/                   # Phase 4  (stub) + overlord/rubrics/
projects/demo/ledger.json         # the fixture every downstream dev runs against
assets/sample/                    # ref_face.png, shot.mp4, voice.wav (mock-provider outputs)
tests/test_kernel.py              # kernel self-test (python tests/test_kernel.py)
```

---

## 1. The ledger — node schema, ownership, status machine, API

### 1.1 Document tree
```
project
styles[]                                  # style is a separate axis from story
bible { characters[], scenes[], props[], villains[] }   # ASSET nodes
episodes[] → scenes[] → shots[]           # SHOT nodes
lessons[]                                 # in-ledger retrievable lesson store
```
Node ids are **stable path ids**, immutable, never reordered:
- assets: `char_lin`, `scene_throne`, …
- shots: `ep01.sc01.sh01` (`ep{NN}.sc{NN}.sh{NN}`)

### 1.2 plan vs run fields — the writer-tag ownership rule

> **The core invariant (no locks, just enforcement):** `plan.*` is BRAIN-owned, `run.*` is OVERLORD/generating-owned, **fields never overlap**. Writing a field you don't own raises `WriterError`. That is what guarantees "no field overlap → no write conflict."

| node | block | writer(s) | fields |
|---|---|---|---|
| **ASSET** | `plan` | `brain` | `descriptor`, `ai_draw_keywords[]`, `固定特征词[]`, `禁止变化项[]`, `style_id` |
| **ASSET** | `run` | `overlord`, `generating` | `ref_image_paths[]`, `ref_status`, `ref_tag`, `seed`, `locked_seed`, `attempts[]`, `current_attempt_id`, `current_artifact`, `final_verdict` |
| **SHOT** | `plan` | `brain` | `intent`, `dialogue`, `camera{shot_size,movement,lens_mm}`, `action`, `ref_ids[]`, `style_id`, `duration_s`, `showtell_pass` |
| **SHOT** | `run` | `overlord`, `generating` | `status`, `attempts[]`, `current_attempt_id`, `current_artifact`, `final_verdict`, `cost_usd` |

`deps[]` lives on the SHOT node itself (not in plan/run): asset ids + prev-shot id → graph edges. It is set at authoring time (BRAIN) and is structural.

**`status` / `ref_status` are NOT written via `write_run`** — use `set_status()` so the state-machine is validated. `write_run(..., status=...)` raises.

### 1.3 Status state-machine (canonical)

```
        ┌──────────────────────── plan edit (write_plan) ──────────────────────┐
        ▼                                                                       │
   ┌─ pending ─→ generating ─→ landed ─→ judging ─┬─→ approved ─────────────────┘ (terminal*)
   │     ▲           │                            ├─→ needs_regen ─→ generating
   │     │           └────────→ pending (reset)   ├─→ blocked_on_ref ─→ pending
   │     │                                        ├─→ paused ─→ pending
   │     └──────── paused ─→ pending              └─→ skipped (terminal)
   └──────────────────────────────────────────────────────────────────────────
```
- `needs_regen → generating` — lazy sequential re-roll (new seed, deps unchanged).
- `blocked_on_ref → pending` — after the drifted ref re-locks.
- `* → paused → pending` — budget/human/error fence + resume. (`paused` reachable from pending/generating/landed/judging/needs_regen/blocked_on_ref.)
- `approved` is terminal **except** a BRAIN `plan` edit demotes it `approved → pending` and **cascades to dependents** (handled automatically by `write_plan`).
- Asset refs use `ref_status` analogously: `none → drafting → judging → (locked|rejected)`, `rejected → drafting`, `locked → none` only via plan edit. **`locked` gates dependent shots** — a shot whose `ref_id` is not `locked` stays out of the frontier.

Crash recovery: `reset_interrupted()` flips `generating|judging` shots → `pending` and `drafting|judging` asset refs → `none`.

### 1.4 The `ledger.py` public API (verbatim — call these by name)

```python
load(project_dir: str) -> Ledger
artifact_path(project_dir, node_id, attempt_id, ext) -> str   # content-addressed; never overwritten

class Ledger:
    save() -> None                                     # ATOMIC (temp write + os.replace + fsync)
    node(node_id) -> dict                              # the node dict for a stable path id
    nodes(kind=None, status=None) -> list[dict]        # kind ∈ {"asset","shot"}; status = run.status / run.ref_status

    write_plan(node_id, writer, **fields) -> None      # writer must be "brain"; plan-fields only; approved→pending + cascade on edit
    write_run(node_id, writer, **fields) -> None        # writer ∈ {"overlord","generating"}; run-fields only; NOT status
    set_status(node_id, status, writer) -> None         # validates the transition; writer ∈ {"overlord","generating"}

    runnable_frontier() -> list[node_id]               # pending shots w/ all deps approved + asset refs needing a draft
    reset_interrupted() -> list[node_id]               # crash recovery
    wake_dependents(node_id) -> list[node_id]          # dependents now frontier-ready (called on approve/lock)

    append_attempt(node_id, attempt: dict) -> None      # append-only 抽卡 history; sets current_attempt_id + current_artifact
    append_verdict(node_id, verdict: dict) -> None      # attaches to latest attempt + final_verdict
    current_artifact(node_id) -> dict | None

    append_lesson(lesson: dict) -> None
    lessons_for(scope: dict, k=3) -> list[dict]        # top-k by (category,model) then style_id/asset_kind, by hit_count; bumps hit_count

    validate() -> None                                 # pure-Python schema check; raises SchemaError
```
Errors: `WriterError`, `StatusError`, `SchemaError` (all subclass `LedgerError`). Import from `manju.ledger`.

### 1.5 attempt + verdict + lesson record shapes

```jsonc
// attempt — one 抽卡 take (append-only)
{ "attempt_id": "<content-hash>", "ts": "...", "seed": 7, "model": "veo3",
  "prompt": "...", "artifact_path": "...", "thumb_path": "...",
  "verdict": { ... } | null, "lesson_ref": "L1" | null }

// verdict — JUDGE output (see §4)
{ "node_id": "ep01.sc01.sh01", "modality": "image"|"video", "attempt": 1,
  "score": 0.92, "pass": true, "failure_mode": "pass", "fix_hint": "", "drift": false, "evidence": {} }

// lesson — in-ledger, retrievable, keyed by (category, model). NOT a markdown blob.
{ "lesson_id": "L1",
  "scope": { "category": "drift", "model": "veo3", "style_id": "国漫暗黑", "asset_kind": "character" },
  "symptom": "hair color shifted", "fix": "inject 固定特征词", "prompt_delta": "+银灰色眼睛", "hit_count": 3 }
```
`lessons_for(scope)` matches `(category, model)` first, then ranks style_id/asset_kind specificity, then `hit_count`; **retrieval increments hit_count** (a hit). `category` is the failure_mode/shot_type bucket.

### 1.6 Content-addressed artifacts
`artifact_path(project_dir, node_id, attempt_id, ext)` → `projects/<name>/artifacts/<node_id>/<attempt_id>.<ext>`. Named by `attempt_id`, **never overwritten** — skip-if-exists is built on this (an existing path = a reused generation).

---

## 2. The `generating` runner CLI contract (Phase 3 builds it; B & D code against it now)

**Invocation:** `python -m manju.skills.generating.runner --input <request.json>` (also accept the request on **stdin**).

**Canonical input schema** (the one schema all models route through):
```jsonc
{ "kind": "image" | "video",
  "prompt": "<5-part time-coded prompt>",
  "reference_images": ["<abs path>", ...],   // ≤ 9
  "reference_videos": ["<abs path>", ...],
  "reference_audios": ["<abs path>", ...],
  "duration_s": 4,
  "resolution": "720p",
  "aspect_ratio": "16:9",
  "generate_audio": false,
  "seed": 7,
  "model": "mock" }                          // optional; defaults to the mock provider in V1
```

**stdout = EXACTLY ONE JSON line** (the envelope) on success:
```json
{"model":"mock","output_files":["/abs/path/out.mp4"],"data":{...}}
```
- All logs go to **stderr**. stdout is the envelope and nothing else.
- **Nonzero exit on failure.** Never emit a partial envelope.

**Chain:** `presence-router → lossy per-model adapter → provider`.
1. **validate-before-spend** — validate the canonical input AND exclusivity rules BEFORE any provider call. Reject `reference_images` > 9, missing prompt, `kind` mismatch (e.g. `reference_videos` on a `kind:"image"` request), etc. No paid call happens on an invalid request.
2. **presence-router** — picks the adapter from which reference fields are present + `kind` + `model`.
3. **lossy per-model adapter** — maps the canonical schema down to one model's actual params (lossy: drops what a model can't take). Adapters live in `manju/skills/generating/adapters/`.
4. **provider** — does the call.

**Mock provider (V1 default, deterministic):**
- content-address the request → `attempt_id = sha256(canonical_json)` (stable hash of the normalized request).
- output path via `ledger.artifact_path(...)` semantics; **copy the matching `assets/sample/*`** (`kind:"image"`→`ref_face.png`, `kind:"video"`→`shot.mp4`, audio→`voice.wav`) to the output path.
- **skip-if-exists** — if the output path already exists, return it without copying. **This is how generation is reused.**

**Real providers (fal / replicate / vendor) are adapter STUBS** that raise `RuntimeError("set FAL_API_KEY")` / `("set REPLICATE_API_KEY")`. Wiring a real key is the ONLY thing left to plug in — the whole pipeline runs end-to-end on the mock today.

---

## 3. The Brain Plan-column set (Phase 1) — the exact `plan.*` the brain writes

Tooling reads a **stable shape**. The brain writes (and ONLY writes) these via `write_plan(node_id, "brain", ...)`:

**Per ASSET node** (`bible.*`):
`descriptor`, `ai_draw_keywords[]`, `固定特征词[]` (fixed-feature words → injected into every downstream prompt), `禁止变化项[]` (forbidden-change items → exposed as Overlord drift-check inputs), `style_id`.

**Per SHOT node:**
`intent`, `dialogue` (`""` if none; V.O. only for off-screen), `camera{shot_size(景别), movement(运镜), lens_mm}`, `action`, `ref_ids[]` (asset ids), `style_id`, `duration_s`, `showtell_pass` (the SHOW-DON'T-TELL gate result — must be `true` before a shot is generatable).

The brain also authors the **tree structure**: `project`, `styles[]`, the bible buckets, `episodes/scenes/shots` skeletons, and each shot's `deps[]`. Run blocks are emitted empty with `status:"pending"` / `ref_status:"none"` (see the fixture for the exact empty shape).

---

## 4. The Judge contract (Phase 4)

`JUDGE(context_sheet) -> verdict`. The judge is a **swappable vision model** (mock / Gemini-3-pro-vision / Claude-vision). **V1 ships a deterministic MOCK judge.** It is perception, never code — the control plane only assembles the sheet and records the verdict.

**Context-sheet assembly inputs** (all from the ledger, replayable):
- `intent` + the actual prompt used
- the rubric verbatim (`overlord/rubrics/<style>/<shot_type>.json`)
- `prior_lessons` = `lessons_for({category, model, style_id, asset_kind}, k)`
- `ref_role_map` (e.g. `"[Image1]=face"`) + the bible reference image(s) for drift comparison
- **image:** generated image + bible ref image(s)
- **video:** keyframe contact-sheet (9 frames at slice-centers `t = dur·(k+0.5)/n`, 3×3) + first+last frame + `probe.json` (OR native video understanding when available; contact-sheet is the universal floor)

**Verdict shape** (write with `append_verdict`):
```jsonc
{ "node_id": "...", "modality": "image"|"video", "attempt": 1, "score": 0.0-1.0, "pass": bool,
  "failure_mode": "drift"|"anatomy"|"off-prompt"|"artifact"|"motion-incoherent"|"continuity"|"text-garbled"|"pass",
  "fix_hint": "...", "drift": bool, "evidence": {...} }
```
Action policy (overlord): `pass`→`approved`+wake dependents; `fail & attempt<N_MAX(4)`→`needs_regen`+append lesson+re-roll one; `fail & attempt≥N_MAX`→`paused`+escalate; `drift=true`→ref node `needs_regen`, this node `blocked_on_ref`.

---

## 5. Skill IN/OUT table

Output path convention: everything under `projects/<name>/`. Artifacts content-addressed via `artifact_path`.

| skill (gerund) | phase | reads (ledger) | writes (ledger + artifacts) | output path |
|---|---|---|---|---|
| **referencing** | 2 | `bible.*.plan` (固定特征词/禁止变化项/ai_draw_keywords), `style_id` | asset `run`: `ref_image_paths[]`, `ref_tag` (`@char_lin`), `locked_seed`, `ref_status`→`locked` | `projects/<n>/ref_sheet/{char,scene}/NN/*.png` |
| **composing_scenes** | 2 | `shots[].plan` (景别/运镜/ref_ids) | `storyboard/.../shot_NN.spec.json` (bg/character layers separated) | `projects/<n>/storyboard/<ep>/<sc>/` |
| **building_prompts** | 3 | shot `intent`+`dialogue`+`action`+`camera`+ref_tags+`style_id` | `prompts/.../shot_NN.txt` (5-part Subject·Action·Camera·Style·Constraints + `[00:00-00:0X]` blocks + negative floor) | `projects/<n>/prompts/<ep>/<sc>/` |
| **generating** (runner) | 3 | canonical request (built from prompt + ref artifacts) | shot `run` via `append_attempt`; sets `current_artifact`; `status`→`landed` (by overlord hook) | `projects/<n>/artifacts/<node_id>/<attempt_id>.<ext>` |
| **composing** | 5 | `output_files[]` + `dialogue` + `duration_s` | routes to existing TTS/ASR/hyperframes/remotion stack → final render | `projects/<n>/render/` |

Skills write `run.*` as writer `"generating"` (or `"overlord"`); they NEVER touch `plan.*`.

---

## 6. Neighbor-stub convention (parallel build)

Each layer that depends on a not-yet-built neighbor imports it **through a thin seam module** and falls back to a documented stub, so all 5 devs run in parallel against the kernel today.

- **Where stubs live:** each skill/layer package ships a `_stub.py` next to its real module. The seam tries the real import; on `ImportError` (or when a `MANJU_USE_STUBS=1` env flag is set) it uses `_stub.py`.
- **What a stub returns:** the *documented minimal valid output* of that neighbor per the tables above — e.g. the generating-runner stub returns the mock envelope; the brain stub returns the `projects/demo/ledger.json` plan shape; the judge stub returns a deterministic `pass` verdict.
- **The kernel itself has no stubs** — it is built and is the one hard dependency everyone imports directly as `from manju.ledger import load, Ledger, WriterError`.

Example seam:
```python
try:
    from manju.skills.generating.runner import run_request          # real
except ImportError:
    from manju.skills.generating._stub import run_request           # documented mock envelope
```

---

## Decisions a downstream dev MUST know
1. **`status`/`ref_status` go through `set_status()`, never `write_run`.** `write_run` raises if you pass them.
2. **Writers are literal strings:** `"brain"` for plan, `"overlord"` or `"generating"` for run. No other value is accepted.
3. **A BRAIN plan edit auto-demotes** an approved shot (or locked asset) to pending/none and cascades to transitive dependents — you don't manage that yourself; just call `write_plan`.
4. **`runnable_frontier()` returns asset ids whose `ref_status` is `none`** (a fresh ref to draft) PLUS pending shots whose deps are all satisfied. Assets have no upstream deps.
5. **Artifacts are never overwritten.** Same `attempt_id` ⇒ same path ⇒ skip-if-exists ⇒ reuse. Re-roll = new `seed` ⇒ new `attempt_id` ⇒ new path.
6. **Chinese field names are literal keys** (`固定特征词`, `禁止变化项`, `ai_draw_keywords`) — do not transliterate; the schema and lib use them verbatim.
7. **`save()` is atomic and fsync'd** — a hook, a poller, and the judge may each write; last-writer-wins on the whole document, so read-modify-write a fresh `load()` in short critical sections.
