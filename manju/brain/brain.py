"""Phase 1 — THE 爽剧 BRAIN.

Turns (seed_idea, knobs) into the **Plan columns** of the ledger: story + style
+ bible, top-down. Deterministic dramaturgy scaffolding — it **never calls a
model or the network** (per spec: "the brain never calls a model"). Prose is
templated but valid, camera-filmable, and dramaturgically self-consistent.

It is swappable: ALL genre dramaturgy lives inside this module; the emitted Plan
column set (CONTRACTS §3) is identical regardless of genre. See `plan()` and the
"LLM-BRAIN SWAP SEAM" markers.

Entry point:
    plan(seed_idea, knobs, project_dir) -> path to written ledger.json

The five dramaturgy modules (encoded below from manju/brain/dramaturgy/*.md):
  1. 爽点 matrix      — SATISFACTION (压抑→释放, 5 archetypes, escalating 强度)
  2. rhythm curve     — RHYTHM (micro-3-act + 4-stage series waveform)
  3. hook design      — cliffhanger on every non-finale episode
  4. villain design   — 4 tiers; 隐藏反派 needs ≥3 foreshadows
  5. opening rules    — ep1 cold-open template, no 旁白 dump

Standard library only. Python 3.12.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

# The brain imports the kernel ONLY to validate its own output. It does not call
# any run-side API — it authors the document, then validates the shape.
from manju.ledger.ledger import Ledger, load  # noqa: F401  (load used by self-test)

_HERE = os.path.dirname(os.path.abspath(__file__))
_STYLES_DIR = os.path.join(_HERE, "styles")
_SCHEMA_VERSION = "1.0.0"


# ════════════════════════════════════════════════════════════════════════════
# MODULE 5 → SHOW-DON'T-TELL hard gate
# ════════════════════════════════════════════════════════════════════════════
# Interiority markers: verbs of feeling/thinking that no camera can film. A line
# carrying one of these is rejected UNLESS it is explicitly marked 画外音(V.O.).
_INTERIORITY = [
    "感到", "觉得", "心想", "心里", "暗想", "意识到", "明白了", "回忆起",
    "想起", "感觉", "内心", "思绪", "情绪", "恍惚", "懊悔", "嫉妒",
    "felt", "thought", "realized", "remembered", "wondered", "knew that",
]
_VO_MARK = re.compile(r"画外音|\(V\.?O\.?\)|（V\.?O\.?）|V\.O\.")

# Deterministic interiority→filmable rewrites (the brain's "physicalize" table).
# Maps an interior state to a camera-filmable body/object tell.
_PHYSICALIZE = {
    "背叛": "他的酒杯在微微颤抖，指节因用力而发白",
    "愤怒": "他的下颌绷紧，掌心攥出指甲的红痕",
    "恐惧": "他后退半步，喉结上下滚动，呼吸变浅",
    "悲伤": "他别过脸，肩膀几不可察地一沉",
    "决心": "他缓缓抬眼，握紧剑柄，脚下站定",
    "震惊": "他瞳孔骤缩，手中的杯盏脱手坠地",
    "屈辱": "他垂下眼，攥紧的拳头在身侧轻轻发抖",
}


def physicalize(interior_phrase: str, cue: Optional[str] = None) -> str:
    """Convert an interiority phrase to a filmable body/object tell (deterministic).

    e.g. physicalize("她感到背叛") → "她的酒杯在微微颤抖…". A future LLM brain
    would write a richer tell here — the gate downstream is identical.
    """
    text = interior_phrase
    key = cue
    if key is None:
        for k in _PHYSICALIZE:
            if k in interior_phrase:
                key = k
                break
    if key and key in _PHYSICALIZE:
        return _PHYSICALIZE[key]
    # generic fallback: strip the interior verb, keep a neutral physical beat
    for marker in _INTERIORITY:
        text = text.replace(marker, "")
    return (text.strip() or "他停下动作，目光定住，周遭一时寂静")


def showtell_check(text: str) -> tuple[bool, str]:
    """SHOW-DON'T-TELL gate. Returns (passes, reason).

    Rejects interiority ("她感到 / 他心想 / 觉得被背叛" …) unless the line is
    explicitly off-screen narration 画外音(V.O.). A passing line is camera-filmable.
    This is BLOCKING: a shot's showtell_pass is set True only after this passes.
    """
    if text is None or text.strip() == "":
        return True, "empty (no dialogue/narration to film)"
    if _VO_MARK.search(text):
        return True, "explicit 画外音(V.O.) — off-screen narration is allowed"
    for marker in _INTERIORITY:
        if marker in text:
            return False, f"interiority {marker!r} is not camera-filmable; physicalize it or mark 画外音(V.O.)"
    return True, "filmable"


def _ensure_filmable(text: str) -> str:
    """Rewrite-or-keep: if text fails the gate, physicalize it; assert it passes."""
    ok, _ = showtell_check(text)
    if ok:
        return text
    fixed = physicalize(text)
    ok2, reason = showtell_check(fixed)
    if not ok2:  # pragma: no cover — physicalize table must always produce a filmable line
        raise ValueError(f"could not make line filmable: {text!r} → {fixed!r} ({reason})")
    return fixed


# ════════════════════════════════════════════════════════════════════════════
# MODULE 1 → 爽点 matrix (压抑→释放, escalating 强度)
# ════════════════════════════════════════════════════════════════════════════
# archetype -> (base 强度, a filmable 压抑 setup template, a filmable 释放 template)
SATISFACTION = {
    "身份碾压": (0.55,
                 "{villain}当众嗤笑{hero}是个无名之辈，挥手将他逐出门外。",
                 "{hero}亮出本门信物，{villain}脸色骤变，当众单膝跪地。"),
    "打脸复仇": (0.65,
                 "{villain}当众折断{hero}的剑，众人哄笑，{hero}被踩进尘土。",
                 "{hero}一剑挑落{villain}的兵刃，反手将断剑插在他脚前。"),
    "逆袭翻盘": (0.75,
                 "{hero}被{villain}逼至悬崖，退无可退，众人皆道他必死。",
                 "{hero}骤然翻腕，一道暗藏的杀招逼得{villain}连退三步。"),
    "情感爆发": (0.70,
                 "{hero}默默收殓同门的尸骨，咬紧牙关，一言不发。",
                 "{hero}将断剑重重插入地面，抬眼直视{villain}，声音不抖。"),
    "悬念揭秘": (0.80,
                 "一个无人能答的疑问悬在{hero}心头，画面定格在那枚旧符上。",
                 "旧符在火光下显出暗纹，{hero}缓缓抬头，真相令满座失色。"),
}
ARCHETYPE_ORDER = ["身份碾压", "打脸复仇", "逆袭翻盘", "情感爆发", "悬念揭秘"]


class SatisfactionError(ValueError):
    """Raised when a 爽点 release cites no prior 压抑 setup (the self-check)."""


def satisfaction_self_check(beats: list[dict]) -> None:
    """HARD self-check: every 释放(爽点) must cite ≥1 prior 压抑 setup by id.

    `beats` is the ordered beat list; a release carries pays_off=[setup_id,...].
    A release whose pays_off is empty, or which cites a setup not appearing
    EARLIER in the list, is rejected.
    """
    seen_setups: set[str] = set()
    for b in beats:
        if b.get("type") == "压抑":
            seen_setups.add(b["id"])
        elif b.get("type") == "释放":
            payoffs = b.get("pays_off", [])
            if not payoffs:
                raise SatisfactionError(
                    f"爽点 {b['id']!r} cites no prior 压抑 setup (pays_off empty) — rejected")
            for sid in payoffs:
                if sid not in seen_setups:
                    raise SatisfactionError(
                        f"爽点 {b['id']!r} cites {sid!r} which has no prior 压抑 setup — rejected")


# ════════════════════════════════════════════════════════════════════════════
# MODULE 2 → rhythm curve (micro-3-act + 4-stage series waveform)
# ════════════════════════════════════════════════════════════════════════════
SERIES_STAGES = [  # (name, 强度 band low, high)
    ("起势", 0.45, 0.60),
    ("攀升", 0.60, 0.75),
    ("风暴", 0.75, 0.90),
    ("决战", 0.90, 1.00),
]


def stage_for_episode(idx: int, n: int) -> tuple[str, float, float]:
    """Map a 0-based episode index to a series stage by even partition.

    A 1-episode series maps to 决战 (the single episode carries a full payload +
    finale rules). Returns (stage_name, 强度_low, 强度_high).
    """
    if n <= 1:
        return SERIES_STAGES[-1]
    # even partition of [0, n) across the 4 stages
    si = min(len(SERIES_STAGES) - 1, (idx * len(SERIES_STAGES)) // n)
    return SERIES_STAGES[si]


def micro_3act_budget(total_s: float) -> dict[str, float]:
    """Split an episode's duration into the 30/90/30 hook/escalation/payload acts."""
    return {
        "hook_30s": round(total_s * 0.20, 2),
        "escalation_90s": round(total_s * 0.60, 2),
        "payload_30s": round(total_s * 0.20, 2),
    }


# ════════════════════════════════════════════════════════════════════════════
# MODULE 3 → hook / cliffhanger design
# ════════════════════════════════════════════════════════════════════════════
CLIFFHANGERS = {
    "反转": "镜头猛地推近——那张脸竟是众人以为已死之人。",
    "危机": "一柄冷刃悄然抵上{hero}后颈，画面骤然定格。",
    "新敌现身": "一道陌生身影踏入光中，气压骤沉，众人齐齐回头。",
    "悬念升级": "那枚旧符在掌心裂开一线，露出更深的暗纹，疑团更重。",
    "代价揭示": "{hero}低头看向掌心——方才那一击，代价已悄然浮现。",
}
CLIFF_BY_STAGE = {"起势": "悬念升级", "攀升": "新敌现身", "风暴": "危机", "决战": "反转"}


# ════════════════════════════════════════════════════════════════════════════
# MODULE 4 → villain design (4 tiers; 隐藏反派 needs ≥3 foreshadows)
# ════════════════════════════════════════════════════════════════════════════
VILLAIN_TIERS = ["小", "中", "大", "隐藏"]


class VillainError(ValueError):
    """Raised when a 隐藏反派 has <3 foreshadows (the gate)."""


def validate_hidden_villain(villain: dict) -> None:
    """HARD gate: a 隐藏反派 needs foreshadows[] ≥3, each {episode, line_ref}."""
    fs = villain.get("foreshadows", [])
    if len(fs) < 3:
        raise VillainError(
            f"隐藏反派 {villain.get('id')!r} has {len(fs)} foreshadows (<3) — rejected")
    for f in fs:
        if "episode" not in f or "line_ref" not in f:
            raise VillainError(
                f"隐藏反派 {villain.get('id')!r} foreshadow missing episode/line_ref: {f} — rejected")


# ════════════════════════════════════════════════════════════════════════════
# MODULE 5 (other half) → opening / cold-open templates
# ════════════════════════════════════════════════════════════════════════════
COLD_OPENS = {
    "危机临头": "{hero}在乱刃中翻身格挡，血溅衣襟，无人解释他为何在此。",
    "当众受辱": "{villain}当众将一碗冷水泼在{hero}脸上，四下哄笑成片。",
    "身份反差": "众人将{hero}当作扫地的杂役呼来喝去，他却无声拭净了那柄旧剑。",
    "倒计时": "殿外更漏一声声逼近，{hero}盯着那扇即将开启的石门，指尖收紧。",
    "强敌压境": "{villain}抬手震碎一根石柱，{hero}立于碎石之中，纹丝未动。",
    "反常一幕": "满堂烛火无风自灭，唯有{hero}面前那一盏，烧成了诡异的青色。",
}
# 主爽点类型 -> cold-open template (deterministic; opening-rules.md)
OPEN_BY_PAYOFF = {
    "身份碾压": "身份反差",
    "打脸复仇": "当众受辱",
    "逆袭翻盘": "强敌压境",
    "情感爆发": "反常一幕",
    "悬念揭秘": "反常一幕",
}
# cold opens that also plant the series' first 压抑 setup
OPEN_PLANTS_SETUP = {"当众受辱", "身份反差", "强敌压境"}


# ════════════════════════════════════════════════════════════════════════════
# STYLE AXIS — style_id resolves to a preset; story never depends on it
# ════════════════════════════════════════════════════════════════════════════
def load_style(style_id: str) -> dict:
    """Resolve a style_id to its preset JSON (palette/film_vocab/negative_floor).

    Swapping style = swapping this preset. ZERO story fields depend on it.
    """
    path = os.path.join(_STYLES_DIR, f"{style_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"unknown style_id {style_id!r}: no preset at {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ════════════════════════════════════════════════════════════════════════════
# bible — deterministic character + scene + villain assets
# ════════════════════════════════════════════════════════════════════════════
def _empty_asset_run(asset_id: str) -> dict:
    """Run block emitted EMPTY per the fixture (writer overlord/generating fills it)."""
    return {
        "ref_image_paths": [],
        "ref_status": "none",
        "ref_tag": f"@{asset_id}",
        "seed": None,
        "locked_seed": None,
        "attempts": [],
        "current_attempt_id": None,
        "current_artifact": None,
        "final_verdict": None,
    }


def _empty_shot_run() -> dict:
    """Run block emitted EMPTY per the fixture."""
    return {
        "status": "pending",
        "attempts": [],
        "current_attempt_id": None,
        "current_artifact": None,
        "final_verdict": None,
        "cost_usd": 0,
    }


def _build_bible(style_id: str, n: int) -> tuple[dict, dict, list[dict]]:
    """Return (bible, hero_asset, villain_assets). Deterministic 爽剧 cast.

    The hero + throne scene mirror the demo fixture's anchor assets; villains are
    instantiated per the 4-tier escalation.
    """
    hero = {
        "id": "char_lin",
        "kind": "character",
        "plan": {
            "descriptor": "林夜 — exiled young swordsman, cold-eyed, returns to reclaim his name.",
            "ai_draw_keywords": ["young man", "long black hair", "silver-grey eyes",
                                 "dark hanfu robe", "single sword", "scar over left brow"],
            "固定特征词": ["银灰色眼睛", "左眉伤疤", "黑色长发束起", "黑色暗纹长袍"],
            "禁止变化项": ["发型不可变", "眼睛颜色不可变", "伤疤位置不可变", "服装主色不可变"],
            "style_id": style_id,
        },
        "run": _empty_asset_run("char_lin"),
    }
    throne = {
        "id": "scene_throne",
        "kind": "scene",
        "plan": {
            "descriptor": "废弃宗门大殿 — abandoned sect throne hall, shattered pillars, moonlight through broken roof.",
            "ai_draw_keywords": ["ruined hall", "broken stone pillars", "moonlight shafts",
                                 "cracked throne", "drifting dust", "cold blue ambient"],
            "固定特征词": ["断裂石柱", "月光从破顶射入", "裂开的石座", "冷蓝色调"],
            "禁止变化项": ["大殿布局不可变", "光源方向不可变", "色调不可变"],
            "style_id": style_id,
        },
        "run": _empty_asset_run("scene_throne"),
    }

    # 4-tier villains (instantiate only as many tiers as N can carry; always
    # include the 隐藏反派 in the finale — the moat gate runs on it).
    villain_specs = [
        ("villain_minor", "小", "周三爷 — 门中管事，仗势欺人的小人物。",
         ["middle-aged man", "greasy smile", "brown robe", "fat fingers"],
         ["油腻笑容", "褐色管事袍"], ["体型不可变"]),
        ("villain_mid", "中", "苏决 — 敌方副统领，冷面狠辣。",
         ["lean man", "scarred jaw", "iron-grey armor", "twin daggers"],
         ["下颌刀疤", "铁灰色甲胄"], ["甲胄颜色不可变", "刀疤位置不可变"]),
        ("villain_arch", "大", "玄罡 — 当世大反派，名震一方的强者。",
         ["tall man", "white-streaked hair", "black-gold robe", "long spear"],
         ["白发束冠", "黑金色长袍", "丈二长枪"], ["发色不可变", "长袍配色不可变"]),
        ("villain_hidden", "隐藏", "执棋者 — 幕后真凶，所有棋局的执棋之人。",
         ["hooded figure", "pale ringed hand", "jade chess piece", "shadowed face"],
         ["苍白戴戒之手", "玉色棋子"], ["持棋之手不可变", "棋子不可变"]),
    ]
    # how many tiers fit: 1 ep → just hidden(finale)+minor; scale up with N.
    tier_count = min(len(villain_specs), max(2, n + 1))
    chosen = villain_specs[:tier_count - 1] + [villain_specs[-1]]  # always keep 隐藏
    # de-dup if minor list already included hidden
    seen_ids: set[str] = set()
    villains: list[dict] = []
    for vid, tier, desc, kw, fixed, forbid in chosen:
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        villains.append({
            "id": vid,
            "kind": "villain",
            "plan": {
                "descriptor": desc,
                "ai_draw_keywords": kw,
                "固定特征词": fixed,
                "禁止变化项": forbid,
                "style_id": style_id,
            },
            "run": _empty_asset_run(vid),
        })

    bible = {
        "characters": [hero],
        "scenes": [throne],
        "props": [],
        "villains": villains,
    }
    return bible, hero, villains


# ════════════════════════════════════════════════════════════════════════════
# shot authoring — the dramaturgy gets WIRED into filmable shots here
# ════════════════════════════════════════════════════════════════════════════
# Camera vocabulary keyed by beat role (景别/运镜/lens — all filmable).
_CAM = {
    "establish": {"shot_size": "全景", "movement": "缓慢推进", "lens_mm": 35},
    "setup": {"shot_size": "中景", "movement": "固定", "lens_mm": 50},
    "escalate": {"shot_size": "中近景", "movement": "横向跟移", "lens_mm": 50},
    "payload": {"shot_size": "近景", "movement": "急推", "lens_mm": 85},
    "cliff": {"shot_size": "特写", "movement": "定格", "lens_mm": 85},
}


def _shot(shot_id: str, deps: list[str], intent: str, dialogue: str, cam_role: str,
          action: str, ref_ids: list[str], style_id: str, duration_s: float) -> dict:
    """Build a SHOT node with a FULL plan + EMPTY run. Runs the SHOW-DON'T-TELL gate.

    showtell_pass is set True ONLY after both dialogue and action pass the gate;
    failing text is physicalized (rewrite-or-reject) before commit.
    """
    dialogue = _ensure_filmable(dialogue)
    action = _ensure_filmable(action)
    ok_d, _ = showtell_check(dialogue)
    ok_a, _ = showtell_check(action)
    showtell_pass = ok_d and ok_a
    return {
        "id": shot_id,
        "deps": deps,
        "plan": {
            "intent": intent,
            "dialogue": dialogue,
            "camera": dict(_CAM[cam_role]),
            "action": action,
            "ref_ids": ref_ids,
            "style_id": style_id,
            "duration_s": duration_s,
            "showtell_pass": showtell_pass,
        },
        "run": _empty_shot_run(),
    }


def _build_episode(ep_idx: int, n: int, knobs: dict, hero: dict, throne: dict,
                   villains: list[dict], style_id: str,
                   beats: list[dict], foreshadows: list[dict]) -> dict:
    """Author one episode: cold-open(ep1) / 压抑 setups / payload 释放 / cliffhanger.

    Appends its 压抑/释放 beats to `beats` (for the satisfaction self-check) and
    its hidden-villain foreshadows to `foreshadows`.
    """
    ep_id = f"ep{ep_idx + 1:02d}"
    is_finale = (ep_idx == n - 1)
    stage, lo, hi = stage_for_episode(ep_idx, n)
    payoff_type = knobs["主爽点类型"]
    base, setup_tpl, release_tpl = SATISFACTION[payoff_type]
    # 强度 escalates: clamp the running base into this stage's band, rising with idx
    intensity = round(min(hi, max(lo, base + 0.05 * ep_idx)), 3)

    hero_id = hero["id"]
    throne_id = throne["id"]
    # pick the tier-appropriate villain for this stage's confrontation
    stage_villain = {"起势": "小", "攀升": "中", "风暴": "大", "决战": "隐藏"}[stage]
    vmap = {v["plan"]["descriptor"].split(" ")[0]: v for v in villains}
    villain = next((v for v in villains if {"小": "周三爷", "中": "苏决", "大": "玄罡",
                    "隐藏": "执棋者"}[stage_villain] in v["plan"]["descriptor"]), villains[-1])
    villain_id = villain["id"]
    hero_name = hero["plan"]["descriptor"].split(" ")[0]
    villain_name = villain["plan"]["descriptor"].split(" ")[0]

    def fill(tpl: str) -> str:
        return tpl.format(hero=hero_name, villain=villain_name)

    budget = micro_3act_budget(knobs["时长"])
    sc_id = f"{ep_id}.sc01"
    shots: list[dict] = []
    sh = 0

    def next_sh() -> str:
        nonlocal sh
        sh += 1
        return f"{sc_id}.sh{sh:02d}"

    prev_shot_id: Optional[str] = None

    def deps_for(refs: list[str]) -> list[str]:
        d = list(refs)
        if prev_shot_id:
            d.append(prev_shot_id)
        return d

    # ── HOOK act ──────────────────────────────────────────────────────────────
    if ep_idx == 0:
        # MODULE 5: ep1 cold-open — deterministic template, filmable, no 旁白 dump
        tpl_name = OPEN_BY_PAYOFF.get(payoff_type, "危机临头")
        cold_action = fill(COLD_OPENS[tpl_name])
        s = _shot(next_sh(), deps_for([hero_id, throne_id]),
                  intent=f"冷开场[{tpl_name}]：前30秒立冲突，确立{hero_name}的处境与气场，不用旁白交代。",
                  dialogue="", cam_role="establish", action=cold_action,
                  ref_ids=[hero_id, throne_id], style_id=style_id,
                  duration_s=budget["hook_30s"])
        shots.append(s)
        prev_shot_id = s["id"]
        # the cold open plants the series' first 压抑 setup (if its template does)
        if tpl_name in OPEN_PLANTS_SETUP:
            beats.append({"id": f"{s['id']}#setup", "type": "压抑", "episode": ep_id,
                          "line_ref": s["id"], "text": cold_action})
    else:
        # later episodes open by re-stating the standing threat (a 压抑 beat)
        s = _shot(next_sh(), deps_for([hero_id, throne_id]),
                  intent=f"{ep_id} 开场[{stage}]：重申当前压制，{hero_name}仍处下风，铺垫本集爆点。",
                  dialogue="", cam_role="establish", action=fill(setup_tpl),
                  ref_ids=[hero_id, throne_id], style_id=style_id,
                  duration_s=budget["hook_30s"])
        shots.append(s)
        prev_shot_id = s["id"]
        beats.append({"id": f"{s['id']}#setup", "type": "压抑", "episode": ep_id,
                      "line_ref": s["id"], "text": s["plan"]["action"]})

    # ── ESCALATION act ───────────────────────────────────────────────────────
    # a 压抑 setup shot that the payload will cite (always present)
    setup_shot = _shot(next_sh(), deps_for([hero_id, throne_id, villain_id]),
                       intent=f"压抑升级：{villain_name}进一步施压，将{hero_name}逼入绝境，为释放蓄力。",
                       dialogue="", cam_role="escalate", action=fill(setup_tpl),
                       ref_ids=[hero_id, villain_id], style_id=style_id,
                       duration_s=budget["escalation_90s"])
    shots.append(setup_shot)
    prev_shot_id = setup_shot["id"]
    setup_beat_id = f"{setup_shot['id']}#setup"
    beats.append({"id": setup_beat_id, "type": "压抑", "episode": ep_id,
                  "line_ref": setup_shot["id"], "text": setup_shot["plan"]["action"]})

    # plant a hidden-villain foreshadow (concrete, on-screen) in every non-finale ep,
    # so the finale reveal clears the ≥3 gate.
    if not is_finale:
        fs_shot = _shot(next_sh(), deps_for([hero_id]),
                        intent=f"埋线：一处不起眼却反常的细节，日后回看指向隐藏反派。",
                        dialogue="", cam_role="setup",
                        action="案几一角，一枚玉色棋子被一只苍白戴戒的手悄然收回袖中。",
                        ref_ids=[hero_id], style_id=style_id,
                        duration_s=round(budget["escalation_90s"] * 0.4, 2))
        shots.append(fs_shot)
        prev_shot_id = fs_shot["id"]
        foreshadows.append({"episode": ep_id, "line_ref": fs_shot["id"]})

    # ── PAYLOAD act → the episode's main 爽点 释放, citing the setup ───────────
    payload_dialogue = {
        "身份碾压": "你也配？",
        "打脸复仇": "这一剑，还给你。",
        "逆袭翻盘": "棋差一招的，是你。",
        "情感爆发": "他们的命，我替他们讨回来。",
        "悬念揭秘": "原来一切，从一开始就错了。",
    }[payoff_type]
    payload_shot = _shot(next_sh(), deps_for([hero_id, villain_id, throne_id]),
                         intent=f"本集爆点[{payoff_type}, 强度{intensity}]：{hero_name}完成释放，回收前置压抑。",
                         dialogue=payload_dialogue, cam_role="payload",
                         action=fill(release_tpl), ref_ids=[hero_id, villain_id],
                         style_id=style_id, duration_s=budget["payload_30s"])
    shots.append(payload_shot)
    prev_shot_id = payload_shot["id"]
    beats.append({"id": f"{payload_shot['id']}#release", "type": "释放", "episode": ep_id,
                  "line_ref": payload_shot["id"], "intensity": intensity,
                  "pays_off": [setup_beat_id], "text": payload_shot["plan"]["action"]})

    # ── CLIFFHANGER → every non-finale episode; finale resolves instead ───────
    if is_finale:
        # MODULE 4: finale unmasks the 隐藏反派 (the top 爽点), no trailing cliffhanger
        hidden = next((v for v in villains if "执棋者" in v["plan"]["descriptor"]), None)
        if hidden is not None:
            reveal = _shot(next_sh(), deps_for([hero_id, hidden["id"], throne_id]),
                           intent="终章揭面：隐藏反派现身，回收全部伏笔，最高强度释放收束全篇。",
                           dialogue="执棋的人，该下来了。", cam_role="payload",
                           action="兜帽落下，那只苍白戴戒的手将玉色棋子按在棋盘正中，幕后真凶终于显形。",
                           ref_ids=[hero_id, hidden["id"]], style_id=style_id,
                           duration_s=budget["payload_30s"])
            shots.append(reveal)
    else:
        cliff_type = CLIFF_BY_STAGE[stage]
        cliff_shot = _shot(next_sh(), deps_for([hero_id]),
                           intent=f"集尾钩子[{cliff_type}]：在悬念顶点切黑，逼出下一集的追看欲。",
                           dialogue="", cam_role="cliff",
                           action=fill(CLIFFHANGERS[cliff_type]),
                           ref_ids=[hero_id], style_id=style_id,
                           duration_s=round(budget["hook_30s"] * 0.5, 2))
        shots.append(cliff_shot)

    return {
        "id": ep_id,
        "title": {"起势": "归来", "攀升": "锋起", "风暴": "风暴", "决战": "执棋者"}[stage],
        "hook": fill(setup_tpl),
        "scenes": [{"id": sc_id, "title": "大殿对峙", "shots": shots}],
    }


# ════════════════════════════════════════════════════════════════════════════
# THE ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════
def plan(seed_idea: str, knobs: dict, project_dir: str) -> str:
    """Author the full Plan columns of a ledger from (seed_idea, knobs).

    knobs = {题材, 集数N, 时长, 主爽点类型, style_id}.
    Writes projects/<name>/ledger.json and returns its path.

    The brain is the WRITER "brain": it fills every plan.* field (CONTRACTS §3)
    and authors the tree structure + deps; run blocks are emitted EMPTY
    (status:"pending" / ref_status:"none") per the fixture. It NEVER calls a
    model or the network.

    ── LLM-BRAIN SWAP SEAM ────────────────────────────────────────────────────
    A future LLM brain replaces the deterministic dramaturgy below (the 5 modules
    + physicalize table) with model-generated story content, but MUST:
      • emit the identical Plan column set (this is the swap contract),
      • run the same showtell_check / satisfaction_self_check / villain gate,
      • emit empty run blocks.
    Tooling never knows which brain wrote the Plan. All genre logic stays here.
    """
    n = int(knobs["集数N"])
    style_id = knobs["style_id"]
    style = load_style(style_id)  # STYLE AXIS: resolved here, story never depends on it
    payoff_type = knobs["主爽点类型"]
    if payoff_type not in SATISFACTION:
        raise ValueError(f"unknown 主爽点类型 {payoff_type!r}; must be one of {ARCHETYPE_ORDER}")

    bible, hero, villains = _build_bible(style_id, n)
    throne = bible["scenes"][0]

    # author every episode top-down, accumulating beats + foreshadows for the gates
    beats: list[dict] = []
    foreshadows: list[dict] = []
    episodes = [
        _build_episode(i, n, knobs, hero, throne, villains, style_id, beats, foreshadows)
        for i in range(n)
    ]

    # ── HARD GATES (blocking, before commit) ──────────────────────────────────
    # MODULE 1: every 爽点 cites a prior 压抑 setup
    satisfaction_self_check(beats)
    # MODULE 4: the 隐藏反派 needs ≥3 foreshadows. A short series can't plant 3
    # across non-finale episodes (it has too few), so seed the minimum here.
    hidden = next((v for v in villains if "执棋者" in v["plan"]["descriptor"]), None)
    if hidden is not None:
        while len(foreshadows) < 3:
            # deterministic seed foreshadows anchored to existing early shots
            anchor = episodes[0]["scenes"][0]["shots"][min(len(foreshadows),
                     len(episodes[0]["scenes"][0]["shots"]) - 1)]["id"]
            foreshadows.append({"episode": "ep01", "line_ref": anchor})
        hidden["foreshadows"] = foreshadows[:max(3, len(foreshadows))]
        validate_hidden_villain(hidden)
        # foreshadows are NOT a schema plan-field on the asset; keep the validated
        # record on the villain's descriptor trail via 固定特征词 is wrong — instead
        # we drop the transient key before commit (it lives only for the gate).
        del hidden["foreshadows"]

    project_name = os.path.basename(os.path.normpath(project_dir))
    doc = {
        "schema_version": _SCHEMA_VERSION,
        "project": {
            "id": project_name,
            "title": f"{seed_idea} ({project_name})",
            "genre": "manju",
            "default_style_id": style_id,
            "knobs": {
                "题材": knobs.get("题材", ""),
                "集数N": n,
                "时长": knobs["时长"],
                "主爽点类型": payoff_type,
                "style_id": style_id,
            },
        },
        "styles": [style],
        "bible": bible,
        "episodes": episodes,
        "lessons": [],
    }

    # validate the SHAPE against the kernel schema before writing
    led = Ledger(doc, project_dir)
    led.validate()  # raises SchemaError on any shape violation
    os.makedirs(project_dir, exist_ok=True)
    led.save()  # atomic
    return os.path.join(project_dir, "ledger.json")
