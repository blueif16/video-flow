"""Re-ingest the 5 tier-1 Chinese channels using the STATIC SOURCE track only
(-orig / manual subs), skipping the 429-prone tlang translation endpoint.
Browser impersonation + skip=translated_subs are baked into ingest.py.
Stores NATIVE Chinese text; we translate to English downstream."""
import json, time, traceback
from yt_rag.ingest import ingest_channel

# Source/manual tracks only — never the "X from Y" tlang conversions.
SOURCE_LANGS = ["zh-Hant-orig", "zh-Hans-orig", "zh-orig",
                "zh-TW", "zh-CN", "zh-Hant", "zh-Hans", "zh"]
COOKIES = None  # credential-free works; set a path here for throwaway-acct headroom

CHANNELS = [
    ("@jiuyixiaoketang", 30),
    ("@papayaclass",     30),
    ("@lingdujieshuo",   30),
    ("@joy-ai",          30),
    ("@AI視覺實驗室",      30),
]
SUMMARY = "/tmp/yt_ingest_zh_summary.json"
results = []
for i, (handle, n) in enumerate(CHANNELS, 1):
    print(f"\n######## [{i}/{len(CHANNELS)}] {handle} (n={n}, source-track) ########", flush=True)
    rec = {"handle": handle, "lang": "zh", "n_requested": n}
    try:
        rec.update(ingest_channel(handle, n, sub_langs=SOURCE_LANGS, cookiefile=COOKIES))
    except Exception as e:
        rec["error"] = str(e)
        traceback.print_exc()
    results.append(rec)
    with open(SUMMARY, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    time.sleep(5)

tot = {k: sum(r.get(k, 0) for r in results) for k in ("videos", "chunks", "created", "no_subs")}
print("\n==== ZH SOURCE-TRACK RE-RUN DONE ====", flush=True)
print("TOTALS:", json.dumps(tot), flush=True)
print(json.dumps(results, ensure_ascii=False), flush=True)
