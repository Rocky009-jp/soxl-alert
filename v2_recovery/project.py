"""Projection of the ledger through a ResolutionSet: exclude by fingerprint, supplement a stored row only when needed,
refuse a version choice, then run the core's own selection on the final rows.

Order (fixed): Snapshot -> set structure and references -> explicit check_d and sessions -> every row parsed on its own
-> exclusion -> supplement -> version_selection -> final checks. The raw ledger, the Snapshot and the set are never
changed; the market state is never read for a rule or written.
"""
import copy
import json

from v2_core.errors import InputError
from v2_core.fixture import parse_iso_date
from v2_core.observations import parse_observation, select_decision
from v2_core.sessions import SessionList
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_persistence.events import project_context, session_dict

from .common import KIND_ACK, KIND_DECLARE, V_CHANGED, V_ROW_REMOVED
from .errors import resolution_invalid
from .ledger import Row, copy_sessions, ledger_digest, parse_ledger, sessions_digest
from .validate import SnapshotView, validate_set


class Ctx:
    """All checked inputs of one call, copied once at the start."""

    def __init__(self, snapshot, resolutions, sessions, raw_observations, check_d):
        self.sv = SnapshotView(snapshot)                                         # 1 Snapshot
        self.resolutions = resolutions
        self.records = validate_set(self.sv, resolutions)                        # 2 structure and references
        self.sl = copy_sessions(sessions)                                        # 3 check_d and sessions
        self.check_d = check_d
        self._check_check_d()
        self._check_sessions()
        self.rows = parse_ledger(raw_observations)                               # 4 every row on its own
        self.ledger_digest = ledger_digest(self.rows)
        self.sessions_digest = sessions_digest(self.sl)
        self.all_by_fp = {}
        for r in self.rows:
            self.all_by_fp.setdefault(r.fp, r)

    def _check_sessions(self):
        """The saved session ranges (every APPLY, every declaration) against the injected sessions, before any row."""
        for ap in self.sv.applies:
            slice_check(self.sl, ap.context, ap.d)
        for rec in self.records:
            if rec["kind"] == KIND_DECLARE:
                slice_check(self.sl, rec["session_context"], rec["d"])

    def _check_check_d(self):
        d, sv, sl = self.check_d, self.sv, self.sl
        parse_iso_date(d, "target_session_date")
        if not d > sv.start_after:
            raise PersistenceError("target_not_after_genesis", "target_session_date")
        latest = sv.v.state.as_of_d
        if latest is not None and d < latest:
            raise InputError("state_ahead_of_target", "state")
        session = sl.get(d)
        if session is None:
            raise InputError("target_not_in_sessions", "sessions")
        if not session.confirmed:
            raise InputError("target_unconfirmed", "sessions")
        if sl.next(d) is None:
            raise InputError("next_session_missing", "sessions")
        if sl.previous(d) is None:
            raise InputError("previous_session_missing", "sessions")


def stored_row(ctx, ref):
    """The saved decision of an APPLY as a Row. Its fingerprint must equal the reference."""
    row = Row(parse_observation(ctx.sv.decision_cols(ref["seq"])))
    if row.fp != ref["fingerprint"]:
        raise resolution_invalid("resolutions", "applied_ref")
    return row


def apply_records(ctx, records):
    """Exclusion by exact fingerprint, then a single supplement per APPLY when its row is missing after exclusion.

    Returns (remaining {fp: Row}, actually_excluded {fp}, supplemented [applied_ref]).
    """
    excl = set()
    for rec in records:
        excl.update(rec["record_fingerprints"])
    actually = {fp for fp in ctx.all_by_fp if fp in excl}
    remaining = {fp: r for fp, r in ctx.all_by_fp.items() if fp not in excl}
    supplemented, seen = [], set()
    for rec in records:
        if rec["kind"] == KIND_ACK and rec["variant"] in (V_CHANGED, V_ROW_REMOVED):
            ref = rec["applied_ref"]
            if ref["seq"] in seen:
                continue
            seen.add(ref["seq"])
            if ref["fingerprint"] not in remaining:
                remaining[ref["fingerprint"]] = stored_row(ctx, ref)
                supplemented.append(copy.deepcopy(ref))
    return remaining, actually, supplemented


def check_versions(ctx, remaining, actually, field):
    """A row that is excluded must not leave another version of its record_id in the final set, unless that version
    is the fixed decision of an S1 APPLY (CHANGED with the original still present, or a stored row supplemented)."""
    ids = {ctx.all_by_fp[fp].obs.record_id for fp in actually}
    for fp, r in remaining.items():
        if r.obs.record_id in ids and fp not in ctx.sv.fixed_fps:
            raise resolution_invalid(field, "version_selection")


def slice_check(sl, context, d):
    index = {s.date: i for i, s in enumerate(sl.sessions)}
    if any(e["date"] not in index for e in context):
        raise PersistenceError("session_context_missing", "sessions", detail=d)
    lo, hi = index[context[0]["date"]], index[context[-1]["date"]]
    current = [session_dict(s) for s in sl.sessions[lo:hi + 1]]
    if project_context(current) != project_context(context):
        raise PersistenceError("session_context_mismatch", "sessions", detail=d)


def final_checks(ctx, raw, records):
    """The S1 ledger checks for every APPLY, skipped session and declared day, then the core's selection for check_d.
    (The saved session ranges were compared with the injected sessions earlier, in Ctx.)"""
    sl = ctx.sl
    for ap in ctx.sv.applies:
        for sessions in (ap.stored_sessions, sl):
            chosen = select_decision(raw, sessions, ap.d)
            if chosen is None or chosen.record_id != ap.record_id or chosen.fingerprint() != ap.fingerprint:
                raise PersistenceError("ledger_mismatch", "observations", detail=ap.d)
    for ap in ctx.sv.applies:
        for sd in ap.skipped:
            if select_decision(raw, sl, sd) is not None:
                raise PersistenceError("late_observation", "observations", detail=sd)
    for rec in records:
        if rec["kind"] != KIND_DECLARE:
            continue
        stored = SessionList.from_dicts(rec["session_context"])
        for sessions in (stored, sl):
            if select_decision(raw, sessions, rec["d"]) is not None:
                raise PersistenceError("late_observation", "observations", detail=rec["d"])
    select_decision(raw, sl, ctx.check_d)


class EffectiveLedger:
    """The final six-column ledger handed to the core, with what was excluded and supplemented.

    Structured accessors return fresh copies. It is never printed with its rows.
    """

    __slots__ = ("_text", "_view")

    def __init__(self, rows, excluded, supplemented, ledger_digest_, resolutions_digest, check_d):
        view = {"rows": rows, "excluded_fingerprints": sorted(excluded), "supplemented": supplemented,
                "ledger_digest": ledger_digest_, "effective_digest": sha256_text(canonical_json(rows)),
                "resolutions_digest": resolutions_digest, "check_d": check_d}
        text = canonical_json(view)
        object.__setattr__(self, "_text", text)
        object.__setattr__(self, "_view", json.loads(text))

    def __setattr__(self, name, value):
        raise AttributeError("EffectiveLedger is immutable")

    def __delattr__(self, name):
        raise AttributeError("EffectiveLedger is immutable")

    def __eq__(self, other):
        return isinstance(other, EffectiveLedger) and self._text == other._text

    def __hash__(self):
        return hash(self._text)

    def __repr__(self):
        return "EffectiveLedger(rows=%d, excluded=%d, supplemented=%d)" % (
            len(self._view["rows"]), len(self._view["excluded_fingerprints"]), len(self._view["supplemented"]))

    @property
    def rows(self):
        return copy.deepcopy(self._view["rows"])

    def raw_observations(self):
        """Fresh six-column dicts, the only ledger prepare_day is given."""
        return copy.deepcopy(self._view["rows"])

    @property
    def excluded_fingerprints(self):
        return list(self._view["excluded_fingerprints"])

    @property
    def supplemented(self):
        return copy.deepcopy(self._view["supplemented"])

    @property
    def ledger_digest(self):
        return self._view["ledger_digest"]

    @property
    def effective_digest(self):
        return self._view["effective_digest"]

    @property
    def resolutions_digest(self):
        return self._view["resolutions_digest"]

    @property
    def check_d(self):
        return self._view["check_d"]


def resolve_core(ctx, records, resolutions_digest, field):
    remaining, actually, supplemented = apply_records(ctx, records)
    check_versions(ctx, remaining, actually, field)
    final = sorted((r.cols for r in remaining.values()), key=canonical_json)
    final_checks(ctx, copy.deepcopy(final), records)
    return EffectiveLedger(final, actually, supplemented, ctx.ledger_digest, resolutions_digest, ctx.check_d)


def resolve_observations(snapshot, resolutions, sessions, raw_observations, check_d):
    """Final ledger and the basis for it. Changes no market state and none of its inputs."""
    ctx = Ctx(snapshot, resolutions, sessions, raw_observations, check_d)
    return resolve_core(ctx, ctx.records, resolutions.digest, "resolutions")
