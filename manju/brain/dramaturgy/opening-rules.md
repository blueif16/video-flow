# Opening rules — the cold open (distilled from 0xsline/short-drama, MIT)

Episode 1 has ~3 seconds to stop a swipe. The rule:

> **Ep1 uses one of 6 cold-open templates; 前30秒立冲突; no 旁白 dump.**

The opening shows a conflict, never narrates backstory. Exposition is paid out
later through action, not front-loaded as voice-over.

## The 6 cold-open templates

| # | template       | the hook it lands in <30s                                      |
|---|----------------|---------------------------------------------------------------|
| 1 | 危机临头       | drop the hero mid-danger; survive first, explain never        |
| 2 | 当众受辱       | open on a public humiliation — the 压抑 that the series repays |
| 3 | 身份反差       | show the gap between how they're treated and who they are     |
| 4 | 倒计时         | a clock/threat is already running as we cut in                |
| 5 | 强敌压境       | the antagonist's power is shown first, hero is outmatched     |
| 6 | 反常一幕       | one wrong/uncanny detail that demands an explanation          |

## Rules the brain enforces
- Ep1's **first shot** is the cold-open beat, tagged with its template id.
- The first 30s budget (`hook_30s`) carries a *conflict*, filmable, no V.O. dump.
  An opening V.O. that merely explains backstory fails SHOW-DON'T-TELL.
- The cold open plants the series' first 压抑 setup whenever the template is
  当众受辱 / 身份反差 / 强敌压境 — so the first payoff has something to cite.
- Template choice is deterministic in V1: derived from `主爽点类型`
  (身份碾压→身份反差, 打脸复仇→当众受辱, 逆袭翻盘→强敌压境, 情感爆发→反常一幕,
  悬念揭秘→反常一幕; danger-led seeds fall back to 危机临头).

## Where the LLM brain plugs in
V1 selects a template and emits a filmable cold-open shot. A future LLM brain may
author a more original opening but must still pick one of the 6 templates, place
it as ep1's first shot, and keep the first 30s V.O.-dump-free — checked by the
SHOW-DON'T-TELL gate, which is genre-blind.
