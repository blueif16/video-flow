"""Final batch: tier-2 channels. EN use default en.* ; ZH use static source-track.
Impersonation + skip=translated_subs are baked into ingest.py."""
import json, time, traceback
from yt_rag.ingest import ingest_channel

ZH_SOURCE = ["zh-Hant-orig", "zh-Hans-orig", "zh-orig",
             "zh-TW", "zh-CN", "zh-Hant", "zh-Hans", "zh"]

# (handle, n_videos, sub_langs)  sub_langs=None -> en.* default
CHANNELS = [
    ("@flo.motion",   20, None),
    ("@isadoesai",    20, None),
    ("@NerdyRodent",  20, None),
    ("@Aiconomist",   20, None),
    ("@CorridorCrew", 15, None),
    ("@OUYCC",        20, ZH_SOURCE),
    ("@Alchain",      20, ZH_SOURCE),
    ("@linbintalk",   15, ZH_SOURCE),
]
SUMMARY = "/tmp/yt_ingest_tier2_summary.json"
results = []
for i, (handle, n, langs) in enumerate(CHANNELS, 1):
    lang = "zh" if langs else "en"
    print(f"\n######## [{i}/{len(CHANNELS)}] {handle} (n={n}, {lang}) ########", flush=True)
    rec = {"handle": handle, "lang": lang, "tier": 2, "n_requested": n}
    try:
        rec.update(ingest_channel(handle, n, sub_langs=langs))
    except Exception as e:
        rec["error"] = str(e)
        traceback.print_exc()
    results.append(rec)
    with open(SUMMARY, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    time.sleep(5)

tot = {k: sum(r.get(k, 0) for r in results) for k in ("videos", "chunks", "created", "no_subs")}
print("\n==== TIER-2 DONE ====", flush=True)
print("TOTALS:", json.dumps(tot), flush=True)
print(json.dumps(results, ensure_ascii=False), flush=True)
