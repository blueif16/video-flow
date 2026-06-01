# AI 漫剧 workflow: orchestration architecture (ComfyUI vs pure Claude-Code) + battle-tested templates
_scope: corpus re-search (EN+ZH, the 19 newly-ingested channels) + Exa verification • generated 2026-05-31 • companion to `ai-manju-short-video-workflow-2026-05-31.md`_

## TL;DR
1. **It's not ComfyUI vs code — it's a two-layer split.** Orchestration (script→reference-library→shot-routing→assemble→QC) should be **code Claude owns natively** (a skill/YAML DAG + your own node renderer). Generation (the actual image/video) is a **tool the brain calls**. ComfyUI is a great *generation engine* and a terrible *orchestrator*. [E][Y]
2. **You never have to make Claude "speak ComfyUI's visual language."** ComfyUI is "a workflow engine with a server wrapped around it" — drive it through its HTTP `/prompt` API with **API-format JSON** (or an MCP server). The canvas is just one client; `curl` is another. Claude authors/edits that JSON like any other JSON. [E]
3. **The battle-tested 漫剧 path in May 2026 is closed-API + an LLM brain — no ComfyUI in sight.** 九姨/PAPAYA/Jack-vs-AI/Theoretically-Media all run: GPT/Claude writes shot-list → Nano Banana (Pro) character sheet → reference-to-image per shot → i2v (Seedance 2 / Kling 3 / Domo) → 剪映/Resolve. ComfyUI only shows up when people self-host open models (WAN/LTX/Flux) for cost/uncensored at scale. [Y]

## The architecture decision (your actual question)
**Recommendation: pure Claude-Code orchestration (skill/YAML DAG + custom DAG-renderer front-end), closed-API generation by default, ComfyUI wired in ONLY as a self-host generation tool via its API/MCP when you need open models.** Don't make ComfyUI the orchestrator; don't make Claude "speak ComfyUI."

Why, layer by layer:

### Orchestration layer = code (NOT ComfyUI)
- Three independent sources converge: **AI学长小林** (工作流 vs Agent: the workflow/skill owns the skeleton — triggers, dataflow, perms, error-handling, audit; the Agent owns the judgment nodes), the **Synta** "Claude Code vs n8n" piece (Claude Code = code-first build speed; n8n = runtime visibility/retries/approvals; best teams use *both*), and **Runchat/Runflow** (ComfyUI "has no built-in scheduling, conditional branching, webhook handling, or orchestration"). [Y][E]
- Two builders already shipped your exact vision — **code DAG driven by Claude, with a visual node front-end, no ComfyUI syntax**:
  - **Cole Medin / Archon** — open-source "harness builder": encode any agentic process as a single **YAML node-by-node workflow**, run via Claude Code, artifact-dir passes data between nodes, worktree isolation for parallel runs. Demo'd Claude Code + Remotion + ElevenLabs end-to-end. https://youtu.be/vhbaZJtW2Hg?t=459
  - **Benji / Muse Studio** — Kanban UI over story→scene→keyframe→video→approve, imports any ComfyUI workflow via API-JSON, auto-detects inputs/outputs; built in **~2 weeks vibe-coding with Claude**. https://youtu.be/IpDTneyFC1o?t=1293
- Productized proof the UX lands: **VoooAI "NL2Workflow"** (one sentence → visual node canvas, every node editable) and **九姨's "Sjinn AI/AI导演"** (one prompt → full 漫剧). Both are visual-node, not chat. Quality is "directional," not hero-tier.

### Generation layer = a tool the brain calls
- **Closed-API (default for 漫剧):** Seedance 2 / Kling 3 / Veo / Nano Banana via vendor or fal.ai. No ComfyUI needed at all — pure code wins outright. This is what every battle-tested 漫剧 template actually uses.
- **Open/self-host (only if cost-at-scale / uncensored / no per-clip fee):** ComfyUI is the best engine — but you wire it behind your code orchestrator via its API or MCP, never as the orchestrator.
  - ComfyUI API: HTTP+WS on `:8188`, POST the node graph to `/prompt`. **Gotcha:** API-format JSON ≠ the save/load JSON — export via Dev Mode → "Save (API Format)" (the #1 first-integration failure). [E, Runflow guide 2026-04-22]
  - Agent control today: **ComfyUI-MCP-Server** / `comfyui_LLM_party` (Benji demo: LLM batch-runs workflows by tool-call, parameterized nodes). [Y]
  - Reference build: **`github.com/12georgiadis/comfyui-cinema-pipeline`** — Claude Code (MCP) = "brain/orchestrator" → ComfyUI Local + Comfy Cloud + DaVinci; 70+ workflows w/ honest stability ratings. Confirms the split AND flags the limit: **"true headless NLE for AI-agent control = research phase," "FCP+ComfyUI direct = 0/10 does not exist."** [E]
- n8n+ComfyUI battle-tested templates exist (eimoon Ghibli generator; **22b-studio** 7-stage repo; aaron.de Google-Sheets-as-queue) — good if you want a runtime with retries/visibility for free, but it's a heavier substrate than a Claude skill if Claude owns the whole thing.

### Reality check on "zero human involvement"
Achievable for the *mechanical* work, but everyone actually shipping keeps a human at the **cheap checkpoints** (script approve, sketch/keyframe gate) because regen rate is 30–50% and full hands-off still drifts. **22b-studio** bakes "human review at every checkpoint" + "fail cheaply at sketch, full-render only approved scenes." **Benji's Hermes** pipeline explicitly keeps "human in the loop." → Design the front-end around **approve/redo nodes at the cheap stages**, not pure fire-and-forget. The one-prompt tools (Sjinn/VoooAI) prove fire-and-forget works at "directional" quality only.

## Battle-tested production templates (from the corpus, May 2026)
**EN — asset-first closed-API (the dominant pattern):**
- **Theoretically Media "Dragon Blue"** — Claude (Co-work) holds char/scene/prompt templates + production tracker + safety-word substitution log; Nano Banana Pro spray-and-pray (~400 imgs, 2×2 grids) → Dreamina/Seedance Omni multi-ref i2v → "best moments from each gen, edit together." 2 days, 85 shots→32 used (2.66 ratio). https://youtu.be/ORuSQ0Fui-A
- **Jack vs AI** — Claude writes the prompt framework → Nano Banana 2 character sheets (suited/unsuited variants, all angles) → Seedance 2 i2v; "Seedance beats Kling on VFX/continuity; Kling tears on motion blur." https://youtu.be/suIwxbO-_ZE
- **Tao Prompts** — one Nano Banana 2 prompt → 8-shot char sheet (4 full-body + 4 face) → Kling Omni-reference (label image1/2/3, call them in prompt). https://youtu.be/2psBexPkw3I
- **Isa does AI** — reference-library discipline: every character/location/prop gets its own ref file, tagged into *every* scene prompt; one strong visual per character. https://youtu.be/WTHuRRmt1RQ
- **Mickmumpitz** — deepest open/local char consistency: char-sheet → LoRA (FluxGym) → IP-adapter → Blender+ComfyUI for multi-char + camera control. https://youtu.be/YpuSE9hcal8
- **Aiconomist** — influencer-farm automation: WAN 2.1/2.2 + Lightning LoRA in ComfyUI, StableVideoInfinity for 1-min no-drift, + "automate ComfyUI from Telegram via OpenClaw." https://youtu.be/teEychmxy6c

**ZH — 漫剧 流水线 (one-prompt or GPT-scripted):**
- **九姨小課堂** — (a) GPT picks theme → GPT 分镜脚本 (角色设定+分镜+运动+音效提示词) → Nano Banana Pro 风格/角色参考图 → Domo AI 图生视频 → 剪映 (split人声/BGM, 加字幕). https://youtu.be/iiI-CiS_sis  (b) "Sjinn AI 一条指令" all-in-one 导演. https://youtu.be/4GsGyfqG3m8 — 35h→1亿播放; 出海 RPM 远高于国内.
- **PAPAYA 電腦教室** — 一人動畫公司: Midjourney concept (+Moodboard for style lock) → Nano Banana char ref → ChatGPT 分镜 → **背景/人物分开生成再合成** (upload order sets aspect ratio!) → i2v (pick best model per shot) → Suno BGM → Premiere keyframe for camera moves. https://youtu.be/KHCHTCXGyug
- **AI学长小林** — the orchestration brain: n8n raised $180M (Nvidia), $2.5B val, 6× users; Agent Skills vs n8n = complementary not replacement (Skills fault-tolerant but slow+token-heavy; n8n stable+tool-reliant). https://youtu.be/3R4jdMtLtzk

**Code-as-video (the Western orchestration mirror):**
- **John Hartquist** — Claude Code + Remotion + Replicate/VO3/Nano Banana/ElevenLabs MCP, reusable React components, git, `/transcribe` word-timing. https://youtu.be/z7Bkf3Vc63U
- **Cole Medin / Archon** + **Benji / Muse Studio** — see architecture section.

## Sources
### YouTube (yt-rag, deep-linked)
- Theoretically Media "Dragon Blue" — https://youtu.be/ORuSQ0Fui-A?t=306 ; ComfyUI App Mode — https://youtu.be/STHQPWLTXtc?t=546
- Jack vs AI Seedance 2 — https://youtu.be/suIwxbO-_ZE?t=462 ; Tao Prompts char sheet — https://youtu.be/2psBexPkw3I?t=93
- Mickmumpitz ComfyUI movies — https://youtu.be/YpuSE9hcal8?t=638 ; Nerdy Rodent LTX-2 — https://youtu.be/tufeXrzYgrs
- Benji ComfyUI+MCP — https://youtu.be/Yk7y56Kk-LI?t=366 ; Muse Studio — https://youtu.be/IpDTneyFC1o?t=1293 ; Hermes pipeline — https://youtu.be/6jPhOTUlPq8?t=273
- Aiconomist OpenClaw→ComfyUI — https://youtu.be/xm788ZdsXjI ; long influencer vids — https://youtu.be/teEychmxy6c?t=463
- 九姨 漫剧拆解 — https://youtu.be/iiI-CiS_sis?t=91 ; Sjinn 一条指令 — https://youtu.be/4GsGyfqG3m8 ; PAPAYA 一人動畫 — https://youtu.be/KHCHTCXGyug?t=183
- AI学长小林 工作流vsAgent — https://youtu.be/3R4jdMtLtzk?t=275 ; n8n vs Agent Skills — https://youtu.be/96LG1nms23Q
- John Hartquist Claude+Remotion — https://youtu.be/z7Bkf3Vc63U ; Cole Medin Archon — https://youtu.be/vhbaZJtW2Hg?t=459
### Exa (web)
- ComfyUI API developer guide — runflow.io/blog/comfyui-api-developer-guide (2026-04-22)
- comfyui-cinema-pipeline (Claude Code MCP = brain) — github.com/12georgiadis/comfyui-cinema-pipeline (2026-02)
- Claude Code vs n8n decision framework — synta.io/blog/claude-code-vs-n8n (2026-03-25)
- Runchat vs ComfyUI vs n8n vs Langflow — runchat.com (2026-03-27)
- n8n+ComfyUI Ghibli generator — blog.eimoon.com (2025-06) ; 22b-studio 7-stage repo — github.com/sinmb79/22b-studio (2026-04) ; Sheets-queue — aaron.de (2026-01)
- VoooAI NL2Workflow (visual node canvas, one-sentence) — voooai.com/workflow-comparison

## Method notes
- yt-rag legs (12 searches, EN+ZH, the newly-ingested channels) + 2 Exa probes (ComfyUI-API / orchestration-comparison). No Reddit leg this pass.
- Highest-confidence result: the orchestrator/generator split is asserted independently by a ZH creator, a Western SaaS comparison, a GitHub cinema repo, and the ComfyUI API docs — strong convergence.
- Corpus has MORE than the handoff listed: `yt_ae_to_code_recreation` (Cole Medin, Moritz), `yt_remotion_motion` (John Hartquist), `yt_lewiswjackson` — all useful for the code-orchestration angle.
