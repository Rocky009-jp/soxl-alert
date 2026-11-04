"""Values of the maintenance package (C-4): the report of a root, the unlock plan, the MANIFEST bytes and the result.

RootReport and UnlockPlan are the package's own immutable, text-backed values (the existing `_Frozen` pattern); they hold
identities and fixed words only, never a path. The MANIFEST is the canonical JSON text of eight fixed keys, a pure
function of what an operation is about, so a later call can compare the file with the bytes it would write now.
Nothing here touches a file, a clock, the environment or the network."""
import copy
import json
from dataclasses import dataclass
from typing import Any

from v2_history.common import is_hex64, is_int
from v2_history_ops.values import _Frozen, digest_of
from v2_persistence.codec import canonical_json
from v2_persistence.local.errors import LocalStoreError
from v2_recovery.common import valid_request_id

# --- names: the same as S2 and C-3 (a test reads all three modules and compares) ----------------------------------------
HISTORY_NAME = "history.json"
V1_NAME = "snapshot.json"
LOCK_NAME = "write.lock"
TMP_PREFIX, TMP_SUFFIX = ".history.", ".tmp"
S2_TMP_PREFIX = ".snapshot."
LOCK_MAGIC = b"v2_history_maintain.lock\n"
C3_LOCK_MAGIC = b"v2_history_local.lock\n"
S2_LOCK_MAGIC = b"v2_persistence.local.lock\n"
QUARANTINE_NAME = "quarantine"
MANIFEST_NAME = "MANIFEST"
Q_TMP_PREFIX = ".q."

# --- fixed words --------------------------------------------------------------------------------------------------------
EMPTY, V2, V1_ONLY, V1_AND_V2 = "EMPTY", "V2", "V1_ONLY", "V1_AND_V2"
OWNER_S2, OWNER_C3, OWNER_C4, OWNER_EMPTY, OWNER_UNKNOWN = "S2", "C3", "C4", "EMPTY", "UNKNOWN"
KIND_LOCK, KIND_TMP = "lock", "tmp"
UNLOCKED, MIGRATED, ADOPTED = "UNLOCKED", "MIGRATED", "ADOPTED"
OP_UNLOCK, OP_MIGRATION, OP_ADOPTION = "UNLOCK", "MIGRATION", "ADOPTION"
PLAN_OPERATION = "soxl-v2-maintenance-unlock/1"
MANIFEST_FORMAT = "soxl-v2-quarantine/1"
MANIFEST_KEYS = frozenset(["format", "operation", "key", "request_id", "plan_hash", "publication_hash",
                           "writers_stopped", "targets"])
TARGET_KEYS = frozenset(["name", "kind", "raw_sha256", "raw_size"])
PLAN_BODY_KEYS = frozenset(["operation", "request_id", "writers_stopped", "targets"])
PLAN_TARGET_KEYS = frozenset(["name", "kind", "raw_sha256", "raw_size", "st_dev", "st_ino"])
MANIFEST_KINDS = (KIND_LOCK, KIND_TMP, "v1", "history")
_HEX = frozenset("0123456789abcdef")


def maintenance_error(code, field, phase, rule=None, cleanup=(), primary=None):
    return LocalStoreError(code, field, phase, rule=rule, cleanup=cleanup, primary=primary)


def _plan_error(rule):
    return maintenance_error("maintenance_plan_invalid", "plan", "args", rule=rule)


# --- name classification (the loose rule of the C-3 scan: prefix and suffix) ---------------------------------------------
def safe_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 255 and name not in (".", "..")
            and not any(c in name for c in ("/", "\\", "\0")))


def is_history_tmp(name):
    return safe_name(name) and name.startswith(TMP_PREFIX) and name.endswith(TMP_SUFFIX)


def is_snapshot_tmp(name):
    return safe_name(name) and name.startswith(S2_TMP_PREFIX) and name.endswith(TMP_SUFFIX)


def is_root_tmp(name):
    return is_history_tmp(name) or is_snapshot_tmp(name)


def is_q_tmp(name):
    """The package's own temporary file inside a quarantine directory: .q.<32 hex>.tmp."""
    if not safe_name(name) or not name.startswith(Q_TMP_PREFIX) or not name.endswith(TMP_SUFFIX):
        return False
    middle = name[len(Q_TMP_PREFIX):-len(TMP_SUFFIX)]
    return len(middle) == 32 and all(c in _HEX for c in middle)


def lock_owner(data):
    """Which kind of writer left this lock (a hint for a person; it never changes how an unlock works)."""
    if data == b"":
        return OWNER_EMPTY
    for magic, owner in ((S2_LOCK_MAGIC, OWNER_S2), (C3_LOCK_MAGIC, OWNER_C3), (LOCK_MAGIC, OWNER_C4)):
        if data.startswith(magic):
            return owner
    return OWNER_UNKNOWN


# --- RootReport -----------------------------------------------------------------------------------------------------------
class RootReport(_Frozen):
    """What a root holds, seen without the lock: layout, the two main files, the lock and temporary files, the
    quarantine. Identities and fixed words only; no path."""

    __slots__ = ()

    @classmethod
    def _make(cls, view):
        return cls._wrap(view, _plan_error)

    def _get(self, key):
        return copy.deepcopy(self._view[key])

    layout = property(lambda self: self._get("layout"))
    history = property(lambda self: self._get("history"))
    v1 = property(lambda self: self._get("v1"))
    artifacts = property(lambda self: self._get("artifacts"))
    quarantine = property(lambda self: self._get("quarantine"))

    def __repr__(self):
        v = self._view
        return "RootReport(layout=%s, artifacts=%d)" % (v["layout"], len(v["artifacts"]))


# --- UnlockPlan -----------------------------------------------------------------------------------------------------------
class UnlockPlan(_Frozen):
    """{body, plan_hash}: what a person confirms before an explicit unlock. Made only by plan_unlock."""

    __slots__ = ()

    @classmethod
    def _make(cls, body):
        return cls._wrap({"body": body, "plan_hash": digest_of(body)}, _plan_error)

    @property
    def body(self):
        return copy.deepcopy(self._view["body"])

    plan_hash = property(lambda self: self._view["plan_hash"])
    request_id = property(lambda self: self._view["body"]["request_id"])
    writers_stopped = property(lambda self: self._view["body"]["writers_stopped"])
    targets = property(lambda self: copy.deepcopy(self._view["body"]["targets"]))

    def __repr__(self):
        try:
            return "UnlockPlan(targets=%d, plan_hash=%s)" % (len(self._view["body"]["targets"]),
                                                             self._view["plan_hash"][:12])
        except (KeyError, TypeError):
            return "UnlockPlan(?)"


def plan_unlock(report, request_id, writers_stopped):
    """Pure. The declaration must be exactly True (a person says the writers are stopped; nothing proves it)."""
    if writers_stopped is not True:
        raise maintenance_error("maintenance_declaration_missing", "writers_stopped", "args")
    if type(report) is not RootReport:
        raise maintenance_error("maintenance_plan_invalid", "plan", "args", rule="report_type")
    if not valid_request_id(request_id):
        raise maintenance_error("maintenance_plan_invalid", "plan", "args", rule="request_id")
    arts = report.artifacts
    if not arts:
        raise maintenance_error("maintenance_nothing_to_unlock", "store", "args")
    if any(a["regular"] is not True for a in arts):
        raise maintenance_error("maintenance_target_unsupported", "store", "args")
    tmps = sorted((a for a in arts if a["kind"] == KIND_TMP), key=lambda a: a["name"])
    locks = [a for a in arts if a["kind"] == KIND_LOCK]
    targets = [{"name": a["name"], "kind": a["kind"], "raw_sha256": a["raw_sha256"], "raw_size": a["raw_size"],
                "st_dev": a["st_dev"], "st_ino": a["st_ino"]} for a in tmps + locks]
    return UnlockPlan._make({"operation": PLAN_OPERATION, "request_id": request_id, "writers_stopped": True,
                             "targets": targets})


def _target_ok(t):
    if type(t) is not dict or set(t) != PLAN_TARGET_KEYS:
        return False
    if t["kind"] == KIND_LOCK:
        name_ok = t["name"] == LOCK_NAME
    elif t["kind"] == KIND_TMP:
        name_ok = is_root_tmp(t["name"])
    else:
        name_ok = False
    return (name_ok and is_hex64(t["raw_sha256"]) and is_int(t["raw_size"]) and t["raw_size"] >= 0
            and is_int(t["st_dev"]) and is_int(t["st_ino"]))


def _plan_shape_ok(body):
    if (type(body) is not dict or set(body) != PLAN_BODY_KEYS or body["operation"] != PLAN_OPERATION
            or not valid_request_id(body["request_id"]) or body["writers_stopped"] is not True
            or type(body["targets"]) is not list or not body["targets"]):
        return False
    targets = body["targets"]
    if not all(_target_ok(t) for t in targets):
        return False
    names = [t["name"] for t in targets]
    tmps = [t["name"] for t in targets if t["kind"] == KIND_TMP]
    locks = [i for i, t in enumerate(targets) if t["kind"] == KIND_LOCK]
    return (len(set(names)) == len(names) and tmps == sorted(tmps) and len(locks) <= 1
            and (not locks or locks[0] == len(targets) - 1))


def check_plan(plan):
    """(body, plan_hash) of a plan that plan_unlock could have made, or a refusal. The hash is recomputed here; the
    names and kinds are held to the two shapes (the lock, a temporary file), so a plan can never name history.json,
    snapshot.json or a directory, and the lock can only come last."""
    if type(plan) is not UnlockPlan:
        raise maintenance_error("maintenance_plan_invalid", "plan", "args", rule="type")
    try:
        view = plan.to_dict()
        body, plan_hash = view["body"], view["plan_hash"]
        ok = _plan_shape_ok(body)
    except (KeyError, TypeError, AttributeError):
        ok = False
    if not ok:
        raise maintenance_error("maintenance_plan_invalid", "plan", "args", rule="shape")
    if not is_hex64(plan_hash) or digest_of(body) != plan_hash:
        raise maintenance_error("maintenance_plan_invalid", "plan", "args", rule="plan_hash")
    return body, plan_hash


# --- MANIFEST -------------------------------------------------------------------------------------------------------------
def manifest_dict(operation, key, request_id, plan_hash, publication_hash, writers_stopped, targets):
    return {"format": MANIFEST_FORMAT, "operation": operation, "key": key, "request_id": request_id,
            "plan_hash": plan_hash, "publication_hash": publication_hash, "writers_stopped": writers_stopped,
            "targets": [{"name": t["name"], "kind": t["kind"], "raw_sha256": t["raw_sha256"],
                         "raw_size": t["raw_size"]} for t in targets]}


def manifest_bytes(manifest):
    """The one canonical byte form (ASCII JSON, no newline). Equal inputs give equal bytes."""
    return canonical_json(manifest).encode("ascii")


def read_manifest(data):
    """The manifest dict of exactly these bytes, or None when they are not a well-formed MANIFEST in canonical form."""
    try:
        obj = json.loads(data.decode("utf-8"))
        ok = (type(obj) is dict and set(obj) == MANIFEST_KEYS and obj["format"] == MANIFEST_FORMAT
              and obj["operation"] in (OP_UNLOCK, OP_MIGRATION, OP_ADOPTION) and is_hex64(obj["key"])
              and is_hex64(obj["plan_hash"]) and type(obj["writers_stopped"]) is bool
              and (obj["publication_hash"] is None or is_hex64(obj["publication_hash"]))
              and type(obj["targets"]) is list and len(obj["targets"]) > 0
              and (obj["request_id"] is None or valid_request_id(obj["request_id"])))
        if ok:
            for t in obj["targets"]:
                if (type(t) is not dict or set(t) != TARGET_KEYS or not safe_name(t["name"])
                        or t["kind"] not in MANIFEST_KINDS or not is_hex64(t["raw_sha256"])
                        or not is_int(t["raw_size"]) or t["raw_size"] < 0):
                    ok = False
                    break
        if ok and manifest_bytes(obj) != data:
            ok = False
    except (ValueError, UnicodeDecodeError, KeyError, TypeError, AttributeError, RecursionError):
        ok = False
    return obj if ok else None


def unlock_manifest(body, plan_hash):
    return manifest_dict(OP_UNLOCK, plan_hash, body["request_id"], plan_hash, None, True, body["targets"])


# --- result ---------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MaintenanceResult:
    """Only a normal completion returns this. `history` is the History held in history.json at the end (None for an
    unlock); `resumed` says an earlier attempt had already done part of the work. Not a right to notify."""
    status: str
    key: str
    resumed: bool
    history: Any
    persistence_level: str
