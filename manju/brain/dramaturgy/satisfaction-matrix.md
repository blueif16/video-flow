# 爽点 matrix — 压抑→释放 (distilled from 0xsline/short-drama, MIT)

The engine of 爽剧: every release (释放, 爽点) is **earned** by a prior setup of
suppression (压抑). A 爽点 with no setup is not satisfying — it reads as a power
fantasy with no stakes. The brain encodes this as a hard self-check.

## The 5 爽点 archetypes (escalating intensity)

| # | archetype     | the 压抑 it pays off                         | the 释放 (filmable beat)                              | base 强度 |
|---|---------------|---------------------------------------------|------------------------------------------------------|-----------|
| 1 | 身份碾压       | hero treated as worthless / nobody          | true identity/rank revealed; oppressor must kneel    | 0.55      |
| 2 | 打脸复仇       | hero humiliated, mocked, wronged            | the mocker is publicly, concretely defeated          | 0.65      |
| 3 | 逆袭翻盘       | hero cornered, outmatched, written off      | a hidden card flips the board in one move            | 0.75      |
| 4 | 情感爆发       | hero suppresses grief/loyalty/love silently | the dam breaks — one decisive emotional action       | 0.70      |
| 5 | 悬念揭秘       | a planted question gnaws unanswered         | the truth lands and recolors everything prior        | 0.80      |

`强度` (intensity) is a 0–1 dial. It must **escalate** across the series: each
later 爽点 of the same or higher tier should not undershoot the running max minus
a small dip-allowance (the rhythm curve's 减速 valleys). The brain raises 强度
monotonically across episodes per the rhythm waveform.

## The hard rule (encoded as a self-check, blocking)

> **Every 爽点 must cite ≥1 prior 压抑 setup (by id) or the brain rejects it.**

A 压抑 setup is a small, concrete, *shown* humiliation/loss/threat placed earlier
in the timeline. The check is structural: a release beat carries `pays_off: [setup_id, ...]`,
and the referenced setup must exist **earlier** in the ordered beat list. No
forward references, no orphan 爽点.

```
压抑(setup)  →  …distance…  →  释放(爽点, pays_off=[setup])
   ^ shown, concrete, earlier            ^ rejected if pays_off is empty
```

Tuning the suppression→release distance: too short = cheap; too long = audience
forgets. The brain places at least one setup in the same or immediately prior
episode as each payoff.

## Where the LLM brain plugs in
The 爽剧 V1 brain instantiates archetypes deterministically from `主爽点类型`.
A future LLM brain may *write richer setups/payoffs* but must still emit beats
carrying `pays_off[]` and pass the identical self-check — the check is genre-blind.
