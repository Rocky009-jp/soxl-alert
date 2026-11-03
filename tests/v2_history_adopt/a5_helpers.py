"""Helpers for the v2_history_adopt tests (never imported by the runtime). Synthetic sessions, series and ledgers.

Sockets are disabled on import (as in the other test packages). The existing helpers (h_helpers, ho_helpers, r3_helpers,
r4_helpers, d5_helpers) are only imported for reading, never changed. Every expected value of an adoption record and of
a plan is calculated here from the position where the file was damaged and from the file's own JSON, with the
independent test-only record builder HB and plain hashlib; never with the code under test.
"""
import copy
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_diagnose"), os.path.join(ROOT, "tests", "v2_history_restart")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import d5_helpers as X  # noqa: E402  (existing helper; it also disables sockets)
import r3_helpers as R3  # noqa: E402
import v2_history as V  # noqa: E402
import v2_history_adopt as A  # noqa: E402
from v2_persistence.codec import canonical_json  # noqa: E402
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_recovery.common import requested_text  # noqa: E402

H, P, D, WHEN, T, R4 = X.H, X.P, X.D, X.WHEN, X.T, X.R4
G = X.G
ZERO = "0" * 64
WHEN_TEXT = requested_text(WHEN)
REASON = "ADOPT_VERIFIED_PREFIX"
OPERATION = "soxl-v2-history-prefix-adoption-plan/1"
GONE = object()                      # "delete this key" in an edit
_HEX64 = re.compile(r"[0-9a-f]{64}")


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- damaged files --------------------------------------------------------------------------------------------------
def damaged_last(builder):
    """The file of the builder's records whose last record has a wrong event_hash. The expected adopt_count is the number
    of records before it (decided from where the file was changed)."""
    n = len(builder.events)
    return X.file_of(X.with_hash(builder.events, n - 1)), n - 1


def damaged_at(builder, index):
    """The file whose record `index` has a wrong event_hash; the records before it are the verified prefix."""
    return X.file_of(X.with_hash(builder.events, index)), index


def new_world():
    """0 GENESIS, 1..6 APPLY D1..D6, last record damaged: prefix k=6 (GENESIS + D1..D5)."""
    b = X.ex_new()
    data, k = damaged_last(b)
    return b, data, k


# --- the adoption record and the plan, calculated independently ----------------------------------------------------------
def evidence_of(data, k):
    doc = json.loads(data.decode("utf-8"))
    hs, hh = doc.get("head_seq"), doc.get("head_hash")
    return {"raw_sha256": sha_bytes(data), "raw_size": len(data), "claimed_schema_version": 2,
            "claimed_head_seq": hs if type(hs) is int else None,
            "claimed_head_hash": hh if isinstance(hh, str) and _HEX64.fullmatch(hh) else None,
            "discarded_from_seq": k}


def record_of(prefix, evidence, rid, when=WHEN_TEXT, basis_over=None, over=None):
    """One RECOVERY_PREFIX_ADOPTION record after `prefix` (a list of record dicts), written by the design's table.
    basis_over / over edit the basis / the record (GONE removes a key); the request hash is recomputed from the basis
    unless `over` sets it, and the event hash is always recomputed last."""
    last = prefix[-1]
    basis = {"request_id": rid, "evidence": deep(evidence), "reason_code": REASON, "requested_at": when}
    for key, value in (basis_over or {}).items():
        if value is GONE:
            del basis[key]
        else:
            basis[key] = value
    rec = {"kind": "RECOVERY_PREFIX_ADOPTION", "seq": len(prefix), "parent_seq": len(prefix) - 1,
           "parent_hash": last["event_hash"], "evidence": deep(evidence), "request_id": rid,
           "request_hash": H.request_hash(basis), "request_basis": basis, "reason_code": REASON,
           "requested_at": when, "state_after": deep(last["state_after"])}
    for key, value in (over or {}).items():
        if value is GONE:
            rec.pop(key, None)
        else:
            rec[key] = value
    rec["event_hash"] = H.hash_of(rec)
    if (over or {}).get("event_hash") is GONE:
        del rec["event_hash"]
    return rec


def adopted_events(data, k, rid="ad1", when=WHEN_TEXT):
    """The candidate's physical records: the file's first k records and the adoption record of the design."""
    prefix = json.loads(data.decode("utf-8"))["events"][:k]
    return prefix + [record_of(prefix, evidence_of(data, k), rid, when)]


def prefix_events(data, k):
    return json.loads(data.decode("utf-8"))["events"][:k]


def expected_basis(data, k, rid, when_text=WHEN_TEXT):
    """The 21 keys of a plan, from the file and the diagnosis (the diagnosis' own digest and discarded block are the only
    values taken from the code that is not under test here: the B-5a diagnosis)."""
    events = json.loads(data.decode("utf-8"))["events"]
    prefix = events[:k]
    rec = record_of(prefix, evidence_of(data, k), rid, when_text)
    diag = G.diagnose_history_bytes(data)
    candidate = H.header(prefix + [rec])
    return {
        "operation": OPERATION, "status": "READY", "raw_sha256": sha_bytes(data), "raw_size": len(data),
        "diagnosis_digest": diag.digest, "adopt_count": k, "discarded": diag.to_dict()["discarded"],
        "prefix_head_seq": prefix[-1]["seq"], "prefix_head_hash": prefix[-1]["event_hash"],
        "prefix_state_digest": sha_text(cj(prefix[-1]["state_after"])),
        "prefix_document_digest": sha_text(cj(H.header(prefix))), "request_id": rid, "request_hash": rec["request_hash"],
        "reason_code": REASON, "requested_at": when_text, "candidate_history": candidate,
        "candidate_digest": sha_text(cj(candidate)), "candidate_head_seq": k, "candidate_head_hash": rec["event_hash"],
        "candidate_state_digest": sha_text(cj(prefix[-1]["state_after"])), "candidate_record": rec}


def candidate_bytes(data, k, rid="ad1", when=WHEN_TEXT):
    """The normalized bytes of the candidate (what a store would write)."""
    return cj(H.header(adopted_events(data, k, rid, when))).encode("utf-8")


# --- calling the runtime --------------------------------------------------------------------------------------------------
def prep(data, k, rid="ad1", when=WHEN):
    return A.prepare_prefix_adoption(data, k, rid, when)


def confirm(plan, data, plan_hash=None):
    return A.confirm_prefix_adoption(plan, plan.plan_hash if plan_hash is None else plan_hash, data)


def refusal(fn, *args, **kwargs):
    """(code, field, rule) of the refusal of fn."""
    try:
        fn(*args, **kwargs)
    except Exception as e:                                   # noqa: BLE001 - the type is part of the check below
        assert isinstance(e, Exception)
        return type(e).__name__, getattr(e, "code", None), getattr(e, "field", None), getattr(e, "rule", None)
    raise AssertionError("expected a refusal")


def err(fn, *args, **kwargs):
    """('code', 'field', 'rule') of a PersistenceError refusal."""
    out = refusal(fn, *args, **kwargs)
    assert out[0] == "PersistenceError", out
    return out[1:]


def plan_with(plan, fn):
    """A plan from the plan's dict after fn(dict) changed it (the hash is not fixed up)."""
    d = plan.to_dict()
    fn(d)
    return A.AdoptionPlan.from_dict(d)


def refreshed(plan, fn):
    """Like plan_with, but the plan_hash is recomputed from the changed basis, so only the content is wrong."""
    d = plan.to_dict()
    fn(d)
    d["plan_hash"] = sha_text(cj(d["basis"]))
    return A.AdoptionPlan.from_dict(d)
