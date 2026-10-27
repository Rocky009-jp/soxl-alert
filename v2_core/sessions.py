"""Injected session list: explicit dates, close/open times with time zone, confirmed flag.

There is no calendar library, clock or cron here. Callers pass the sessions.
"""
from dataclasses import dataclass
from datetime import datetime

from .errors import InputError
from .fixture import parse_iso_date


def parse_aware_datetime(text, field):
    if not isinstance(text, str) or not text:
        raise InputError("datetime_invalid", field)
    s = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise InputError("datetime_invalid", field)
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise InputError("datetime_missing_timezone", field)
    return dt


@dataclass(frozen=True)
class Session:
    date: str
    open_at: datetime
    close_at: datetime
    confirmed: bool


class SessionList:
    def __init__(self, sessions):
        self.sessions = list(sessions)
        previous = None
        for s in self.sessions:
            parse_iso_date(s.date, "sessions")
            if previous is not None and s.date <= previous.date:
                raise InputError("session_order_or_duplicate", "sessions")
            if not s.open_at < s.close_at:
                raise InputError("session_times_invalid", "sessions")
            if previous is not None and not previous.close_at < s.open_at:
                raise InputError("session_times_invalid", "sessions")
            previous = s
        self._index = {s.date: i for i, s in enumerate(self.sessions)}

    @classmethod
    def from_dicts(cls, items):
        out = []
        for it in items:
            if not isinstance(it, dict):
                raise InputError("session_item_invalid", "sessions")
            confirmed = it.get("confirmed")
            if not isinstance(confirmed, bool):
                raise InputError("session_confirmed_invalid", "sessions")
            out.append(Session(
                parse_iso_date(it.get("date"), "sessions"),
                parse_aware_datetime(it.get("open_at"), "sessions"),
                parse_aware_datetime(it.get("close_at"), "sessions"),
                confirmed,
            ))
        return cls(out)

    def get(self, d):
        i = self._index.get(d)
        return None if i is None else self.sessions[i]

    def previous(self, d):
        i = self._index.get(d)
        return None if i is None or i == 0 else self.sessions[i - 1]

    def next(self, d):
        i = self._index.get(d)
        return None if i is None or i + 1 >= len(self.sessions) else self.sessions[i + 1]

    def back(self, d, n):
        """The session n sessions before D (None if the list is too short)."""
        i = self._index.get(d)
        if i is None or i - n < 0:
            return None
        return self.sessions[i - n]
