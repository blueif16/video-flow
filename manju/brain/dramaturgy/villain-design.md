# Villain design — 4-tier escalation (distilled from 0xsline/short-drama, MIT)

Antagonist pressure must escalate so each 爽点 release clears a *bigger* obstacle
than the last. The brain instantiates four tiers and wires them to the rhythm
stages.

## The 4 tiers

| tier | name   | role                                            | first appears | beaten at        |
|------|--------|-------------------------------------------------|---------------|------------------|
| 小   | 小反派 | the everyday humiliator; cheap 压抑 fodder       | 起势          | 起势/攀升 (打脸)  |
| 中   | 中反派 | a faction lieutenant; first real resistance     | 攀升          | 攀升/风暴         |
| 大   | 大反派 | the named arch-antagonist; series-long pressure  | 风暴          | 决战             |
| 隐藏 | 隐藏反派 | the true hand behind it all; the final reversal | 决战 (unmask) | 决战 (top 爽点)   |

Each tier's defeat is itself a 爽点 (打脸复仇 / 逆袭翻盘 / 身份碾压), escalating in 强度.

## The hard rule (encoded, blocking)

> **The 隐藏反派 requires `foreshadows[] ≥ 3`, each `{episode, line_ref}`, or it is rejected.**

A hidden villain that appears out of nowhere is a cheat. The reveal only lands if
it was *seeded*: at least three earlier, concrete, on-screen hints (a line, an
object, an off-beat reaction) tied to specific episodes/shots. The brain rejects
a 隐藏反派 whose `foreshadows` list has fewer than three `{episode, line_ref}`
entries.

```
隐藏反派.foreshadows = [
  {episode: "ep01", line_ref: "ep01.sc01.sh02"},   # a planted glance
  {episode: "ep02", line_ref: "ep02.sc01.sh03"},   # an object that recurs
  {episode: "ep03", line_ref: "ep03.sc02.sh01"},   # a line that rereads later
]   # len < 3 → rejected
```

Foreshadow `line_ref`s must point at shots that exist **earlier** than the reveal.

## Where the LLM brain plugs in
V1 derives tiers from N and seeds the minimum 3 foreshadows deterministically. A
future LLM brain may plant richer hints but must still emit a 隐藏反派 carrying
≥3 valid `{episode, line_ref}` foreshadows — the gate is genre-blind.
