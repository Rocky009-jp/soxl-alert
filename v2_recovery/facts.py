"""Fixed facts for the S3-A rule functions that do not come from one S1 Snapshot (S3-B-2, API-1).

FixedApply / FixedFacts hold what the rule functions read about the saved APPLY records, declarations and segment
boundaries; LedgerContext is the checked-input bundle built from them (the counterpart of project.Ctx for facts that
are not an S1 Snapshot and a ResolutionSet). Nothing here reads a ledger rule from the market: no strategy formula,
threshold or state transition is written in this module.

project.apply_records / check_versions / final_checks / resolve_core and commands.check_commands take a context `ctx`
that is a project.Ctx or a LedgerContext. `ctx.sv` is a validate.SnapshotView or a FixedFacts; the functions read only
these names of it: applies, by_seq, apply_days, fixed_fps, decision_cols, latest_apply_day, head_seq.
Not re-exported by v2_recovery.__init__.
"""
import copy

from v2_core.errors import CoreError, InputError
from v2_core.fixture import parse_iso_date
from v2_core.observations import parse_observation
from v2_core.sessions import SessionList
from v2_persistence.errors import PersistenceError
from v2_persistence.events import session_dict

from .common import is_date, is_hex64, is_int, same
from .ledger import copy_sessions, ledger_digest, parse_ledger, sessions_digest
from .project import slice_check

_SESSION_KEYS = frozenset(["date", "open_at", "close_at", "confirmed"])
_APPLY_PART_KEYS = frozenset(["seq", "event_hash", "d", "decision", "context", "skipped"])
_DECLARE_PART_KEYS = frozenset(["seq", "event_hash", "d", "context"])
_BOUNDARY_PART_KEYS = frozenset(["date", "session"])


def _invalid(rule="shape"):
    return PersistenceError("facts_invalid", "facts", rule=rule)


def _canonical_sessions(items, minimum):
    """A list of session dicts in canonical form (as session_dict would write it) and its SessionList."""
    if not isinstance(items, list) or len(items) < minimum:
        raise _invalid()
    for e in items:
        if not isinstance(e, dict) or set(e) != _SESSION_KEYS:
            raise _invalid()
    try:
        sl = SessionList.from_dicts(copy.deepcopy(items))
    except InputError:
        raise _invalid() from None
    if not same([session_dict(s) for s in sl.sessions], items):
        raise _invalid()
    return sl


class _ReadOnlyMap:
    """A read-only view of a dict (no assignment, deletion, pop or clear). Values are immutable FixedApply objects."""

    __slots__ = ("_d",)

    def __init__(self, d):
        object.__setattr__(self, "_d", d)

    def __setattr__(self, name, value):
        raise AttributeError("read-only mapping")

    def __delattr__(self, name):
        raise AttributeError("read-only mapping")

    def __getitem__(self, key):
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __contains__(self, key):
        return key in self._d

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def keys(self):
        return tuple(self._d)

    def values(self):
        return tuple(self._d.values())

    def items(self):
        return tuple(self._d.items())


class FixedApply:
    """One saved APPLY as the rule functions read it. record_id and fingerprint are computed here from the saved
    decision (parse_observation), never taken from the caller. Immutable: attributes cannot be assigned or deleted, and
    every structured accessor (context, stored_sessions, decision_cols) returns an independent copy."""

    __slots__ = ("_seq", "_event_hash", "_d", "_context", "_sessions", "_skipped", "_record_id", "_fingerprint",
                 "_decision")

    def __init__(self, part):
        if not isinstance(part, dict) or set(part) != _APPLY_PART_KEYS:
            raise _invalid()
        seq, event_hash, d = part["seq"], part["event_hash"], part["d"]
        if not is_int(seq) or seq < 1 or not is_hex64(event_hash) or not is_date(d):
            raise _invalid()
        skipped = part["skipped"]
        if (not isinstance(skipped, (list, tuple)) or not all(is_date(x) for x in skipped)
                or len(set(skipped)) != len(skipped)):
            raise _invalid()
        context = part["context"]
        sl = _canonical_sessions(context, 2)
        if context[-2]["date"] != d:
            raise _invalid()
        decision = part["decision"]
        if not isinstance(decision, dict):
            raise _invalid()
        try:
            obs = parse_observation(copy.deepcopy(decision))
        except (CoreError, OverflowError):
            raise _invalid() from None
        if obs.role != "decision" or obs.status != "observed" or obs.target_date != d:
            raise _invalid()
        for name, value in (("_seq", seq), ("_event_hash", event_hash), ("_d", d),
                            ("_context", copy.deepcopy(context)), ("_sessions", tuple(sl.sessions)),
                            ("_skipped", tuple(skipped)), ("_record_id", obs.record_id),
                            ("_fingerprint", obs.fingerprint()), ("_decision", copy.deepcopy(decision))):
            object.__setattr__(self, name, value)

    def __setattr__(self, name, value):
        raise AttributeError("FixedApply is immutable")

    def __delattr__(self, name):
        raise AttributeError("FixedApply is immutable")

    seq = property(lambda self: self._seq)
    event_hash = property(lambda self: self._event_hash)
    d = property(lambda self: self._d)
    skipped = property(lambda self: self._skipped)
    record_id = property(lambda self: self._record_id)
    fingerprint = property(lambda self: self._fingerprint)

    @property
    def context(self):
        return copy.deepcopy(self._context)

    @property
    def stored_sessions(self):
        """A new SessionList of the saved range on every read (its sessions are immutable values)."""
        return SessionList(self._sessions)

    def decision_cols(self):
        return copy.deepcopy(self._decision)


class FixedFacts:
    """The checked facts of one effective history: every effective APPLY (all segments, in chain order), every
    effective declaration, the boundary sessions of every segment and the head seq. Build only with from_parts.

    Immutable: attributes cannot be assigned or deleted. applies is a tuple of immutable FixedApply, by_seq a read-only
    mapping of them, apply_days / fixed_fps are frozensets, and declares / boundaries return independent copies."""

    __slots__ = ("_applies", "_by_seq", "_apply_days", "_fixed_fps", "_declares", "_boundaries", "_boundary_day",
                 "_head_seq", "_latest_day")

    def __init__(self, *_args, **_kwargs):
        raise TypeError("use FixedFacts.from_parts")

    def __setattr__(self, name, value):
        raise AttributeError("FixedFacts is immutable")

    def __delattr__(self, name):
        raise AttributeError("FixedFacts is immutable")

    @classmethod
    def from_parts(cls, applies, declares, boundaries, boundary_day, head_seq):
        """Shape checks only: ints (not bool), hashes, dates, canonical session dicts, context[-2].date == d and an
        observable decision. A problem is facts_invalid. The values are copied; the caller's objects are not kept."""
        if (not isinstance(applies, (list, tuple)) or not isinstance(declares, (list, tuple))
                or not isinstance(boundaries, (list, tuple)) or not boundaries):
            raise _invalid()
        if not is_int(head_seq) or head_seq < 0 or not is_date(boundary_day):
            raise _invalid()
        fixed = [FixedApply(p) for p in applies]
        seqs = [ap.seq for ap in fixed]
        if seqs != sorted(set(seqs)) or any(s > head_seq for s in seqs):
            raise _invalid()
        decl = []
        for p in declares:
            if not isinstance(p, dict) or set(p) != _DECLARE_PART_KEYS:
                raise _invalid()
            if not is_int(p["seq"]) or p["seq"] < 1 or not is_hex64(p["event_hash"]) or not is_date(p["d"]):
                raise _invalid()
            _canonical_sessions(p["context"], 3)
            if len(p["context"]) != 3 or p["context"][1]["date"] != p["d"]:
                raise _invalid()
            decl.append({"seq": p["seq"], "event_hash": p["event_hash"], "d": p["d"],
                         "context": copy.deepcopy(p["context"])})
        if len({x["seq"] for x in decl}) != len(decl) or any(x["seq"] > head_seq for x in decl):
            raise _invalid()
        bounds = []
        for p in boundaries:
            if not isinstance(p, dict) or set(p) != _BOUNDARY_PART_KEYS or not is_date(p["date"]):
                raise _invalid()
            sl = _canonical_sessions([p["session"]], 1)
            if sl.sessions[0].date != p["date"]:
                raise _invalid()
            bounds.append({"date": p["date"], "session": copy.deepcopy(p["session"])})
        if bounds[-1]["date"] != boundary_day:
            raise _invalid()
        obj = object.__new__(cls)
        days = frozenset(ap.d for ap in fixed)
        for name, value in (("_applies", tuple(fixed)), ("_by_seq", {ap.seq: ap for ap in fixed}),
                            ("_apply_days", days), ("_fixed_fps", frozenset(ap.fingerprint for ap in fixed)),
                            ("_declares", decl), ("_boundaries", bounds), ("_boundary_day", boundary_day),
                            ("_head_seq", head_seq), ("_latest_day", max(days) if days else None)):
            object.__setattr__(obj, name, value)
        return obj

    applies = property(lambda self: self._applies)
    by_seq = property(lambda self: _ReadOnlyMap(self._by_seq))
    apply_days = property(lambda self: self._apply_days)
    fixed_fps = property(lambda self: self._fixed_fps)
    declares = property(lambda self: copy.deepcopy(self._declares))
    boundaries = property(lambda self: copy.deepcopy(self._boundaries))
    boundary_day = property(lambda self: self._boundary_day)
    head_seq = property(lambda self: self._head_seq)
    latest_day = property(lambda self: self._latest_day)

    def latest_apply_day(self, upto_seq):
        """The later of the current segment's boundary and the latest APPLY day with seq <= upto_seq. Older segments
        end at or before the current boundary (the restart floor), so they never raise the value."""
        return max([self._boundary_day] + [ap.d for ap in self._applies if ap.seq <= upto_seq])

    def decision_cols(self, seq):
        return self._by_seq[seq].decision_cols()


class LedgerContext:
    """All checked inputs of one call over FixedFacts, copied once at the start (the counterpart of project.Ctx).

    Order: facts type -> sessions -> check_d (date, after the boundary, not before the latest APPLY, in sessions,
    confirmed, next and previous present) -> every boundary session equal to the injected sessions -> the saved
    session range of every APPLY and declaration -> every ledger row on its own."""

    def __init__(self, facts, sessions, raw_observations, check_d):
        if not isinstance(facts, FixedFacts):
            raise _invalid("type")
        self.sv = facts
        self.facts = facts
        self.sl = copy_sessions(sessions)
        self.check_d = check_d
        self._check_check_d()
        self._check_boundaries()
        for ap in facts.applies:
            slice_check(self.sl, ap.context, ap.d)
        for dec in facts.declares:
            slice_check(self.sl, dec["context"], dec["d"])
        self.rows = parse_ledger(raw_observations)
        self.ledger_digest = ledger_digest(self.rows)
        self.sessions_digest = sessions_digest(self.sl)
        self.all_by_fp = {}
        for r in self.rows:
            self.all_by_fp.setdefault(r.fp, r)

    @classmethod
    def from_facts(cls, facts, sessions, raw_observations, check_d):
        return cls(facts, sessions, raw_observations, check_d)

    def _check_check_d(self):
        d, facts, sl = self.check_d, self.facts, self.sl
        parse_iso_date(d, "target_session_date")
        if not d > facts.boundary_day:
            raise PersistenceError("target_not_after_boundary", "target_session_date")
        if facts.latest_day is not None and d < facts.latest_day:
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

    def _check_boundaries(self):
        """Every segment's boundary session against the same day of the injected sessions (full equality)."""
        for b in self.facts.boundaries:
            now = self.sl.get(b["date"])
            if now is None:
                raise PersistenceError("session_context_missing", "sessions", detail=b["date"])
            if not same(session_dict(now), b["session"]):
                raise PersistenceError("session_context_mismatch", "sessions", detail=b["date"])
