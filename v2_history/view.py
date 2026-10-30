"""Linear check of one chain view: S1 projection per segment, then the control-record rules (design 4.3, 6, 7.1).

A chain view is the list of records from GENESIS to some record, following effective parents. RECOVERY_RESTORE is
transparent inside a view (its effective parent is the previous element and its state_after is the same).

Pass A cuts the view at GENESIS / RESTART_UNKNOWN and re-attaches each segment's APPLY records to a fresh S1 history
(seq and parent hash only), which the unchanged S1 validate_snapshot recalculates. No rule, threshold or state formula
is written here. Pass B walks the view once and checks every control record against its ancestors only.
"""
from v2_core.errors import InputError
from v2_core.sessions import SessionList
from v2_core.state import MarketState
from v2_persistence.errors import PersistenceError
from v2_persistence.events import (make_apply_event, make_genesis_event, session_dict, snapshot_of)
from v2_persistence.recompute import validate_snapshot
from v2_recovery.common import is_requested_text, valid_request_id

from .common import basis_request_hash, is_date, is_hex64, is_int, same
from .errors import history_invalid
from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN, SCHEMA_MIGRATION

VARIANTS = ("ADDED", "CHANGED", "ROW_REMOVED", "LATE")
REASON_ACK = "ACKNOWLEDGE_LEDGER_CHANGE"
REASON_DECLARE = "MARK_SESSION_MISSING"
REASON_BATCH = "RESOLUTION_BATCH"
REASON_RESTART = "RESTART_UNKNOWN"

COMMAND_KEYS = frozenset(["kind", "variant", "d", "record_fingerprints", "applied_ref", "missing_ref"])
BASIS_KEYS = frozenset(["request_id", "commands", "check_d", "reason_code", "requested_at"])
RESTART_BASIS_KEYS = frozenset(["request_id", "resume_after", "check_d", "reason_code", "requested_at"])
FLOOR_KEYS = frozenset(["last_apply_d", "last_declared_d", "prev_boundary"])
_CONFIRMED_INPUT_KEYS = frozenset(["decision", "row", "prev_row", "prev_session_date", "session_context"])
_REQUEST_LEVEL = ("request_id", "request_hash", "request_basis", "command_count", "ledger_digest", "requested_at")


def _bad(rule):
    return history_invalid(rule)


def initial_state_dict():
    return MarketState.initial().to_dict()


class ApplyInfo:
    """What the control rules need from one validated APPLY (read-only by convention)."""
    __slots__ = ("seq", "event_hash", "d", "fingerprint", "skipped", "context")

    def __init__(self, rec, applied):
        self.seq = rec["seq"]
        self.event_hash = rec["event_hash"]
        self.d = rec["d"]
        self.fingerprint = applied.fingerprint
        self.skipped = list(applied.skipped)
        self.context = [dict(e) for e in applied.context]


class Segment:
    """GENESIS or RESTART_UNKNOWN and the APPLY records up to the next boundary."""
    __slots__ = ("kind", "seq", "date", "session", "applies", "infos")

    def __init__(self, kind, seq, date, session):
        self.kind, self.seq, self.date, self.session = kind, seq, date, session
        self.applies = []
        self.infos = []


class ViewSummary:
    __slots__ = ("segments", "latest_apply_d", "last_segment_declared")

    def __init__(self, segments, latest_apply_d, last_segment_declared):
        self.segments = segments
        self.latest_apply_d = latest_apply_d
        self.last_segment_declared = last_segment_declared

    @property
    def last_segment(self):
        return self.segments[-1]


def sessions_of(items, rule):
    """A list of session dicts that is in canonical form (as session_dict would write it)."""
    if not isinstance(items, list) or not items:
        raise _bad(rule)
    for e in items:
        if not isinstance(e, dict) or set(e) != {"date", "open_at", "close_at", "confirmed"}:
            raise _bad(rule)
    try:
        sl = SessionList.from_dicts(items)
    except InputError:
        raise _bad(rule) from None
    if not same([session_dict(s) for s in sl.sessions], items):
        raise _bad(rule)
    return sl


def check_boundary_session(session, date, rule):
    sl = sessions_of([session], rule)
    s = sl.sessions[0]
    if s.date != date or not s.confirmed:
        raise _bad(rule)


# --- commands (shape only) --------------------------------------------------------------------------------------
def normalize_command(cmd, origin_ns):
    """Shape and types of one stored command. origin_ns is 's3a' (migrated: resolution_seq/resolution_hash for a
    declaration reference) or 'v2' (seq/event_hash). Returns a fresh canonical dict; raises command_shape."""
    def bad():
        return _bad("command_shape")

    if not isinstance(cmd, dict) or set(cmd) != COMMAND_KEYS:
        raise bad()
    kind, variant, d = cmd["kind"], cmd["variant"], cmd["d"]
    if kind == ACK:
        if variant not in VARIANTS:
            raise bad()
    elif kind == DECLARE_MISSING:
        if variant is not None:
            raise bad()
    else:
        raise bad()
    if not is_date(d):
        raise bad()
    fps = cmd["record_fingerprints"]
    if not isinstance(fps, list) or not all(is_hex64(x) for x in fps) or len(set(fps)) != len(fps):
        raise bad()
    applied, missing = cmd["applied_ref"], cmd["missing_ref"]
    if applied is not None:
        if (not isinstance(applied, dict) or set(applied) != {"seq", "event_hash", "fingerprint"}
                or not is_int(applied["seq"]) or applied["seq"] < 1 or not is_hex64(applied["event_hash"])
                or not is_hex64(applied["fingerprint"])):
            raise bad()
        applied = {"seq": applied["seq"], "event_hash": applied["event_hash"], "fingerprint": applied["fingerprint"]}
    if missing is not None:
        if not isinstance(missing, dict):
            raise bad()
        seq_key, hash_key = ("resolution_seq", "resolution_hash") if origin_ns == "s3a" else ("seq", "event_hash")
        if missing.get("kind") == "APPLY" and set(missing) == {"kind", "seq", "event_hash"}:
            if not is_int(missing["seq"]) or missing["seq"] < 1 or not is_hex64(missing["event_hash"]):
                raise bad()
            missing = {"kind": "APPLY", "seq": missing["seq"], "event_hash": missing["event_hash"]}
        elif missing.get("kind") == DECLARE_MISSING and set(missing) == {"kind", seq_key, hash_key}:
            if not is_int(missing[seq_key]) or missing[seq_key] < 1 or not is_hex64(missing[hash_key]):
                raise bad()
            missing = {"kind": DECLARE_MISSING, seq_key: missing[seq_key], hash_key: missing[hash_key]}
        else:
            raise bad()
    if kind == DECLARE_MISSING and (applied is not None or missing is not None):
        raise bad()
    return {"kind": kind, "variant": variant, "d": d, "record_fingerprints": sorted(fps),
            "applied_ref": applied, "missing_ref": missing}


def reasons_for_commands(commands):
    kinds = {c["kind"] for c in commands}
    if kinds == {ACK}:
        return (REASON_ACK, REASON_BATCH)
    if kinds == {DECLARE_MISSING}:
        return (REASON_DECLARE, REASON_BATCH)
    return (REASON_BATCH,)


# --- pass A: segmentation and S1 projection ----------------------------------------------------------------------
def _segments(recs):
    segments = []
    for rec in recs:
        kind = rec["kind"]
        if kind == GENESIS:
            segments.append(Segment(GENESIS, rec["seq"], rec["start_after"], rec["boundary_session"]))
        elif kind == RESTART_UNKNOWN:
            if not is_date(rec["resume_after"]):
                raise _bad("restart_boundary")
            check_boundary_session(rec["boundary_session"], rec["resume_after"], "restart_boundary")
            segments.append(Segment(RESTART_UNKNOWN, rec["seq"], rec["resume_after"], rec["boundary_session"]))
        elif kind == APPLY:
            segments[-1].applies.append(rec)
    return segments


def project_segment(segment):
    """The S1 history of one segment (seq and parent hash re-attached), checked by the unchanged validate_snapshot."""
    events = [make_genesis_event(segment.date, segment.session)]
    for i, rec in enumerate(segment.applies, 1):
        ci = rec["confirmed_inputs"]
        if not isinstance(ci, dict) or set(ci) != _CONFIRMED_INPUT_KEYS:
            raise _bad("s1:confirmed_inputs_keys")
        try:
            ev = make_apply_event(i, events[-1]["event_hash"], rec["d"], ci, rec["skipped_sessions"],
                                  rec["transition_result"], rec["state_after"])
        except (KeyError, TypeError, IndexError, AttributeError, ValueError):
            raise _bad("s1:session_context") from None
        if ev["input_hash"] != rec["input_hash"]:
            raise _bad("s1:input_hash")
        events.append(ev)
    try:
        return validate_snapshot(snapshot_of(events))
    except PersistenceError as e:
        raise _bad("s1:%s" % (e.rule or e.code)) from None


# --- pass B: control records -----------------------------------------------------------------------------------
class _Walk:
    def __init__(self, recs, segments):
        self.recs = recs
        self.segments = segments
        self.requests = set()
        self.apply_by_seq = {}
        self.declare_by_seq = {}
        self.all_apply_days = {i.d for s in segments for i in s.infos}
        self.all_fixed = {i.fingerprint for s in segments for i in s.infos}
        self.seg_i = -1
        self.seg_applies = []        # ApplyInfo of the current segment so far
        self.seg_declares = []       # (d, context) of the current segment so far
        self.latest_apply_d = None   # over the whole view so far
        self.latest_declared_d = None
        self.apply_cursor = []       # per segment: next info index
        self.group_end = 0
        self.group_start = 0
        self.commands = None
        self.group_origin_ns = None

    # -- helpers
    def seg(self):
        return self.segments[self.seg_i]

    def claim_request(self, rid):
        if not valid_request_id(rid) or rid in self.requests:
            raise _bad("request_id")
        self.requests.add(rid)

    def frontier(self):
        """The latest of boundary / APPLY / declaration day in the current segment, and the session it came from."""
        seg = self.seg()
        best, session = seg.date, seg.session
        if self.seg_applies and self.seg_applies[-1].d > best:
            best, session = self.seg_applies[-1].d, self.seg_applies[-1].context[-2]
        if self.seg_declares and self.seg_declares[-1][0] > best:
            best, session = self.seg_declares[-1][0], self.seg_declares[-1][1][1]
        return best, session

    def check_d_ok(self, check_d, d):
        if not is_date(check_d) or not check_d > self.seg().date:
            raise _bad("check_d")
        if self.latest_apply_d is not None and not check_d >= self.latest_apply_d:
            raise _bad("check_d")
        if not is_date(d) or d > check_d:
            raise _bad("check_d")

    # -- groups
    def open_group(self, idx, rec):
        recs = self.recs
        count = rec["command_count"]
        if not is_int(count) or count < 1 or rec["command_index"] != 0 or idx + count > len(recs):
            raise _bad("batch")
        group = recs[idx:idx + count]
        for j, g in enumerate(group):
            if g["kind"] not in (ACK, DECLARE_MISSING) or not is_int(g["command_index"]) or g["command_index"] != j:
                raise _bad("batch")
            for key in _REQUEST_LEVEL:
                if not same(g[key], rec[key]):
                    raise _bad("batch")
            if (g["origin"] is None) != (rec["origin"] is None):
                raise _bad("batch")
        basis = rec["request_basis"]
        self.claim_request(rec["request_id"])
        if not isinstance(basis, dict) or set(basis) != BASIS_KEYS:
            raise _bad("request_basis")
        if basis["request_id"] != rec["request_id"]:
            raise _bad("request_basis")
        if not is_requested_text(basis["requested_at"]):
            raise _bad("requested_at")
        if basis["requested_at"] != rec["requested_at"]:
            raise _bad("requested_at")
        cmds = basis["commands"]
        if not isinstance(cmds, list) or not cmds:
            raise _bad("request_basis")
        ns = "s3a" if rec["origin"] is not None else "v2"
        norm = [normalize_command(c, ns) for c in cmds]
        if not same(norm, cmds):
            raise _bad("command_shape")
        if basis["reason_code"] not in reasons_for_commands(cmds):
            raise _bad("reason_code")
        if not is_hex64(rec["request_hash"]) or rec["request_hash"] != basis_request_hash(basis):
            raise _bad("request_hash")
        if len(cmds) != count:
            raise _bad("batch")
        if not is_hex64(rec["ledger_digest"]):
            raise _bad("ledger_digest")
        self.group_start, self.group_end, self.commands = idx, idx + count, cmds
        self.group_origin_ns = ns

    # -- records
    def record(self, idx, rec, parent_state):
        kind = rec["kind"]
        if kind == GENESIS:
            self.seg_i = 0
            self.apply_cursor = [0] * len(self.segments)
            return
        if kind == APPLY:
            cur = self.apply_cursor[self.seg_i]
            info = self.seg().infos[cur]
            self.apply_cursor[self.seg_i] = cur + 1
            self.apply_by_seq[rec["seq"]] = info
            self.seg_applies.append(info)
            if self.latest_apply_d is None or info.d > self.latest_apply_d:
                self.latest_apply_d = info.d
            return
        if kind in (ACK, DECLARE_MISSING):
            if idx >= self.group_end:
                self.open_group(idx, rec)
            self.resolution_record(idx, rec, parent_state)
            return
        if kind == RESTART_UNKNOWN:
            self.restart_record(rec, parent_state)
            return
        if kind == RECOVERY_RESTORE:
            if not same(rec["state_after"], parent_state):
                raise _bad("restore_state")
            self.claim_request(rec["request_id"])
            return
        if kind == SCHEMA_MIGRATION:
            if not same(rec["state_after"], parent_state):
                raise _bad("state_after")
            self.claim_request(rec["request_id"])
            return

    def resolution_record(self, idx, rec, parent_state):
        cmd = self.commands[idx - self.group_start]
        kind, variant, d = rec["kind"], rec["variant"], rec["d"]
        if variant is not None and variant not in VARIANTS:
            raise _bad("variant")
        if (kind != cmd["kind"] or variant != cmd["variant"] or d != cmd["d"]
                or not same(rec["record_fingerprints"], cmd["record_fingerprints"])):
            raise _bad("batch")
        if rec["origin"] is None and rec["replay_of"] is None:
            if not same(rec["applied_ref"], cmd["applied_ref"]) or not same(rec["missing_ref"], cmd["missing_ref"]):
                raise _bad("batch")
        if rec["reason_code"] != (REASON_ACK if kind == ACK else REASON_DECLARE):
            raise _bad("reason_code")
        self.check_d_ok(rec["request_basis"]["check_d"], d)
        fps = rec["record_fingerprints"]
        if (not isinstance(fps, list) or not all(is_hex64(x) for x in fps) or fps != sorted(set(fps))):
            raise _bad("fingerprints")
        if any(fp in self.all_fixed for fp in fps):
            raise _bad("exclude_applied")
        if kind == ACK:
            self.ack_record(rec, fps)
        else:
            self.declare_record(rec)
        if not same(rec["state_after"], parent_state):
            raise _bad("state_after")

    def ack_record(self, rec, fps):
        variant = rec["variant"]
        if rec["session_context"] is not None or rec["frontier_before"] is not None:
            raise _bad("session_context")
        if variant == "ROW_REMOVED":
            if fps:
                raise _bad("fingerprints")
        elif not fps:
            raise _bad("fingerprints")
        applied, missing = rec["applied_ref"], rec["missing_ref"]
        if variant == "LATE":
            if applied is not None:
                raise _bad("applied_ref")
            self.late_ref(rec, missing)
            return
        if missing is not None:
            raise _bad("missing_ref")
        if (not isinstance(applied, dict) or set(applied) != {"seq", "event_hash", "fingerprint"}
                or not is_int(applied["seq"])):
            raise _bad("applied_ref")
        info = self.apply_by_seq.get(applied["seq"])
        if (info is None or applied["event_hash"] != info.event_hash or applied["fingerprint"] != info.fingerprint
                or rec["d"] != info.d):
            raise _bad("applied_ref")

    def late_ref(self, rec, ref):
        if not isinstance(ref, dict) or not is_int(ref.get("seq")) or set(ref) != {"kind", "seq", "event_hash"}:
            raise _bad("missing_ref")
        d = rec["d"]
        if d in self.all_apply_days:
            raise _bad("missing_ref")
        if ref["kind"] == "APPLY":
            info = self.apply_by_seq.get(ref["seq"])
            if info is None or ref["event_hash"] != info.event_hash or d not in info.skipped:
                raise _bad("missing_ref")
        elif ref["kind"] == DECLARE_MISSING:
            dec = self.declare_by_seq.get(ref["seq"])
            if dec is None or ref["event_hash"] != dec[0] or dec[1] != d:
                raise _bad("missing_ref")
        else:
            raise _bad("missing_ref")

    def declare_record(self, rec):
        d = rec["d"]
        if rec["variant"] is not None:
            raise _bad("variant")
        if rec["applied_ref"] is not None:
            raise _bad("applied_ref")
        if rec["missing_ref"] is not None:
            raise _bad("missing_ref")
        if d in self.all_apply_days:
            raise _bad("declare_applied")
        frontier, session = self.frontier()
        ctx = rec["session_context"]
        if rec["frontier_before"] != frontier or not d > frontier:
            raise _bad("declare_frontier")
        sl = sessions_of(ctx, "session_context")
        if len(ctx) != 3 or ctx[0]["date"] != frontier or ctx[1]["date"] != d:
            raise _bad("session_context")
        if not sl.sessions[0].confirmed or not sl.sessions[1].confirmed or not same(ctx[0], session):
            raise _bad("session_context")
        self.declare_by_seq[rec["seq"]] = (rec["event_hash"], d)
        self.seg_declares.append((d, ctx))
        if self.latest_declared_d is None or d > self.latest_declared_d:
            self.latest_declared_d = d

    def restart_record(self, rec, parent_state):
        basis = rec["request_basis"]
        self.claim_request(rec["request_id"])
        if not isinstance(basis, dict) or set(basis) != RESTART_BASIS_KEYS:
            raise _bad("request_basis")
        resume = rec["resume_after"]
        if basis["request_id"] != rec["request_id"] or basis["resume_after"] != resume:
            raise _bad("request_basis")
        if not is_requested_text(basis["requested_at"]) or basis["requested_at"] != rec["requested_at"]:
            raise _bad("requested_at")
        if basis["reason_code"] != REASON_RESTART or rec["reason_code"] != REASON_RESTART:
            raise _bad("reason_code")
        if not is_hex64(rec["request_hash"]) or rec["request_hash"] != basis_request_hash(basis):
            raise _bad("request_hash")
        prev_boundary = self.seg().date
        expected = {"last_apply_d": self.latest_apply_d, "last_declared_d": self.latest_declared_d,
                    "prev_boundary": prev_boundary}
        floor = rec["floor"]
        if not isinstance(floor, dict) or set(floor) != FLOOR_KEYS or not same(floor, expected):
            raise _bad("restart_floor")
        if resume < max(v for v in expected.values() if v is not None):
            raise _bad("restart_floor")
        check_d = basis["check_d"]
        if not is_date(check_d) or resume > check_d:
            raise _bad("check_d")
        if same(parent_state, initial_state_dict()) and resume == prev_boundary:
            raise _bad("restart_noop")
        if not same(rec["state_after"], initial_state_dict()):
            raise _bad("state_after")
        self.seg_i += 1
        self.seg_applies = []
        self.seg_declares = []


def check_view(recs):
    """Check one chain view (a list of record dicts, GENESIS first). Returns a ViewSummary."""
    segments = _segments(recs)
    for seg in segments:
        applied = project_segment(seg).applies
        seg.infos = [ApplyInfo(rec, ap) for rec, ap in zip(seg.applies, applied)]
    walk = _Walk(recs, segments)
    parent_state = None
    for idx, rec in enumerate(recs):
        walk.record(idx, rec, parent_state)
        parent_state = rec["state_after"]
    if walk.group_end > len(recs):
        raise _bad("batch")
    days = [i.d for s in segments for i in s.infos] + [d for d in walk_declared_days(recs)]
    if len(days) != len(set(days)):
        raise _bad("d_unique")
    return ViewSummary(segments, walk.latest_apply_d, [d for d, _ctx in walk.seg_declares])


def walk_declared_days(recs):
    return [r["d"] for r in recs if r["kind"] == DECLARE_MISSING]
