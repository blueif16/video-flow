# Hook / cliffhanger design (distilled from 0xsline/short-drama, MIT)

爽剧 retention is a chain of unresolved questions. The rule:

> **Every episode except the finale ends on a cliffhanger.**

A cliffhanger is a *shown* beat that opens a new question or reverses an
expectation right as the episode cuts to black — never a narrated tease.

## Cliffhanger types the brain rotates through
1. **反转** — a fact flips (ally is the planter, the dead are alive).
2. **危机** — a concrete threat lands with no resolution shown (blade at throat, fuse lit).
3. **新敌现身** — a higher-tier villain steps into frame for the first time.
4. **悬念升级** — the episode's planted question deepens instead of resolving.
5. **代价揭示** — the cost of the just-won 爽点 is revealed (victory has a price).

## Rules the brain enforces
- The **last shot** of every non-finale episode is tagged as the cliffhanger beat
  and gets a held, charged composition (push-in / freeze / hard cut).
- The cliffhanger must be filmable (passes SHOW-DON'T-TELL) — no V.O. "what will
  happen next?".
- The **finale episode has NO trailing cliffhanger**; it resolves the top 爽点 and
  unmasks the hidden villain instead.
- A cliffhanger may *open* a question that a later episode's 压抑/释放 pays off,
  but it does not itself need a prior setup (it is a question, not a payoff).

## Where the LLM brain plugs in
V1 picks the cliffhanger type deterministically by episode stage. A future LLM
brain writes the specific reversal but must still place exactly one cliffhanger
beat as the final shot of every non-finale episode — the placement rule is
genre-blind and checked structurally.
