"""validate_resolutions: form, hash chain, references and creation-time state of a ResolutionSet.

Checked against the Snapshot only (never against a ledger or the sessions of today). Nothing is repaired. A record is
judged against the *prefix* of the S1 history that existed when it was made (source_head), so a later normal APPLY
never invalidates an older record. The prefix is not re-validated per record: the whole Snapshot is validated once
(validate_snapshot) and each prefix is read from that checked history by seq and event hash.
"""
import copy
from dataclasses import dataclass

from v2_core.errors import InputError
from v2_core.sessions import SessionList
from v2_persistence.events import SESSION_KEYS, session_dict
from v2_persistence.recompute import validate_snapshot

from .common import (BASIS_KEYS, KIND_ACK, KIND_DECLARE, RECORD_KEYS, V_LATE, V_ROW_REMOVED, VARIANTS,
                     basis_request_hash, is_date, is_hex64, is_int, is_requested_text, normalize_command,
                     reason_for_commands, record_hash_of, record_reason, same, valid_request_id)
from .errors import resolution_invalid
from .values import SCHEMA, ResolutionSet

HEADER_KEYS = frozenset(["schema", "head_resolution_seq", "head_resolution_hash", "records"])
_KINDS = (KIND_ACK, KIND_DECLARE)


@dataclass(frozen=True)
class ResolutionCheck:
    """Outcome of validate_resolutions. Only counts, ids and hashes; nothing from a ledger."""
    head_resolution_seq: int
    head_resolution_hash: object
    record_count: int
    request_ids: tuple
    declared_days: tuple
    resolutions_digest: str
    snapshot_head_seq: int


class SnapshotView:
    """What the resolution checks need from a validated Snapshot (read-only copies)."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.v = validate_snapshot(snapshot)
        self.events = snapshot.events                      # a fresh deep copy
        self.applies = list(self.v.applies)
        self.by_seq = {ap.seq: ap for ap in self.applies}
        self.apply_days = {ap.d for ap in self.applies}
        self.fixed_fps = {ap.fingerprint for ap in self.applies}
        self.start_after = self.v.start_after
        self.boundary = copy.deepcopy(self.v.boundary_session)
        self.head_seq = self.v.head_seq
        self.head_hash = self.v.head_hash

    def latest_apply(self, upto_seq):
        """The latest APPLY with seq <= upto_seq, or None."""
        last = None
        for ap in self.applies:
            if ap.seq <= upto_seq:
                last = ap
        return last

    def latest_apply_day(self, upto_seq):
        ap = self.latest_apply(upto_seq)
        return self.start_after if ap is None else ap.d

    def decision_cols(self, seq):
        return copy.deepcopy(self.events[seq]["confirmed_inputs"]["decision"])


def _bad(rule, field="resolutions"):
    return resolution_invalid(field, rule)


def _check_context(ctx):
    if not isinstance(ctx, list) or len(ctx) != 3:
        raise _bad("session_context")
    for e in ctx:
        if not isinstance(e, dict) or set(e) != SESSION_KEYS:
            raise _bad("session_context")
    try:
        sl = SessionList.from_dicts(ctx)
    except InputError:
        raise _bad("session_context") from None
    if not same([session_dict(s) for s in sl.sessions], ctx):
        raise _bad("session_context")
    return sl


def _check_ref_shapes(rec):
    """Variant-wise presence of the two references (the shapes were fixed by normalize_command)."""
    kind, variant = rec["kind"], rec["variant"]
    if kind == KIND_DECLARE:
        return
    if variant == V_LATE:
        if rec["applied_ref"] is not None:
            raise _bad("applied_ref")
        if rec["missing_ref"] is None:
            raise _bad("missing_ref")
    else:
        if rec["applied_ref"] is None:
            raise _bad("applied_ref")
        if rec["missing_ref"] is not None:
            raise _bad("missing_ref")


def validate_set(sv, resolutions):
    """Validate against a SnapshotView. Returns the records as fresh dicts (validated)."""
    if not isinstance(resolutions, ResolutionSet):
        raise _bad("type")
    data = resolutions.to_dict()
    if not isinstance(data, dict) or set(data) != HEADER_KEYS:
        raise _bad("header_keys")
    if data["schema"] != SCHEMA:
        raise _bad("schema")
    recs = data["records"]
    if not isinstance(recs, list):
        raise _bad("records")
    n = len(recs)
    head_seq, head_hash = data["head_resolution_seq"], data["head_resolution_hash"]
    if not is_int(head_seq) or head_seq != n:
        raise _bad("head")
    if n == 0:
        if head_hash is not None:
            raise _bad("head")
    else:
        if not isinstance(recs[-1], dict) or head_hash != recs[-1].get("resolution_hash"):
            raise _bad("head")
    for rec in recs:
        if not isinstance(rec, dict) or set(rec) != RECORD_KEYS:
            raise _bad("record_keys")

    prev_hash = None
    for i, rec in enumerate(recs):                        # chain first, so later rules read trusted positions
        if not is_int(rec["resolution_seq"]) or rec["resolution_seq"] != i + 1:
            raise _bad("seq")
        if rec["parent_resolution_hash"] != prev_hash:
            raise _bad("parent_hash")
        if not is_hex64(rec["resolution_hash"]) or rec["resolution_hash"] != record_hash_of(rec):
            raise _bad("resolution_hash")
        prev_hash = rec["resolution_hash"]

    checker = _Checker(sv, recs)
    i = 0
    while i < n:
        first = recs[i]
        count = first["command_count"]
        if not is_int(count) or count < 1 or first["command_index"] != 0 or i + count > n:
            raise _bad("batch")
        group = recs[i:i + count]
        checker.check_group(group, i)
        i += count
    return copy.deepcopy(recs)


class _Checker:
    def __init__(self, sv, recs):
        self.sv = sv
        self.recs = recs
        self.seen_requests = set()
        self.last_src = 0
        self.declares = []          # [{"seq","hash","d","context"}] of DECLARE records checked so far

    def check_group(self, group, start):
        sv = self.sv
        first = group[0]
        rid = first["request_id"]
        if not valid_request_id(rid) or rid in self.seen_requests:
            raise _bad("request")
        self.seen_requests.add(rid)
        for j, rec in enumerate(group):
            for key in ("request_id", "request_hash", "request_basis", "command_count", "source_head_seq",
                        "source_head_hash", "state_after", "ledger_digest", "requested_at"):
                if not same(rec[key], first[key]):
                    raise _bad("batch")
            if not is_int(rec["command_index"]) or rec["command_index"] != j:
                raise _bad("batch")
        basis = first["request_basis"]
        self._check_basis(first, basis)
        commands = basis["commands"]
        if len(commands) != len(group):
            raise _bad("batch")
        src = first["source_head_seq"]
        self._check_source(first)
        check_d = basis["check_d"]
        prefix_day = sv.latest_apply_day(src)
        if not is_date(check_d) or not check_d > sv.start_after or not check_d >= prefix_day:
            raise _bad("check_d")
        for j, rec in enumerate(group):
            self._check_record(rec, commands[j], check_d, src)

    def _check_basis(self, first, basis):
        if not isinstance(basis, dict) or set(basis) != BASIS_KEYS:
            raise _bad("request_basis")
        if basis["request_id"] != first["request_id"] or not is_requested_text(basis["requested_at"]):
            raise _bad("request_basis")
        if basis["requested_at"] != first["requested_at"]:
            raise _bad("requested_at")
        cmds = basis["commands"]
        if not isinstance(cmds, list) or not cmds:
            raise _bad("request_basis")
        norm = [normalize_command(c, "resolutions") for c in cmds]
        if not same(norm, cmds):
            raise _bad("command_shape")
        if basis["reason_code"] not in reason_for_commands(cmds):
            raise _bad("reason_code")
        if not is_hex64(first["request_hash"]) or first["request_hash"] != basis_request_hash(basis):
            raise _bad("request_hash")

    def _check_source(self, first):
        sv = self.sv
        src = first["source_head_seq"]
        if not is_int(src) or not 0 <= src <= sv.head_seq or src < self.last_src:
            raise _bad("source_head")
        if first["source_head_hash"] != sv.events[src]["event_hash"]:
            raise _bad("source_head")
        if not same(first["state_after"], sv.events[src]["state_after"]):
            raise _bad("state_after")
        if not is_hex64(first["ledger_digest"]):
            raise _bad("ledger_digest")
        self.last_src = src

    def _check_record(self, rec, cmd, check_d, src):
        sv = self.sv
        kind = rec["kind"]
        if kind not in _KINDS:
            raise _bad("kind")
        if rec["variant"] is not None and rec["variant"] not in VARIANTS:
            raise _bad("variant")
        if (rec["kind"] != cmd["kind"] or rec["variant"] != cmd["variant"] or rec["d"] != cmd["d"]
                or not same(rec["record_fingerprints"], cmd["record_fingerprints"])
                or not same(rec["applied_ref"], cmd["applied_ref"]) or not same(rec["missing_ref"], cmd["missing_ref"])):
            raise _bad("batch")
        if rec["reason_code"] != record_reason(kind):
            raise _bad("reason_code")
        if not is_date(rec["d"]) or rec["d"] > check_d:
            raise _bad("check_d")
        fps = rec["record_fingerprints"]
        if not isinstance(fps, list) or not all(is_hex64(x) for x in fps) or fps != sorted(set(fps)):
            raise _bad("fingerprints")
        if any(fp in sv.fixed_fps for fp in fps):
            raise _bad("exclude_applied")
        _check_ref_shapes(rec)
        if kind == KIND_ACK:
            self._check_ack(rec, src)
        else:
            self._check_declare(rec, src)

    def _check_ack(self, rec, src):
        sv = self.sv
        variant = rec["variant"]
        if rec["session_context"] is not None or rec["frontier_before"] is not None:
            raise _bad("session_context")
        fps = rec["record_fingerprints"]
        if variant == V_ROW_REMOVED:
            if fps:
                raise _bad("fingerprints")
        elif not fps:
            raise _bad("fingerprints")
        if variant == V_LATE:
            self._check_late_ref(rec, src)
            return
        ref = rec["applied_ref"]
        ap = sv.by_seq.get(ref["seq"])
        if (ap is None or ref["seq"] > src or ref["event_hash"] != ap.event_hash
                or ref["fingerprint"] != ap.fingerprint or rec["d"] != ap.d):
            raise _bad("applied_ref")

    def _check_late_ref(self, rec, src):
        sv = self.sv
        ref = rec["missing_ref"]
        if ref["kind"] == "APPLY":
            ap = sv.by_seq.get(ref["seq"])
            if (ap is None or ref["seq"] > src or ref["event_hash"] != ap.event_hash
                    or rec["d"] not in ap.skipped):
                raise _bad("missing_ref")
            return
        for dec in self.declares:
            if dec["seq"] == ref["resolution_seq"]:
                if dec["hash"] != ref["resolution_hash"] or dec["d"] != rec["d"] or dec["seq"] >= rec["resolution_seq"]:
                    raise _bad("missing_ref")
                return
        raise _bad("missing_ref")

    def _check_declare(self, rec, src):
        sv = self.sv
        if rec["variant"] is not None:
            raise _bad("variant")
        d = rec["d"]
        _check_context(rec["session_context"])
        ctx = rec["session_context"]
        prefix = sv.latest_apply(src)
        prefix_day = sv.start_after if prefix is None else prefix.d
        last_decl = self.declares[-1]["d"] if self.declares else None
        frontier = prefix_day if last_decl is None or last_decl < prefix_day else last_decl
        if d in sv.apply_days:
            raise _bad("declare_applied")
        if rec["frontier_before"] != frontier or not d > frontier:
            raise _bad("declare_frontier")
        if ctx[0]["date"] != frontier or ctx[1]["date"] != d or not ctx[0]["confirmed"] or not ctx[1]["confirmed"]:
            raise _bad("session_context")
        if last_decl is not None and last_decl == frontier:
            expected = self.declares[-1]["context"][1]
        elif prefix is None:
            expected = sv.boundary
        else:
            expected = prefix.context[-2]
        if not same(ctx[0], expected):
            raise _bad("session_context")
        self.declares.append({"seq": rec["resolution_seq"], "hash": rec["resolution_hash"], "d": d, "context": ctx})


def validate_resolutions(snapshot, resolutions):
    """Check a ResolutionSet against an S1 Snapshot. Raises on any problem; returns an independent summary."""
    sv = SnapshotView(snapshot)                           # validate_snapshot raises its own errors for a bad Snapshot
    recs = validate_set(sv, resolutions)
    return ResolutionCheck(
        head_resolution_seq=len(recs), head_resolution_hash=resolutions.head_resolution_hash,
        record_count=len(recs), request_ids=tuple(dict.fromkeys(r["request_id"] for r in recs)),
        declared_days=tuple(r["d"] for r in recs if r["kind"] == KIND_DECLARE),
        resolutions_digest=resolutions.digest, snapshot_head_seq=sv.head_seq)
