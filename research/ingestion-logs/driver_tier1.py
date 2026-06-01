"""Paced batch ingest of tier-1 AI-video channels into yt-rag.
Runs in background; writes a partial summary after each channel."""
import json, time, traceback
from yt_rag.ingest import ingest_channel

# (handle, n_videos, language, tier) — from the discovery workflow's verified list
CHANNELS = [
    ("@TheoreticallyMedia", 30, "en", 1),
    ("@curiousrefuge",       30, "en", 1),
    ("@mickmumpitz",         30, "en", 1),
    ("@taoprompts",          30, "en", 1),
    ("@JackVsAI",            30, "en", 1),
    ("@conorcreates123",     30, "en", 1),
    ("@BenjisAIPlayground",  30, "en", 1),
    ("@jiuyixiaoketang",     30, "zh", 1),
    ("@papayaclass",         30, "zh", 1),
    ("@lingdujieshuo",       30, "zh", 1),
    ("@joy-ai",              30, "zh", 1),
    ("@AI視覺實驗室",          30, "zh", 1),
]

SUMMARY = "/tmp/yt_ingest_summary.json"
results = []
for i, (handle, n, lang, tier) in enumerate(CHANNELS, 1):
    print(f"\n######## [{i}/{len(CHANNELS)}] {handle} (n={n}, {lang}) ########", flush=True)
    rec = {"handle": handle, "lang": lang, "tier": tier, "n_requested": n}
    try:
        rec.update(ingest_channel(handle, n))
    except Exception as e:
        rec["error"] = str(e)
        traceback.print_exc()
    results.append(rec)
    with open(SUMMARY, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    time.sleep(4)  # polite gap between channels

# Totals
tot = {k: sum(r.get(k, 0) for r in results) for k in ("videos", "chunks", "created", "no_subs")}
print("\n==== ALL DONE ====", flush=True)
print("TOTALS:", json.dumps(tot), flush=True)
print(json.dumps(results, ensure_ascii=False), flush=True)
