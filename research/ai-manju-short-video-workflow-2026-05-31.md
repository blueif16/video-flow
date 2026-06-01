# AI 漫剧 / AI short-video production workflow (June 2026) — research brief
_scope: last ~6mo (Dec 2025 → May 2026), creative/AI-video lens, deep dive • 4 legs (Reddit + YouTube-RAG + Exa×2) • generated 2026-05-31_

## TL;DR
1. **The winning workflow is asset-first, not prompt-first.** Build a *locked subject library* (character three-view sheets + people-free scene plates + props) with an image model, then drive video by **reference/image-to-video — never raw text-to-video**. This single decision is what holds character identity across cuts and is repeatedly called "the moat." [R][Y][E1][E2]
2. **No single model wins — route per shot.** A 500-generation blind benchmark and Chinese studio practice agree: use Seedance 2.0 / Kling 3.0 / Vidu / Veo 3.x / Sora 2 each for what it's best at, in one pipeline. [E1][E2][Y]
3. **The efficiency unlock is an agent orchestrator, not a faster model.** China's industrial 漫剧 pipelines (巨日禄, 万兴剧厂, 小云雀, Vidu) auto-decompose script → character files → storyboard → batch-generate → edit-draft, taking "3 people / 15 days" down to "1 person / 1 day" and lifting usable-take rate from ~30% to ~90%. The Western mirror is Remotion + Claude Code skills. [E1][E2][Y]

## The recommended pipeline (synthesized best practice, June 2026)

```
1. SCRIPT      LLM (Claude / GPT / Gemini) writes a SHOT-LISTED script.
   ↓           Lock structure before any art: Hook(0–3s) → Friction → Spike(60–90s) → Button.
2. ASSET LIB   Image model builds a reusable "subject library / 主体库 / 角色卡":
   ↓           character 3-view sheets + clean people-free scene plates + props.
               Tools: Seedream · 即梦 Dreamina · Nano Banana (Pro) · Midjourney V7 · Flux.
3. KEYFRAMES   Generate first/last frames per shot FROM the locked references.
   ↓           (first-last-frame chaining = consistency + longer takes)
4. VIDEO       Reference/image-to-video, ROUTED PER SHOT-TYPE:
   ↓             · hero / dialogue / lip-sync  → Seedance 2.0 (quad-modal refs)
                 · cinematic realism / B-roll   → Veo 3.x
                 · long narrative take (≤25s)    → Sora 2 Pro
                 · anime / 漫剧 cel style + cheap detail/hands → Vidu Q3 (生数)
                 · multi-shot storyboard / 4K / value-at-scale → Kling 3.0 (可灵)
                 · fast exploration              → Runway Gen-4 Turbo · Hailuo 02
                 · open / self-host              → Wan 2.x in ComfyUI (Animate, FLF, LoRA)
5. AUDIO       ElevenLabs for hero VO + edge-tts / Kokoro for bulk; lip-sync as a SEPARATE pass.
   ↓
6. ASSEMBLE    DaVinci Resolve · 剪映/CapCut · or Remotion (code-as-video, frame-precise AI edits).
   ↓
7. FIX         Composite / cleanup in AE / Nuke. Plan for 30–50% regeneration — it's normal.

ORCHESTRATION layer over the whole chain: n8n / fal.ai router + an agent
(巨日禄 · Vidu · 万兴剧厂 · 小云雀) OR Remotion + Claude Code / MCP skills.
```

## What's working (claimed)
- **Asset/subject library before generation** is the consistency fix everyone converged on — Vidu 主体库, Sora "3-second subject lock", 即梦/Seedance reference modes, and the open-source LoRA + first-last-frame equivalent. [E1][E2][R]
- **Reference-to-video / image-to-video beats text-to-video** for any multi-shot story; describe characters in heavy detail at first appearance. [E1][E2]
- **Multi-model per-shot routing** ("Seedance for main frames, Vidu ~0.2元/s for hands/detail, Kling for empty/transition shots — never one model"). [E2]
- **Script & structure first, art later** — write a text shot-list before thumbnailing; front-load hook + curiosity gap + ending. (Pantoja, Vane Motion, Veritasium, Kurzgesagt all independently.) [Y]
- **Agent batch-automation** auto-parses script → character files → storyboard → video draft; the human only picks the genre formula, approves keyframes, and iterates on completion-rate data. [E1][E2]
- **Open/local workhorse:** WAN 2.2 14B + GGUF quantization + Kijai Lightning LoRAs in ComfyUI; LTX-2.3 with IC-LoRA / ID-LoRA (single ref image + audio → identity+voice locked). [R][E1]
- **Code-as-video** (Remotion + Claude Code / OpenCode): reusable overlay/caption/B-roll components, git history, and a frame/timestamp debug overlay so you can tell the AI exactly which frames to edit. [Y]
- **Perceived quality = craft, not model:** timing/spacing contrast (fast move → hard slow-out), hold key poses, on-twos vs on-threes, arcs/slow-in-out; and *shorter runtime sustains higher quality* — "hint at a wider story" instead of padding. [Y]

## What's broken / contested
- **Vendor consistency claims vs. reality.** Marketing touts "world's best" consistency (Gen-4.5, LTX-2, 1,247 Elo), but the highest-signal hands-on report says consistency is "weak across the board" and demo shots are cherry-picked. [R]
- **"Fast" models aren't fast on consumer GPUs.** Real throughput is still poor: ~5 min / 5s clip on 12GB (WAN 2.2 Q4), ~30 min / clip on 4GB (WAN 5B), 7–8 min for HD/15s (LTX-2). Speed claims assume tuned setups (GGUF, sageattention, `--novram`). [R]
- **China's 90%-usable-rate is unverified** beyond vendor/press sources (techtimes, 36kr, kejixun). Treat as directional, not proven. [E1][E2]
- **Sora is simultaneously hyped and eulogized** — praised for anime motion, yet multiple "Farewell Sora" posts and a School-of-Motion claim it shut down ~15 months in from "uniqueness fatigue," reportedly walking from a ~$1B Disney deal. Verify before betting on it. [R][Y]
- **Two practitioner camps** that don't fully agree: local/open (ComfyUI: WAN/LTX) vs. closed-API (Sora 2 / Gen-4.5 / Kling). Consistency is solved by *workflow*, not by either camp's flagship model. [R]

## Numbers worth verifying
- China: **~470 AI titles/day**; 巨日禄 agent "3 people·15 days → 1 person·1 day", Seedance 2.0 usable rate **30% → 90%+**. [E1]
- Hits: **《霍去病》 ~5亿 views**, ~6 min, **~3,000元 compute**, 360 纳米漫剧流水线; **《风水天师》 ~3.7亿 views**, #1 红果 漫剧 (director 唐季礼). [E2]
- Cost tiers: **Kling 3.0 ~$0.39–0.50/clip**, **Vidu ~0.2元/s off-peak**, Runway Gen-4 Turbo ~30s gen. Hard per-second API prices for Seedance 2.0 / Veo 3.x / Sora 2 Pro were NOT surfaced. [E1]
- Solo throughput: AI-mandrama Claude-Skills SOP (Dreamina + edge-tts + ffmpeg) ≈ **1 episode / ~5h**; 《丧尸清道夫》 solo 10-day short on Seedance 2.0. [E1][E2]

## Next moves
- **Concrete experiment:** Build one 60–90s vertical 漫剧 episode end-to-end using the asset-first chain above — lock a 角色卡 first, generate first/last keyframes, route 2–3 shots across Seedance/Vidu/Kling, assemble in CapCut/Resolve. Measure your own usable-take rate; that's the real KPI.
- **Clone the reference repos:** `github.com/cyuanxv/ai-mandrama-skills` (Claude Code Skills SOP for 漫剧), the `poptechstudio` n8n + Qdrant + fal.ai + Remotion + ComfyUI self-host stack, and `ID-LoRA` for identity locking.
- **Ingest the missing best-practice channels into yt-rag** (the corpus has zero true generative-video creators today). Top picks, all reproducible-pipeline channels: **@TheoreticallyMedia** (deepest tool-by-tool, cost-transparent breakdowns), **@CorridorCrew** (AI-anime workflow), **@curious-refuge** (AI-film competitions + judging rubrics), **@AiSamson** (model launches/impact), **@isadoesai** (sub-hour music-video + lip-sync). Note: top Chinese 漫剧 creators (沐心, 杨涵涵, 万俟枫) publish on 抖音/红果/B站, not YouTube — capture them via case-study articles, not channel ingest. *(Say the word and I'll ingest the Western set.)*

## Sources
### Reddit
- WAN 2.2 14B GGUF Q4 + UMT5XXL + Kijai Lightning LoRA, ~5min/5s on 12GB — r/comfyui, 2025-08-09 — https://www.reddit.com/r/comfyui/comments/1mlcv9w/
- LTX-2 I2V fp8 `--novram`: HD/15s in 7-8min, weak face consistency — r/StableDiffusion, 2026-01-11 — https://www.reddit.com/r/StableDiffusion/comments/1qae922/
- Sora anime pipeline: 15s gens stitched in Premiere, bilingual JP/EN prompt + animation-principles scaffold — r/SoraAi, 2025-11-01 — https://www.reddit.com/r/SoraAi/comments/1olp7hg/
- WAN 2.1 I2V + trained LoRA + last-frame chaining for 30s consistent clips — r/StableDiffusion, 2025-04-04 — https://www.reddit.com/r/StableDiffusion/comments/1jr6j11/
- Runway Gen-4.5 I2V pitched for longer/consistent stories; now MCP into Claude/Cursor — r/runwayml, 2026-01-21 — https://www.reddit.com/r/runwayml/comments/1qjbfp8/
- Multi-agent "story bible" + hierarchical generation kills long-form drift — r/bittensor_, 2026-01-04 — https://www.reddit.com/r/bittensor_/comments/1q3obg7/
### YouTube (yt-rag, adjacent corpus — deep links keep MM:SS)
- AI video pipeline in code: Claude Code + Remotion + VO3.1/Nano Banana + ElevenLabs + `/transcribe` word-timing — John Hartquist, 2025-12-06 — https://youtu.be/z7Bkf3Vc63U?t=373
- Reusable Remotion overlay/caption/B-roll components driven by agents; frame-debug overlay for AI edits — CodingMenace, 2026-02-22 — https://youtu.be/K4DxhkFUFyM?t=817
- Script must hit hook + curiosity gap + epic ending before any animation — Vane Motion, 2026-05-19 — https://youtu.be/NUQyUctGQIQ?t=93
- Storyboarding = directing (POV, emotion, angle = power/intimacy) — Toniko Pantoja, 2026-01-11 — https://youtu.be/rSv2m_QO9G0?t=104
- Text shot-list before thumbnailing; simple shots reuse better in edit — Toniko Pantoja, 2025-10-20 — https://youtu.be/PJ4a2XKJJEU?t=378
- Surviving AI tools give "leverage over taste"; Sora died of "uniqueness fatigue" — School of Motion, 2026-03-30 — https://youtu.be/KGAN0TWt9jg?t=539
- Pro AI brand-film: mix tools (Unreal→Higgsfield/Kling, Nano Banana first frame), AI needs direction — School of Motion, 2026-01-26 — https://youtu.be/5Qx0EhMbNzI?t=443
- Quality reads via timing/spacing contrast, on-twos→threes, squash-stretch, holding key poses — Howard Wimshurst, 2025-12-16 — https://youtu.be/DZWXn7Jgvo8?t=740
- Shorter runtime = higher sustainable quality; hint at a wider story — Howard Wimshurst, 2025-08-16 — https://youtu.be/bgC7A3ea--Q?t=185
### Exa — tools & orchestration
- 500-gen blind benchmark: no model wins all, route per shot-type — medium.com/@cliprise, 2026-02-21 — https://medium.com/@cliprise/i-generated-500-videos-across-6-ai-models-the-definitive-quality-speed-and-cost-comparison-43fb271e509c
- Vidu 漫剧 whitepaper: 参考生视频 + 主体库 lifts output 4–5× — news.qq.com, 2026-04-16 — https://news.qq.com/rain/a/20260416A059LJ00
- China at scale: 470 AI titles/day, Seedance 2.0 + Kling 3.0 + Nano Banana, 90%+ usable — techtimes.com, 2026-05-22
- 巨日禄 agent: 3p/15d → 1p/1d, Seedance 2.0 usable 30%→90% — kejixun.co, 2026-04-30 — https://www.kejixun.co/article/751775.html
- Spec table Seedance 2.0 / Kling 3.0 / Sora 2 / Veo — ccapi.ai, 2026-02-16 — https://ccapi.ai/blog/seedance-2-vs-sora-vs-kling-vs-veo
- Western 6-stage SOP: character sheet → i2v anchor → separate lip-sync → Resolve, 30–50% regen — apatero.com, 2026-03-29 — https://apatero.com/blog/ai-short-film-creation-complete-pipeline-2026
- Self-host: n8n + Qdrant RAG + fal.ai router + Remotion + ComfyUI — github.com/poptechstudio, 2026-04-13
- Claude Code Skills 漫剧 SOP: Dreamina + edge-tts + ffmpeg, ~5h/episode — github.com/cyuanxv/ai-mandrama-skills, 2026-05
### Exa — examples & creators
- "Dragon Blue" full pipeline: Seedance 2.0 + Nano Banana Pro + Claude — Theoretically Media, 2026-03-26 — https://www.youtube.com/watch?v=ORuSQ0Fui-A
- Curious Refuge Feel-Good AI Film comp (finalists + judging criteria) — 2026-04-09 — https://www.youtube.com/watch?v=oOfPFeF62j4
- Vertical-drama "Beat Engine" (Hook/Friction/Spike/Button per second) — real-reel.com, 2026-04-03 — https://www.real-reel.com/vertical-drama-script-guide-film-tv-creators/
- 《风水之王》creator 沐心: solo daily-update, Vidu/即梦/Seedance per-shot — k.sina.cn, 2026-03-15
- 《霍去病》5亿播放: 360 纳米漫剧流水线 + character library, 90% first-pass — 36kr.com, 2026-05-31
- 小云雀短剧 Agent workflow + genre prompt templates — woshipm.com, 2026-05-16

## Method notes
- Legs run: A (Reddit / apify-macrocosmos) + B (YouTube / yt-rag adjacent corpus) + C1 (Exa tools/orchestration) + C2 (Exa examples/creators). No WebSearch A/B probe (deep dive).
- **Empty / weak:** r/KlingAI returned no posts; r/midjourney only memes; the Reddit site-wide scan ignored the keyword and returned default-sub noise. yt-rag has **no dedicated generative-video namespace** — the YouTube leg mined adjacent craft/sentiment channels (Corridor, School of Motion, animation-craft), not direct AI-video creators.
- **Echo-chamber check:** the four legs were largely *independent* — Reddit surfaced the open/local stack, Exa surfaced the Chinese industrial stack, YouTube supplied story-craft principles. Convergence on "asset-first + per-shot routing + agent orchestration" across independent legs is the highest-confidence result here.
- **Biggest unverified claim:** China's 90%-usable-rate and the throughput multipliers (all vendor/press-sourced). Validate with your own pilot before trusting.
