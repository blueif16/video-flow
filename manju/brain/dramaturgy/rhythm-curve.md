# Rhythm curve (distilled from 0xsline/short-drama, MIT)

Two nested rhythms: the **per-episode micro-3-act** and the **whole-series
waveform**. The brain lays both deterministically before writing shots.

## Per-episode micro-3-act (a ~150s episode budget)

| beat          | budget | job                                                        |
|---------------|--------|------------------------------------------------------------|
| `hook_30s`    | 30s    | first 30 seconds: land a conflict/question. NO 旁白 dump.   |
| `escalation_90s` | 90s | stack 压抑 setups + rising complications toward the payload |
| `payload_30s` | 30s    | the episode's main 爽点 释放; then a cliffhanger (non-finale) |

Shot durations within an episode are allocated against this 30/90/30 split, so
the payload always lands late and the hook always lands first. For short test
episodes the same proportions scale down.

## Whole-series waveform (4 stages)

| stage  | name | density | 强度 band | 加速:减速 | role                                  |
|--------|------|---------|-----------|-----------|---------------------------------------|
| 起势   | rise   | low–med | 0.45–0.60 | 1:1       | establish world, plant first 压抑      |
| 攀升   | climb  | med     | 0.60–0.75 | 2:1       | stack payoffs, villains escalate       |
| 风暴   | storm  | high    | 0.75–0.90 | 3:1       | dense 爽点, big-villain confrontation   |
| 决战   | finale | peak    | 0.90–1.00 | 4:1 → resolve | hidden villain unmasked, top 爽点  |

- **density** = 爽点-per-episode pressure (more payoffs packed as the series climbs).
- **强度** = intensity ceiling for that stage; the matrix's monotonic escalation
  rides this band.
- **加速:减速** = ratio of accelerating (tension-up) to decelerating (breath)
  beats. Higher stages spend more time accelerating; the small 减速 valleys are
  the only places 强度 may dip below the running max.

The brain maps episode index → stage by even partition over N episodes (a 1-ep
test maps to 决战 so the single episode carries a full payload + finale rules),
then clamps each episode's payload 强度 into that stage's band.

## Where the LLM brain plugs in
The waveform and 30/90/30 split are genre-blind scaffolding. A future LLM brain
keeps the same stage partition + micro-3-act budget; only the *content* of each
beat changes. The emitted shot `duration_s` allocation against the budget is the
visible seam.
