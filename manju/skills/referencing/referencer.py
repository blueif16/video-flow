"""referencing (Phase 2) — the MOAT: dual-anchor reference sheets.

Built BEFORE generation because consistency (drift-vs-bible) is the #1 failure.
For each bible asset we:

  1. build a DUAL-ANCHOR ref prompt — the asset's own ai_draw_keywords + 固定特征词
     + the style preset, ANCHORED against its counterpart axis (a character is
     anchored against a scene and vice-versa) so 角色 and 场景 stay mutually
     consistent;
  2. assign a deterministic locked_seed (same seed re-rolls a consistent ref);
  3. call the generating runner (through the seam) to draft ref images, and place
     them in the numbered dual-anchor source-of-truth folders
     `projects/<n>/ref_sheet/{char|scene}/NN/*.png`;
  4. write the asset run block — ref_image_paths[], ref_tag (@<asset_id>),
     locked_seed, one append_attempt per take — then set ref_status -> drafting
     (the overlord judge flips drafting -> locked).

It also exposes the overlord's drift-check inputs (`drift_inputs`) and the
downstream tag-injection data (`ref_tags_for`).

Reads:  bible.*.plan (ai_draw_keywords / 固定特征词 / 禁止变化项 / style_id), styles[].
Writes: asset run via write_run + append_attempt + set_status (writer "generating",
        then status via the overlord). Plan.* is never touched.

stdlib only. Generation is REUSED via the seam, never reimplemented.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import shutil

# ── the generating runner seam (CONTRACTS §6) ────────────────────────────────
try:
    from manju.skills.generating.runner import run_request   # real (Agent C)
except ImportError:
    from manju.skills.generating._stub import run_request    # documented mock envelope

# bible kind -> dual-anchor folder. 场景 lands in scene/, every subject (character,
# villain, prop) anchors in char/. The two folders ARE the dual anchor.
_KIND_FOLDER = {"scene": "scene"}  # default below is "char"


def _folder_for(asset: dict) -> str:
    return _KIND_FOLDER.get(asset.get("kind"), "char")


def _seed_for(asset_id: str) -> int:
    """Deterministic locked seed per asset id (stable across runs/machines)."""
    h = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()
    return int(h[:8], 16)  # 32-bit, fits a JSON integer / typical seed range


def _ref_tag(asset_id: str) -> str:
    return f"@{asset_id}"


def _style_preset(ledger, style_id: str) -> dict:
    for style in ledger.doc.get("styles", []):
        if style.get("id") == style_id:
            return style
    return {}


def _bible_assets(ledger) -> list[dict]:
    """All bible asset nodes in document order (the order that fixes each NN index)."""
    out: list[dict] = []
    bible = ledger.doc.get("bible", {})
    for bucket in ("characters", "scenes", "props", "villains"):
        out.extend(bible.get(bucket, []))
    return out


def _index_for(ledger, asset: dict) -> str:
    """Stable 2-digit NN: the asset's position among same-folder bible assets."""
    folder = _folder_for(asset)
    n = 0
    for other in _bible_assets(ledger):
        if other["id"] == asset["id"]:
            return f"{n:02d}"
        if _folder_for(other) == folder:
            n += 1
    return f"{n:02d}"


def _counter_anchor(ledger, asset: dict) -> dict | None:
    """The opposite-axis bible asset to dual-anchor against.

    For a subject (character/villain/prop) -> the first scene; for a scene -> the
    first character. None if the counterpart axis is empty.
    """
    want_scene = _folder_for(asset) != "scene"  # subjects anchor against a scene
    for other in _bible_assets(ledger):
        if other["id"] == asset["id"]:
            continue
        is_scene = _folder_for(other) == "scene"
        if is_scene == want_scene:
            return other
    return None


def _build_prompt(ledger, asset: dict) -> str:
    """Dual-anchor ref prompt: own keywords + 固定特征词 + style + counterpart anchor."""
    plan = asset["plan"]
    style = _style_preset(ledger, plan.get("style_id", ""))

    parts: list[str] = []
    desc = plan.get("descriptor")
    if desc:
        parts.append(desc)
    if plan.get("ai_draw_keywords"):
        parts.append("、".join(plan["ai_draw_keywords"]))
    # 固定特征词 = the fixed-feature words that MUST be present (the anti-drift anchor)
    if plan.get("固定特征词"):
        parts.append("固定特征：" + "、".join(plan["固定特征词"]))

    # dual-anchor: bind this asset to its opposite axis so 角色+场景 stay consistent
    anchor = _counter_anchor(ledger, asset)
    if anchor:
        ap = anchor["plan"]
        anchor_words = ap.get("固定特征词") or ap.get("ai_draw_keywords") or []
        label = "场景锚定" if _folder_for(anchor) == "scene" else "角色锚定"
        if anchor_words:
            parts.append(f"{label}（{anchor['id']}）：" + "、".join(anchor_words))

    # style preset (palette / film vocabulary) + the negative floor as positive constraints
    if style.get("descriptor"):
        parts.append(style["descriptor"])
    if style.get("film_vocabulary"):
        parts.append("、".join(style["film_vocabulary"]))
    if style.get("negative_floor"):
        parts.append("避免：" + "、".join(style["negative_floor"]))

    return " | ".join(p for p in parts if p)


def _ref_sheet_dir(project_dir: str, asset: dict, ledger) -> str:
    return os.path.join(project_dir, "ref_sheet", _folder_for(asset), _index_for(ledger, asset))


def _is_image(path: str) -> bool:
    return os.path.exists(path)


def draft_refs(ledger, project_dir: str, asset_id: str | None = None) -> dict:
    """Draft dual-anchor reference images for one asset (or every ref_status=='none').

    Returns {asset_id: {ref_image_paths, ref_tag, locked_seed, attempt_id, skipped}}.
    Idempotent: an asset whose ref_status is already past 'none' is skipped; the
    runner is skip-if-exists so re-running adds no duplicate files/attempts.
    """
    if asset_id is not None:
        targets = [ledger.node(asset_id)]
    else:
        targets = [a for a in _bible_assets(ledger)
                   if a["run"].get("ref_status", "none") == "none"]

    result: dict[str, dict] = {}
    for asset in targets:
        aid = asset["id"]
        run = asset["run"]

        # idempotency: only draft a fresh ref (none). Anything past none is left alone.
        if run.get("ref_status", "none") != "none":
            result[aid] = {
                "ref_image_paths": run.get("ref_image_paths", []),
                "ref_tag": run.get("ref_tag"),
                "locked_seed": run.get("locked_seed"),
                "skipped": True,
            }
            continue

        seed = _seed_for(aid)
        prompt = _build_prompt(ledger, asset)
        sheet_dir = _ref_sheet_dir(project_dir, asset, ledger)
        os.makedirs(sheet_dir, exist_ok=True)

        # call the runner through the seam — generation is a REUSED primitive
        request = {
            "kind": "image",
            "prompt": prompt,
            "reference_images": [],
            "seed": seed,
            "model": "mock",
            "node_id": aid,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        }
        envelope = run_request(request, project_dir)
        out_path = envelope["output_files"][0]
        data = envelope.get("data", {})
        attempt_id = data.get("attempt_id") or _seed_for(out_path)

        # place/copy the take into the numbered dual-anchor source-of-truth folder
        sheet_path = os.path.join(sheet_dir, f"{attempt_id}.png")
        if not os.path.exists(sheet_path) and os.path.exists(out_path):
            shutil.copyfile(out_path, sheet_path)

        # don't double-record the same take (idempotent re-run guard)
        existing = run.get("attempts", [])
        already = any(a.get("attempt_id") == attempt_id for a in existing)

        if not already:
            ledger.append_attempt(aid, {
                "attempt_id": attempt_id,
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "seed": seed,
                "model": envelope.get("model", "mock"),
                "prompt": prompt,
                "artifact_path": out_path,
                "thumb_path": data.get("thumb_path"),
                "verdict": None,
                "lesson_ref": None,
            })

        # write the asset run block (writer "generating") — ref_image_paths / tag / seed
        paths = list(run.get("ref_image_paths", []))
        if sheet_path not in paths:
            paths.append(sheet_path)
        ledger.write_run(
            aid, "generating",
            ref_image_paths=paths,
            ref_tag=_ref_tag(aid),
            seed=seed,
            locked_seed=seed,
        )
        # drafting -> the overlord judge will flip drafting -> (locked|rejected)
        if run.get("ref_status", "none") == "none":
            ledger.set_status(aid, "drafting", "overlord")

        result[aid] = {
            "ref_image_paths": paths,
            "ref_tag": _ref_tag(aid),
            "locked_seed": seed,
            "attempt_id": attempt_id,
            "skipped": False,
        }

    ledger.save()
    return result


def drift_inputs(ledger, asset_id: str) -> dict:
    """The overlord judge's drift-vs-bible inputs for one asset.

    禁止变化项 / 固定特征词 come from plan (BRAIN-owned, the bible truth); ref_tag /
    ref_image_paths / locked_seed come from run (what referencing drafted).
    """
    node = ledger.node(asset_id)
    plan, run = node["plan"], node["run"]
    return {
        "ref_tag": run.get("ref_tag"),
        "禁止变化项": list(plan.get("禁止变化项", [])),
        "固定特征词": list(plan.get("固定特征词", [])),
        "ref_image_paths": list(run.get("ref_image_paths", [])),
        "locked_seed": run.get("locked_seed"),
    }


def ref_tags_for(ledger, shot_id: str) -> dict:
    """For a shot, expose each referenced asset's tag + 固定特征词 so building_prompts
    can inject them into the shot prompt. Keyed by asset id; data only (we don't
    build the prompt — that's building_prompts' job)."""
    shot = ledger.node(shot_id)
    ref_ids = shot["plan"].get("ref_ids", []) or shot.get("deps", [])
    out: dict[str, dict] = {}
    for aid in ref_ids:
        try:
            node = ledger.node(aid)
        except KeyError:
            continue
        if node.get("kind") not in ("character", "scene", "prop", "villain"):
            continue  # skip prev-shot deps; assets only
        out[aid] = {
            "ref_tag": node["run"].get("ref_tag") or _ref_tag(aid),
            "固定特征词": list(node["plan"].get("固定特征词", [])),
        }
    return out
