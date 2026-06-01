"""The ledger kernel — the one shared library every layer imports.

Owns the ledger.json document: load/atomic-save, node lookup, writer-tag
ownership enforcement (plan=brain / run=overlord|generating, no overlap),
the status state-machine, resume/frontier logic, append-only 抽卡 history,
the retrievable lesson store, and content-addressed artifact paths.

Standard library only. Pure-Python schema validation lives here; the JSON
Schema in schema/ledger.schema.json is the spec-of-record.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Any, Iterable, Optional

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema", "ledger.schema.json")
_LEDGER_FILE = "ledger.json"

# ── writer-tag ownership (the core invariant) ─────────────────────────────────
PLAN_WRITERS = {"brain"}
RUN_WRITERS = {"overlord", "generating"}

ASSET_PLAN_FIELDS = {"descriptor", "ai_draw_keywords", "固定特征词", "禁止变化项", "style_id"}
ASSET_RUN_FIELDS = {"ref_image_paths", "ref_status", "ref_tag", "seed", "locked_seed",
                    "attempts", "current_attempt_id", "current_artifact", "final_verdict"}
SHOT_PLAN_FIELDS = {"intent", "dialogue", "camera", "action", "ref_ids", "style_id",
                    "duration_s", "showtell_pass"}
SHOT_RUN_FIELDS = {"status", "attempts", "current_attempt_id", "current_artifact",
                   "final_verdict", "cost_usd"}

# ── status state-machine (canonical) ──────────────────────────────────────────
STATUSES = {"pending", "generating", "landed", "judging", "approved",
            "needs_regen", "paused", "blocked_on_ref", "skipped"}
# legal transitions: from -> {to}.  approved->pending is plan-edit only (write_plan).
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"generating", "paused", "skipped"},
    "generating": {"landed", "paused", "pending"},
    "landed": {"judging", "paused"},
    "judging": {"approved", "needs_regen", "paused", "blocked_on_ref", "skipped"},
    "needs_regen": {"generating", "paused"},
    "blocked_on_ref": {"pending", "paused"},
    "paused": {"pending"},
    "approved": set(),        # terminal; only write_plan may demote to pending
    "skipped": set(),
}
TERMINAL_OK = {"approved", "locked"}

REF_STATUSES = {"none", "drafting", "judging", "locked", "rejected"}
REF_TRANSITIONS: dict[str, set[str]] = {
    "none": {"drafting"},
    "drafting": {"judging", "rejected"},
    "judging": {"locked", "rejected"},
    "rejected": {"drafting"},
    "locked": set(),          # terminal; only write_plan may demote to none
}


class LedgerError(Exception):
    """Base class for ledger errors."""


class WriterError(LedgerError):
    """Raised when a writer touches a field it does not own."""


class StatusError(LedgerError):
    """Raised on an illegal status / ref_status transition."""


class SchemaError(LedgerError):
    """Raised when a document fails pure-Python schema validation."""


def load(project_dir: str) -> "Ledger":
    """Load projects/<name>/ledger.json into a Ledger."""
    path = os.path.join(project_dir, _LEDGER_FILE)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return Ledger(doc, project_dir)


def artifact_path(project_dir: str, node_id: str, attempt_id: str, ext: str) -> str:
    """Content-addressed artifact path; named by attempt_id, never overwritten."""
    ext = ext.lstrip(".")
    return os.path.join(project_dir, "artifacts", node_id, f"{attempt_id}.{ext}")


class Ledger:
    """In-memory view of one ledger.json with the full kernel API."""

    def __init__(self, doc: dict, project_dir: str):
        self.doc = doc
        self.project_dir = project_dir
        self._index: dict[str, tuple[dict, str]] = {}
        self._reindex()

    # ── indexing / lookup ────────────────────────────────────────────────────
    def _reindex(self) -> None:
        """Rebuild node_id -> (node, kind) map. kind ∈ {asset, shot}."""
        self._index.clear()
        bible = self.doc.get("bible", {})
        for bucket in ("characters", "scenes", "props", "villains"):
            for asset in bible.get(bucket, []):
                self._index[asset["id"]] = (asset, "asset")
        for ep in self.doc.get("episodes", []):
            for sc in ep.get("scenes", []):
                for sh in sc.get("shots", []):
                    self._index[sh["id"]] = (sh, "shot")

    def node(self, node_id: str) -> dict:
        """Return the node dict for a stable path id (raises KeyError if absent)."""
        return self._index[node_id][0]

    def _kind(self, node_id: str) -> str:
        return self._index[node_id][1]

    def nodes(self, kind: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """All nodes, optionally filtered by kind (asset|shot) and run status/ref_status."""
        out = []
        for node, k in self._index.values():
            if kind and k != kind:
                continue
            if status is not None:
                cur = node["run"].get("ref_status") if k == "asset" else node["run"].get("status")
                if cur != status:
                    continue
            out.append(node)
        return out

    # ── atomic save ──────────────────────────────────────────────────────────
    def save(self) -> None:
        """Atomically persist the document (temp write + os.replace)."""
        path = os.path.join(self.project_dir, _LEDGER_FILE)
        os.makedirs(self.project_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.project_dir, prefix=".ledger.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.doc, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ── writer-tag ownership enforcement ─────────────────────────────────────
    def _plan_fields(self, node_id: str) -> set[str]:
        return ASSET_PLAN_FIELDS if self._kind(node_id) == "asset" else SHOT_PLAN_FIELDS

    def _run_fields(self, node_id: str) -> set[str]:
        return ASSET_RUN_FIELDS if self._kind(node_id) == "asset" else SHOT_RUN_FIELDS

    def write_plan(self, node_id: str, writer: str, **fields: Any) -> None:
        """BRAIN writes plan fields; editing an approved/locked node demotes it and cascades."""
        if writer not in PLAN_WRITERS:
            raise WriterError(f"writer {writer!r} may not write plan fields (only {PLAN_WRITERS})")
        allowed = self._plan_fields(node_id)
        bad = set(fields) - allowed
        if bad:
            raise WriterError(f"{sorted(bad)} are not plan-fields for {node_id} ({self._kind(node_id)})")
        node = self.node(node_id)
        node["plan"].update(fields)
        # plan edit invalidates terminal acceptance → demote + cascade
        if self._kind(node_id) == "asset":
            if node["run"].get("ref_status") == "locked":
                node["run"]["ref_status"] = "none"
                self._invalidate_dependents(node_id)
        else:
            if node["run"].get("status") == "approved":
                node["run"]["status"] = "pending"
                self._invalidate_dependents(node_id)

    def write_run(self, node_id: str, writer: str, **fields: Any) -> None:
        """OVERLORD/generating writes run fields (status goes through set_status, not here)."""
        if writer not in RUN_WRITERS:
            raise WriterError(f"writer {writer!r} may not write run fields (only {RUN_WRITERS})")
        allowed = self._run_fields(node_id)
        bad = set(fields) - allowed
        if bad:
            # a plan field smuggled via write_run is the conflict we forbid
            raise WriterError(f"{sorted(bad)} are not run-fields for {node_id} ({self._kind(node_id)})")
        if "status" in fields or "ref_status" in fields:
            raise WriterError("set status via set_status(), not write_run()")
        self.node(node_id)["run"].update(fields)

    def _invalidate_dependents(self, node_id: str) -> None:
        """Demote any approved shot that (transitively) depends on a re-planned node → pending."""
        changed = True
        invalid = {node_id}
        while changed:
            changed = False
            for sh in self.nodes(kind="shot"):
                if sh["id"] in invalid:
                    continue
                if set(sh.get("deps", [])) & invalid:
                    if sh["run"].get("status") == "approved":
                        sh["run"]["status"] = "pending"
                    invalid.add(sh["id"])
                    changed = True

    # ── status machine ───────────────────────────────────────────────────────
    def set_status(self, node_id: str, status: str, writer: str) -> None:
        """Transition a node's run status (or asset ref_status), validating the machine."""
        if writer not in RUN_WRITERS:
            raise WriterError(f"writer {writer!r} may not set status (only {RUN_WRITERS})")
        node = self.node(node_id)
        if self._kind(node_id) == "asset":
            if status not in REF_STATUSES:
                raise StatusError(f"{status!r} is not a valid ref_status")
            cur = node["run"].get("ref_status", "none")
            if status != cur and status not in REF_TRANSITIONS.get(cur, set()):
                raise StatusError(f"illegal ref_status {cur} → {status} on {node_id}")
            node["run"]["ref_status"] = status
            if status == "locked":
                self.wake_dependents(node_id)
        else:
            if status not in STATUSES:
                raise StatusError(f"{status!r} is not a valid status")
            cur = node["run"].get("status", "pending")
            if status != cur and status not in STATUS_TRANSITIONS.get(cur, set()):
                raise StatusError(f"illegal status {cur} → {status} on {node_id}")
            node["run"]["status"] = status
            if status == "approved":
                self.wake_dependents(node_id)

    # ── resume / frontier ────────────────────────────────────────────────────
    def _dep_satisfied(self, dep_id: str) -> bool:
        """A dep is satisfied if a shot dep is approved or an asset dep is locked."""
        if dep_id not in self._index:
            return False
        node, kind = self._index[dep_id]
        if kind == "asset":
            return node["run"].get("ref_status") == "locked"
        return node["run"].get("status") == "approved"

    def runnable_frontier(self) -> list[str]:
        """Pending nodes whose deps are all approved (shots) / locked (asset refs)."""
        out = []
        for node, kind in self._index.values():
            if kind == "asset":
                if node["run"].get("ref_status", "none") in ("none", "pending"):
                    # asset refs have no upstream deps; a fresh ref is runnable
                    out.append(node["id"])
            else:
                if node["run"].get("status") != "pending":
                    continue
                if all(self._dep_satisfied(d) for d in node.get("deps", [])):
                    out.append(node["id"])
        return out

    def reset_interrupted(self) -> list[str]:
        """Crash recovery: flip any generating|judging node back to pending. Returns reset ids."""
        reset = []
        for sh in self.nodes(kind="shot"):
            if sh["run"].get("status") in ("generating", "judging"):
                sh["run"]["status"] = "pending"
                reset.append(sh["id"])
        for a in self.nodes(kind="asset"):
            if a["run"].get("ref_status") in ("drafting", "judging"):
                a["run"]["ref_status"] = "none"
                reset.append(a["id"])
        return reset

    def wake_dependents(self, node_id: str) -> list[str]:
        """Flip pending dependents whose deps are now ALL satisfied so the frontier advances."""
        woken = []
        for sh in self.nodes(kind="shot"):
            if node_id not in sh.get("deps", []):
                continue
            if sh["run"].get("status") != "pending":
                continue
            if all(self._dep_satisfied(d) for d in sh.get("deps", [])):
                woken.append(sh["id"])  # already runnable; surfaced for the runner/poller
        return woken

    # ── 抽卡 history ──────────────────────────────────────────────────────────
    def append_attempt(self, node_id: str, attempt: dict) -> None:
        """Append-only: record a generation take and set it as current."""
        run = self.node(node_id)["run"]
        run.setdefault("attempts", []).append(attempt)
        run["current_attempt_id"] = attempt.get("attempt_id")
        art = {
            "attempt_id": attempt.get("attempt_id"),
            "path": attempt.get("artifact_path"),
            "thumb_path": attempt.get("thumb_path"),
        }
        run["current_artifact"] = {k: v for k, v in art.items() if v is not None}

    def append_verdict(self, node_id: str, verdict: dict) -> None:
        """Attach a judge verdict to the current attempt (and as final_verdict)."""
        run = self.node(node_id)["run"]
        attempts = run.get("attempts", [])
        if attempts:
            attempts[-1]["verdict"] = verdict
        run["final_verdict"] = verdict

    def current_artifact(self, node_id: str) -> Optional[dict]:
        """Return run.current_artifact for a node (None if no take yet)."""
        return self.node(node_id)["run"].get("current_artifact")

    # ── lesson store (the moat) ──────────────────────────────────────────────
    def append_lesson(self, lesson: dict) -> None:
        """Append a lesson to the in-ledger store (hit_count defaults to 0)."""
        lesson.setdefault("hit_count", 0)
        self.doc.setdefault("lessons", []).append(lesson)

    def lessons_for(self, scope: dict, k: int = 3) -> list[dict]:
        """Top-k lessons matching (category, model) then style_id/asset_kind, by hit_count.

        Increments hit_count on each returned lesson (retrieval is a hit).
        """
        cat, model = scope.get("category"), scope.get("model")
        scored: list[tuple[int, int, dict]] = []
        for lesson in self.doc.get("lessons", []):
            s = lesson.get("scope", {})
            if s.get("category") != cat or s.get("model") != model:
                continue
            specificity = 0
            if scope.get("style_id") and s.get("style_id") == scope.get("style_id"):
                specificity += 1
            if scope.get("asset_kind") and s.get("asset_kind") == scope.get("asset_kind"):
                specificity += 1
            scored.append((specificity, lesson.get("hit_count", 0), lesson))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        top = [lesson for _, _, lesson in scored[:k]]
        for lesson in top:
            lesson["hit_count"] = lesson.get("hit_count", 0) + 1
        return top

    # ── validation ───────────────────────────────────────────────────────────
    def validate(self) -> None:
        """Pure-Python structural validation against ledger.schema.json (raises SchemaError)."""
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        errors: list[str] = []
        _validate(self.doc, schema, schema, "$", errors)
        if errors:
            raise SchemaError("; ".join(errors[:20]))


# ── minimal pure-Python JSON Schema (Draft 2020-12 subset) validator ──────────
# Supports the constructs used by ledger.schema.json: type, required, properties,
# additionalProperties, items, enum, $ref (#/$defs/...), oneOf, minItems, examples.
def _resolve(ref: str, root: dict) -> dict:
    assert ref.startswith("#/"), f"only local refs supported: {ref}"
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


_PY_TYPES = {
    "object": dict, "array": list, "string": str,
    "integer": int, "number": (int, float), "boolean": bool, "null": type(None),
}


def _type_ok(value: Any, t: str) -> bool:
    py = _PY_TYPES[t]
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return isinstance(value, py)


def _validate(value: Any, schema: dict, root: dict, path: str, errors: list[str]) -> None:
    if "$ref" in schema:
        _validate(value, _resolve(schema["$ref"], root), root, path, errors)
        return
    if "oneOf" in schema:
        matches = 0
        for sub in schema["oneOf"]:
            tmp: list[str] = []
            _validate(value, sub, root, path, tmp)
            if not tmp:
                matches += 1
        if matches != 1:
            errors.append(f"{path}: matched {matches} of oneOf (want exactly 1)")
        return
    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: {value!r} not in enum {schema['enum']}")
        return

    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, tt) for tt in types):
            errors.append(f"{path}: expected {t}, got {type(value).__name__}")
            return

    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required {req!r}")
        addl = schema.get("additionalProperties", True)
        for key, sub in value.items():
            if key in props:
                _validate(sub, props[key], root, f"{path}.{key}", errors)
            elif addl is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(addl, dict):
                _validate(sub, addl, root, f"{path}.{key}", errors)
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                _validate(item, item_schema, root, f"{path}[{i}]", errors)
