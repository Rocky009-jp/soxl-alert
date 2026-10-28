"""Visually observed F&G records (decision / supplemental) and decision selection for a target session D.

Never replaces a missing observation with 0, a previous value, or a historical proxy.
"""
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .errors import ConflictError, InputError
from .fixture import parse_iso_date
from .sessions import parse_aware_datetime

# English letters/digits first, then letters, digits, "." "_" "-"; at most 64 characters. Matched with fullmatch
# (a "$" anchor would accept a trailing newline). Keeps URLs, spaces and other free text out of saved state and logs.
RECORD_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

ROLES = ("decision", "supplemental")
STATUSES = ("observed", "not_checked")


@dataclass(frozen=True)
class Observation:
    record_id: str
    status: str
    role: str
    value: Optional[float]
    observed_at: Optional[datetime]
    target_date: Optional[str]

    def fingerprint(self):
        payload = json.dumps(
            [self.record_id, self.status, self.role, self.value,
             self.observed_at.astimezone(timezone.utc).isoformat() if self.observed_at else None,
             self.target_date],
            ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_valid_record_id(value):
    return isinstance(value, str) and RECORD_ID_PATTERN.fullmatch(value) is not None


def _parse_value(raw):
    if isinstance(raw, bool):
        raise InputError("fg_value_invalid", "current_fg_value")
    if isinstance(raw, (int, float)):
        v = float(raw)
    elif isinstance(raw, str):
        try:
            v = float(raw.strip())
        except ValueError:
            raise InputError("fg_value_invalid", "current_fg_value")
    else:
        raise InputError("fg_value_invalid", "current_fg_value")
    if not math.isfinite(v) or v < 0 or v > 100:
        raise InputError("fg_value_invalid", "current_fg_value")
    return v


def _blank(x):
    return x is None or (isinstance(x, str) and x.strip() == "")


def parse_observation(raw):
    if not isinstance(raw, dict):
        raise InputError("observation_invalid", "observation")
    record_id = raw.get("record_id")
    if not is_valid_record_id(record_id):
        raise InputError("record_id_invalid", "record_id")
    status = raw.get("observation_status")
    role = raw.get("observation_role")
    if status not in STATUSES:
        raise InputError("status_unknown", "observation_status")
    if role not in ROLES:
        raise InputError("role_unknown", "observation_role")
    if status == "not_checked":
        if not _blank(raw.get("current_fg_value")) or not _blank(raw.get("observed_at_iso8601")):
            raise InputError("not_checked_has_value", "observation")
        target = raw.get("target_us_session_date")
        target = None if _blank(target) else parse_iso_date(target, "target_us_session_date")
        return Observation(record_id, status, role, None, None, target)
    value = _parse_value(raw.get("current_fg_value"))
    observed_at = parse_aware_datetime(raw.get("observed_at_iso8601"), "observed_at_iso8601")
    target = raw.get("target_us_session_date")
    if _blank(target):
        raise InputError("target_session_missing", "target_us_session_date")
    target = parse_iso_date(target, "target_us_session_date")
    return Observation(record_id, status, role, value, observed_at, target)


def _parse_all(raw_observations):
    if not isinstance(raw_observations, (list, tuple)):
        raise InputError("observation_invalid", "observations")
    parsed = [parse_observation(r) for r in raw_observations]
    seen = {}
    for o in parsed:
        prior = seen.get(o.record_id)
        if prior is not None:
            if prior.fingerprint() != o.fingerprint():
                raise ConflictError("record_id_conflict", "record_id")
            # the same record written with another UTC offset: keep one deterministically
            if o.observed_at is not None and o.observed_at.isoformat() >= prior.observed_at.isoformat():
                continue
        seen[o.record_id] = o
    return list(seen.values())


def _in_window(o, session, nxt):
    return o.observed_at is not None and session.close_at <= o.observed_at < nxt.open_at


def select_decision(raw_observations, sessions, d):
    """Return the single decision observation for D, or None.

    - Every record must parse; invalid records are INPUT_ERROR (never silently 'unobserved').
    - A decision must be observed at or after close(D) and before open(next(D)).
    - A decision observed inside D's window must target D; otherwise INPUT_ERROR (target_mismatch).
    - Identical re-submission (same content, any UTC offset) is a no-op. Two different decisions for D, or one
      record_id with different content, is CONFLICT regardless of list order.
    - supplemental records never replace the decision.
    """
    records = _parse_all(raw_observations)
    session = sessions.get(d)
    nxt = sessions.next(d)
    decided = [o for o in records if o.role == "decision" and o.status == "observed"]
    if session is not None and nxt is not None:
        for o in decided:
            if o.target_date != d and _in_window(o, session, nxt):
                raise InputError("target_mismatch", "target_us_session_date")
    decisions = [o for o in decided if o.target_date == d]
    for o in decisions:
        if session is None or nxt is None:
            raise InputError("next_session_missing", "sessions")
        if not _in_window(o, session, nxt):
            raise InputError("decision_outside_window", "observed_at_iso8601")
    if len(decisions) > 1:
        raise ConflictError("decision_conflict", "observation_role")
    return decisions[0] if decisions else None


def first_unprocessed_session(raw_observations, sessions, after_date, d):
    """Earliest session strictly between `after_date` and D that has a valid decision in the input, or None.

    Used to refuse processing D before an earlier, already-observed session (no automatic back-processing).
    A decision counts only if it targets that session and was observed inside that session's window.
    """
    records = _parse_all(raw_observations)
    for sess in sessions.sessions:
        if not (after_date < sess.date < d):
            continue
        nxt = sessions.next(sess.date)
        if nxt is None:
            continue
        for o in records:
            if (o.role == "decision" and o.status == "observed" and o.target_date == sess.date
                    and _in_window(o, sess, nxt)):
                return sess.date
    return None
