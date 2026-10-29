"""The injected ledger as six normalized columns, and the digests that bind a plan to its inputs.

Every row goes through the core's parse_observation on its own. Rows are never matched by record_id alone: the core's
Observation.fingerprint() is the only identity used here.
"""
import copy

from v2_core.errors import InputError
from v2_core.observations import parse_observation
from v2_core.sessions import SessionList
from v2_persistence.codec import canonical_json, sha256_text, utc_text
from v2_persistence.events import session_dict

LEDGER_KEYS = ("record_id", "observation_status", "observation_role", "current_fg_value", "observed_at_iso8601",
               "target_us_session_date")


class Row:
    """One parsed ledger row: the core Observation, its fingerprint and the normalized six columns."""
    __slots__ = ("obs", "fp", "cols")

    def __init__(self, obs):
        self.obs = obs
        self.fp = obs.fingerprint()
        self.cols = {
            "record_id": obs.record_id, "observation_status": obs.status, "observation_role": obs.role,
            "current_fg_value": obs.value,
            "observed_at_iso8601": None if obs.observed_at is None else utc_text(obs.observed_at, "observed_at_iso8601"),
            "target_us_session_date": obs.target_date}


def parse_row(raw):
    if not isinstance(raw, dict):
        raise InputError("observation_invalid", "observation")
    six = {k: copy.deepcopy(raw[k]) for k in LEDGER_KEYS if k in raw}
    try:
        return Row(parse_observation(six))
    except OverflowError:
        raise InputError("fg_value_invalid", "current_fg_value") from None


def parse_ledger(raw_observations):
    """Independent six-column copy of every row, each parsed on its own (a conflict between versions is not decided here)."""
    if not isinstance(raw_observations, (list, tuple)):
        raise InputError("observation_invalid", "observations")
    return [parse_row(r) for r in raw_observations]


def ledger_digest(rows):
    """Order-free, count-preserving digest of the normalized six columns."""
    return sha256_text(canonical_json(sorted(canonical_json(r.cols) for r in rows)))


def copy_sessions(sessions):
    if not isinstance(sessions, SessionList):
        raise InputError("sessions_invalid", "sessions")
    return SessionList(list(sessions.sessions))


def sessions_digest(sl):
    """Whole-list digest used only to bind a plan to the sessions it was made with."""
    return sha256_text(canonical_json([session_dict(s) for s in sl.sessions]))


def in_window(obs, session, nxt):
    return obs.observed_at is not None and session.close_at <= obs.observed_at < nxt.open_at
