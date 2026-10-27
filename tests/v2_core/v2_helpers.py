"""Test helpers. Synthetic sessions/times are not a market calendar. Network is blocked on import."""
import csv
import os
import socket
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from v2_core.fixture import MarketRow, load_research_fixture
from v2_core.sessions import Session, SessionList

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE_DIR = os.path.join(ROOT, "research", "SOXL_audit_20261023", "data")
SIGNALS_CSV = os.path.join(ROOT, "research", "SOXL_audit_20261023", "signals.csv")
TZ = timezone(timedelta(hours=-5))


def _blocked(*_a, **_k):
    raise RuntimeError("network is blocked in v2_core tests")


class _BlockedSocket(object):
    def __init__(self, *a, **k):
        _blocked()


socket.socket = _BlockedSocket          # no sockets can be created in this test process
socket.create_connection = _blocked


@lru_cache(maxsize=None)
def fixture():
    return load_research_fixture(FIXTURE_DIR)


def read_signals_csv():
    with open(SIGNALS_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def make_sessions(dates, confirmed=True):
    """Synthetic session list: open 09:30, close 16:00 at a fixed -05:00 offset. Not a real calendar."""
    out = []
    for d in dates:
        y, m, dd = (int(x) for x in d.split("-"))
        out.append(Session(d, datetime(y, m, dd, 9, 30, tzinfo=TZ), datetime(y, m, dd, 16, 0, tzinfo=TZ), confirmed))
    return SessionList(out)


def obs(record_id, d, value, role="decision", status="observed", hour=20):
    """An observation made on the evening of D (inside the decision window: after close(D), before next open)."""
    y, m, dd = (int(x) for x in d.split("-"))
    at = datetime(y, m, dd, hour, 0, tzinfo=TZ).isoformat()
    return {
        "record_id": record_id, "observation_status": status, "observation_role": role,
        "current_fg_value": value if status == "observed" else "",
        "observed_at_iso8601": at if status == "observed" else "",
        "target_us_session_date": d,
    }


class StubSeries(object):
    """Hand-written market rows for the condition tables (instead of reverse-engineering prices)."""

    def __init__(self, rows):
        self.rows = {r.date: r for r in rows}
        self.dates = sorted(self.rows)
        self.meta = {"price_definition": "adj_close_total_return",
                     "soxl_close_definition": "close_split_adjusted_not_dividend_adjusted"}
        self.closes = {}

    def through(self, d):
        return StubSeries([r for r in self.rows.values() if r.date <= d])._copy_closes(self)

    def _copy_closes(self, other):
        self.closes = dict(other.closes)
        return self

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
        from decimal import Decimal
        v = self.closes.get(d)
        return None if v is None else Decimal(str(v))

    def description(self):
        d = dict(self.meta)
        d.update({"rows": len(self.dates), "first_date": self.dates[0], "last_date": self.dates[-1]})
        return d


def row(d, soxx=110.0, sma=100.0, rsi=50.0, shd=-1.0, prev_rsi=49.0):
    return MarketRow(d, soxx, sma, rsi, shd, prev_rsi)


WEAK = dict(soxx=90.0)                           # SOXX below SMA200: no market-side NORMAL / TREND
NORMAL_OK = dict(soxx=110.0, rsi=50.0, shd=-1.0, prev_rsi=49.0)   # market-side NORMAL met, no RSI cross
TREND_OK = dict(soxx=110.0, rsi=56.0, shd=1.0, prev_rsi=54.0)      # RSI crosses 55 upward, SHD not negative
