"""Helpers for the v2_persistence tests. Synthetic sessions and rows are not a market calendar.

Sockets are disabled on import, as in the v2_core tests. Nothing here reads a clock or a file of its own.
"""
import copy
import os
import socket
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from v2_core.fixture import MarketRow  # noqa: E402
from v2_core.sessions import Session, SessionList  # noqa: E402
from v2_persistence.codec import Snapshot, compute_event_hash  # noqa: E402
from v2_persistence.events import snapshot_dict  # noqa: E402
from v2_persistence.recompute import validate_snapshot  # noqa: E402
from v2_persistence.runner import make_genesis, prepare_day  # noqa: E402
from v2_persistence.store import MemoryStore  # noqa: E402

TZ = timezone(timedelta(hours=-5))
FIXTURE_DIR = os.path.join(ROOT, "research", "SOXL_audit_20261023", "data")


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_persistence tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket
socket.create_connection = _blocked


def weekdays(start="2026-03-02", n=40):
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DATES = weekdays()


def make_session(d, confirmed=True, open_h=9, close_h=16):
    y, m, dd = (int(x) for x in d.split("-"))
    return Session(d, datetime(y, m, dd, open_h, 30, tzinfo=TZ), datetime(y, m, dd, close_h, 0, tzinfo=TZ), confirmed)


def make_sessions(dates=None, unconfirmed=(), overrides=None):
    out = []
    for d in (DATES if dates is None else dates):
        s = make_session(d, confirmed=d not in unconfirmed)
        if overrides and d in overrides:
            s = overrides[d](s)
        out.append(s)
    return SessionList(out)


def obs(record_id, d, value, role="decision", status="observed", hour=20, tz=TZ):
    """An observation made on the evening of D, inside D's decision window."""
    y, m, dd = (int(x) for x in d.split("-"))
    at = datetime(y, m, dd, hour, 0, tzinfo=tz).isoformat()
    return {"record_id": record_id, "observation_status": status, "observation_role": role,
            "current_fg_value": value if status == "observed" else "",
            "observed_at_iso8601": at if status == "observed" else "",
            "target_us_session_date": d}


class StubSeries(object):
    """Hand-written market rows (same shape as the v2_core tests' stub)."""

    def __init__(self, rows):
        self.rows = {r.date: r for r in rows}
        self.dates = sorted(self.rows)
        self.meta = {"price_definition": "adj_close_total_return",
                     "soxl_close_definition": "close_split_adjusted_not_dividend_adjusted"}

    def through(self, d):
        return StubSeries([r for r in self.rows.values() if r.date <= d])

    def has(self, d):
        return d in self.rows

    def previous_date(self, d):
        if d not in self.rows:
            return None
        i = self.dates.index(d)
        return self.dates[i - 1] if i else None

    def row(self, d):
        from v2_core.errors import InputError
        if d not in self.rows:
            raise InputError("target_row_missing", "market")
        return self.rows[d]

    def soxl_close(self, d):
        return None

    def description(self):
        d = dict(self.meta)
        d.update({"rows": len(self.dates), "first_date": self.dates[0], "last_date": self.dates[-1]})
        return d


def row(d, soxx=110.0, sma=100.0, rsi=50.0, shd=-1.0, prev_rsi=49.0):
    return MarketRow(d, soxx, sma, rsi, shd, prev_rsi)


def make_series(dates=None, per_date=None):
    per_date = per_date or {}
    return StubSeries([row(d, **per_date.get(d, {})) for d in (DATES if dates is None else dates)])


class World(object):
    """Series, sessions and a ledger (a plain list of raw rows) for one scenario, plus a MemoryStore."""

    def __init__(self, start_idx=0, per_date=None, unconfirmed=()):
        self.start_after = DATES[start_idx]
        self.sessions = make_sessions(unconfirmed=unconfirmed)
        self.series = make_series(per_date=per_date)
        self.ledger = []
        self.store = MemoryStore()
        self.store.initialize(make_genesis(self.start_after, self.sessions))

    def snap(self):
        return self.store.read()

    def prepare(self, d, snapshot=None):
        return prepare_day(snapshot if snapshot is not None else self.snap(), d, self.series, self.sessions,
                           self.ledger)

    def apply(self, d, value=None, record_id=None):
        """Observe F&G for D (when value is given), prepare and commit. Returns the PrepareResult."""
        if value is not None:
            self.ledger.append(obs(record_id or ("R-" + d), d, value))
        res = self.prepare(d)
        if res.plan is not None:
            self.store.commit(res.plan)
        return res


def rehash(events, fix_chain=True):
    """Rebuild a Snapshot from raw event dicts: recompute parent links, event hashes and the header."""
    events = copy.deepcopy(events)
    for i, ev in enumerate(events):
        if fix_chain and i > 0:
            ev["parent_hash"] = events[i - 1]["event_hash"]
        ev["event_hash"] = compute_event_hash(ev)
    return Snapshot.from_dict(snapshot_dict(events))


def tampered(snapshot, mutate, rehash_events=True, fix_chain=True):
    """Apply mutate(events) to a copy of the events; rehash (default) so that only the content is wrong."""
    events = snapshot.events
    mutate(events)
    if rehash_events:
        return rehash(events, fix_chain=fix_chain)
    d = snapshot.to_dict()
    d["events"] = events
    return Snapshot.from_dict(d)


def check(snapshot):
    return validate_snapshot(snapshot)
