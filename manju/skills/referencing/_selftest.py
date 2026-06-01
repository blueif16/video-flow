"""Self-test for referencing (Phase 2). Run: python -m manju.skills.referencing._selftest

Copies projects/demo -> projects/_scratch_ref (gitignored), drafts refs for
char_lin + scene_throne, and asserts the moat invariants + idempotency.
"""
from __future__ import annotations

import os
import shutil

from manju.ledger import load
from manju.skills.referencing.referencer import draft_refs, drift_inputs, ref_tags_for

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DEMO = os.path.join(_REPO, "projects", "demo")
_SCRATCH = os.path.join(_REPO, "projects", "_scratch_ref")


def _setup() -> None:
    if os.path.exists(_SCRATCH):
        shutil.rmtree(_SCRATCH)
    shutil.copytree(_DEMO, _SCRATCH)


def _png_ok(path: str) -> bool:
    # PNG magic number 0x89504E47
    with open(path, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def main() -> None:
    _setup()

    led = load(_SCRATCH)
    res = draft_refs(led, _SCRATCH)
    assert set(res) == {"char_lin", "scene_throne"}, res

    # reload from disk to confirm the writes persisted atomically
    led = load(_SCRATCH)
    for aid, folder in (("char_lin", "char"), ("scene_throne", "scene")):
        run = led.node(aid)["run"]
        assert run["ref_status"] == "drafting", (aid, run["ref_status"])
        assert run["ref_image_paths"], (aid, "no ref paths")
        assert run["ref_tag"] == f"@{aid}", run["ref_tag"]
        assert isinstance(run["locked_seed"], int), run["locked_seed"]
        assert len(run["attempts"]) >= 1, run["attempts"]
        for p in run["ref_image_paths"]:
            assert os.path.join("ref_sheet", folder, "00") in p, p
            assert os.path.exists(p) and _png_ok(p), p
    print("PASS draft_refs: refs drafted, PNGs exist & open, run block written")

    di = drift_inputs(led, "char_lin")
    assert di["禁止变化项"] == ["发型不可变", "眼睛颜色不可变", "伤疤位置不可变", "服装主色不可变"], di
    assert di["ref_tag"] == "@char_lin"
    assert di["固定特征词"] and di["ref_image_paths"] and isinstance(di["locked_seed"], int)
    print("PASS drift_inputs:", {k: (v if k != "ref_image_paths" else f"[{len(v)} path]") for k, v in di.items()})

    tags = ref_tags_for(led, "ep01.sc01.sh01")
    assert set(tags) == {"char_lin", "scene_throne"}, tags
    assert tags["char_lin"]["ref_tag"] == "@char_lin"
    assert tags["char_lin"]["固定特征词"], tags
    # sh02 depends on a prev shot too — that dep must be skipped (assets only)
    tags2 = ref_tags_for(led, "ep01.sc01.sh02")
    assert set(tags2) == {"char_lin"}, tags2
    print("PASS ref_tags_for:", {k: v["ref_tag"] for k, v in tags.items()}, "| sh02:", list(tags2))

    # idempotency: re-run adds no duplicate attempts / files
    before = {aid: len(led.node(aid)["run"]["attempts"]) for aid in ("char_lin", "scene_throne")}
    files_before = sorted(_all_sheet_files())
    led2 = load(_SCRATCH)
    res2 = draft_refs(led2, _SCRATCH)
    assert all(r["skipped"] for r in res2.values()), res2
    led2 = load(_SCRATCH)
    after = {aid: len(led2.node(aid)["run"]["attempts"]) for aid in ("char_lin", "scene_throne")}
    files_after = sorted(_all_sheet_files())
    assert before == after, (before, after)
    assert files_before == files_after, "ref_sheet files changed on re-run"
    print("PASS idempotency: re-run skipped, attempts", before, "files", len(files_after))

    led.validate()
    print("PASS validate: ledger is schema-valid")
    print("\nALL SELF-TESTS PASSED")


def _all_sheet_files() -> list[str]:
    root = os.path.join(_SCRATCH, "ref_sheet")
    out = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            out.append(os.path.join(dp, fn))
    return out


if __name__ == "__main__":
    main()
