# Handoff — AI 漫剧 / AI short-video workflow research + corpus build
_session ended 2026-05-31. Next session: read this, then the two artifacts below, then grow your own understanding by searching the new yt-rag corpus._

## 0. What this was
Goal: figure out the best 2026 end-to-end workflow for AI 漫剧 / AI short-video / short-story generation, AND build a YouTube-transcript RAG corpus (yt-rag) of the best creator tutorials — English **and** Chinese — to learn the real workflows from.

## 1. Read these first (the findings)
1. **`research/ai-manju-short-video-workflow-2026-05-31.md`** — the multi-source research brief (Reddit + Exa + YouTube). Contains the synthesized recommended pipeline, model-pick table, what's contested, numbers to verify, and source links. **This is the substance — start here.**
2. **`research/ingestion-logs/`** — everything about the corpus build:
   - `tier1_en+zh_first-run_summary.json` — first run (7 EN succeeded; 5 ZH **failed** via the en-translation route)
   - `tier1_zh_sourcetrack_summary.json` — the ZH re-run that worked (source-track fix)
   - `tier2_summary.json` — final batch (5 EN + 3 ZH)
   - `log_verify_en-vs-zh-429.txt` — proof of the root cause (en-translation 429s, native downloads)
   - `log_*.txt`, `driver_*.py` — raw run logs + the exact drivers used

## 2. The corpus now (what you can search)
`mcp__yt-rag__list_repository` → 54 namespaces, 15,515 chunks. **19 namespaces are new this session.** The AI-video ones to search:

**English AI filmmaking / ComfyUI (12 channels, ~3,168 chunks) — high signal:**
`yt_theoreticallymedia` `yt_curiousrefuge` `yt_mickmumpitz` `yt_taoprompts` `yt_jackvsai` `yt_conorcreates123` `yt_benjisaiplayground` `yt_flo.motion` `yt_isadoesai` `yt_nerdyrodent` `yt_aiconomist` `yt_corridorcrew`

**Chinese (7 namespaces, ~1,228 chunks) — NATIVE Chinese text, mixed signal:**
`yt_jiuyixiaoketang` (AI漫剧 + monetization) · `yt_papayaclass` (Kling/Suno/Nano-Banana MV) · `yt_lingdujieshuo` (AI tools/news) · `yt_alchain` (AI coding/news) · `yt_ouycc` (agent/VCP) · `yt_linbintalk` (n8n/agentic automation) · `yt_joy-ai` (near-empty, 3 chunks)

⚠️ **Quality caveat:** the Chinese set skews toward *AI-tools / monetization / automation news*, not pure 漫剧 production craft. The deep 漫剧 "保姆级" courses live on **Bilibili**, which yt-rag cannot ingest (YouTube-only). Weigh Chinese chunks accordingly.

## 3. yt-rag code changes made this session (in `~/Desktop/yt-rag`)
All permanent improvements to the tool's own code:
- **`src/yt_rag/ingest.py`**
  - `subtitleslangs` → `["en.*"]` default (was `["en","en-US"]`; the old exact-match missed translated tracks).
  - `download_video_subs(...)` gained **`sub_langs`** + **`cookiefile`** params; sub-file glob broadened `{id}.en*.vtt` → `{id}.*.vtt`; added **`extractor_args: skip=translated_subs`** + browser **`impersonate=chrome`** + `sleep_interval_requests`/`retries`.
  - `ingest_channel(...)` gained **`sub_langs`** + **`cookiefile`**, threaded through.
- **`src/yt_rag/mcp_server.py`**
  - `ingest_channel` tool now exposes **`sub_langs`** + **`cookiefile`** (+ updated docstring).
  - **NEW `ingest_channels` tool** — batch, paced, fault-tolerant. Use this instead of writing loop-scripts.
- **venv:** added **`curl-cffi==0.14.0`** (required for impersonation; pinned to yt-dlp's supported 0.10–0.14 range).

### ⚠️ RELOAD REQUIRED
The running yt-rag MCP server has the OLD code in memory (Python doesn't hot-reload). **Restart Claude Code, or `/mcp` → reconnect `yt-rag`**, to pick up all of the above. After reload, ingestion is a single MCP call — no scripts:
```
ingest_channels([
  {"channel":"@SomeZHChannel","n_videos":20,
   "sub_langs":["zh-Hant-orig","zh-Hans-orig","zh-orig","zh-TW","zh-Hant","zh-Hans","zh"]},
  {"channel":"@SomeENChannel","n_videos":20}
])
```

## 4. The key technical lesson (so you don't repeat the pain)
YouTube **429-rate-limits its on-demand caption *generation*** — anything with a `&tlang=` param: English translations (`en-zh-TW`) AND script-conversions (`zh-Hans-zh-TW`). The **static source track** (`*-orig` ASR, or creator manual subs) is NOT rate-limited. Fix = request the `-orig`/manual track + `skip=translated_subs` + browser impersonation, on a **residential IP** (datacenter IPs are blocked regardless). This works **credential-free**. A throwaway-account `cookies.txt` (NEVER your primary) adds ~4–7× headroom and is the *only* way to reach auto-only channels (their sole captions are `tlang` conversions).

## 5. Open decisions / next moves
1. **Translation of Chinese chunks** — currently stored NATIVE Chinese (Gemini embeddings are multilingual, so they're already searchable). Decide: **read-time** translation (translate on retrieval during synthesis — recommended, zero cost) vs **ingest-time** (batch-translate all ZH chunks to English for a unified corpus). User wants "our own model" translation either way.
2. **Stragglers (optional, low value):** `@joy-ai` resolved to a wrong/near-empty handle (find the real one or drop); `@AI視覺實驗室` had 0 static tracks — needs a throwaway cookie + `skip=translated_subs` removed to grab its conversions.
3. **Expand corpus:** more AI-video channels via `ingest_channels`; consider a Bilibili ingester if the deep 漫剧 courses are wanted (separate build — yt-rag is YouTube-only).
4. **The actual deliverable:** use the corpus to write the *definitive, evidence-backed* AI 漫剧/short-video production workflow (search the namespaces in §2, cross-check against the research brief in §1).

## 6. One-line status
Research brief ✅ · 19 channels ingested (EN strong, ZH mixed) ✅ · yt-rag upgraded (reload to activate) ✅ · Chinese deep-course content still gated behind Bilibili ⚠️
