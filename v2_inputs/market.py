"""The market series: the daily chart (Yahoo chart v8) JSON bytes of a fetch function that the caller passes in, interpreted
here; and the series pinned per target day on a ref of the git remote (market.json), so that a later run of the same day
reads the same bytes, whatever the source revises (U-07: a revision only reaches the target days after it)."""
import datetime as dt
import hashlib
import json
import math

from v2_core.errors import InputError
from v2_core.fixture import PRICE_DEF_SOXL_CLOSE, PRICE_DEF_SOXX, MarketSeries
from v2_git_store import OK

from .xnys import ny_offset

SYMBOLS = ("SOXX", "SPY", "IEF", "SOXL")
PREHISTORY_START = "2010-02-11"
PRICE_MAX = 1000000
CLOSE_MARGIN = dt.timedelta(minutes=60)
NAME = "market.json"
SCHEMA = "v2_inputs.market.1"
SOURCE = "yahoo_chart_v8"
BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"


def _price(x):
    """A finite number above 0 and below PRICE_MAX (a bool is not a number)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    if isinstance(x, float) and not math.isfinite(x):
        return False
    return 0 < x < PRICE_MAX


def _iso_date(text):
    """True for a text that is exactly a calendar date YYYY-MM-DD."""
    if type(text) is not str:
        return False
    try:
        return dt.date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def chart_url(symbol, start, end):
    """The daily chart URL of one symbol from start to end (dates, 00:00 UTC). A pure function; the fetch function of the
    entry script (S4-E) uses it, load_inputs does not call it."""
    seconds = None
    if symbol in SYMBOLS and _iso_date(start) and _iso_date(end):
        seconds = [int(dt.datetime.combine(dt.date.fromisoformat(x), dt.time(0), dt.timezone.utc).timestamp())
                   for x in (start, end)]
    if seconds is None:
        raise InputError("input_args_invalid", "inputs")
    return "%s%s?period1=%d&period2=%d&interval=1d&events=div%%2Csplit&includeAdjustedClose=true" % (
        BASE_URL, symbol, seconds[0], seconds[1])


def _columns(data, symbol):
    """(timestamps, close, adjclose) of a response of the right shape, or None (no exception is raised in a handler)."""
    if type(data) is not bytes:
        return None
    try:
        result = json.loads(data.decode("utf-8"))["chart"]["result"][0]
        stamps = result["timestamp"]
        close = result["indicators"]["quote"][0]["close"]
        adjusted = result["indicators"]["adjclose"][0]["adjclose"]
        named = result["meta"]["symbol"]
    except (ValueError, KeyError, IndexError, TypeError, UnicodeDecodeError, AttributeError, RecursionError):
        return None
    if named != symbol or not (type(stamps) is list and type(close) is list and type(adjusted) is list):
        return None
    if not (len(stamps) == len(close) == len(adjusted)):
        return None
    return stamps, close, adjusted


def _day_of(stamp):
    """The New York date (YYYY-MM-DD) of a time in UTC seconds, or None for a time that is not an int or out of range."""
    if type(stamp) is not int:
        return None
    try:
        utc = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return (utc + ny_offset(utc.date())).date().isoformat()


def parse_chart(data, symbol, through=None):
    """{date: (close, adjclose)} of one symbol from PREHISTORY_START to `through` (the target D). A row after `through`
    (the bar of a session still open, or the separate live row of the same date) is dropped before any check: it is not
    pinned and not an error. A day with a null close or adjusted close has no row. A date twice (up to `through`) is a
    response of the wrong shape; a value that is not a finite number in (0, PRICE_MAX) is a bad value (the first date)."""
    columns = _columns(data, symbol)
    days = None
    if columns is not None:
        days = [_day_of(t) for t in columns[0]]
    if columns is None or None in days:
        raise InputError("input_market_response_invalid", "market")
    rows, seen, invalid = {}, set(), None
    for day, close, adjusted in zip(days, columns[1], columns[2]):
        if through is not None and day > through:
            continue
        if day in seen:
            raise InputError("input_market_response_invalid", "market")
        seen.add(day)
        if day < PREHISTORY_START or close is None or adjusted is None:
            continue
        if _price(close) and _price(adjusted):
            rows[day] = (float(close), float(adjusted))
        elif invalid is None or day < invalid:
            invalid = day
    if invalid is not None:
        raise InputError("input_market_value_invalid", "market", detail=invalid)
    return rows


def snapshot_bytes(through, by_symbol):
    """The canonical bytes of market.json: sorted keys, separators "," ":" and ASCII; the same content gives the same bytes."""
    symbols = {}
    for s in SYMBOLS:
        dates = sorted(d for d in by_symbol[s] if PREHISTORY_START <= d <= through)
        symbols[s] = {"dates": dates, "close": [by_symbol[s][d][0] for d in dates],
                      "adjclose": [by_symbol[s][d][1] for d in dates]}
    body = {"schema": SCHEMA, "through": through, "source": SOURCE, "symbols": symbols}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _snapshot(data):
    """(through, {symbol: {date: (close, adjclose)}}) of the bytes of a market.json, or None when they are not one."""
    try:
        body = json.loads(data.decode("ascii"))
        if body["schema"] != SCHEMA or body["source"] != SOURCE or not _iso_date(body["through"]):
            return None
        out = {}
        for s in SYMBOLS:
            entry = body["symbols"][s]
            dates, close, adjusted = entry["dates"], entry["close"], entry["adjclose"]
            if not (type(dates) is list and type(close) is list and type(adjusted) is list
                    and len(dates) == len(close) == len(adjusted)):
                return None
            if not all(_iso_date(d) for d in dates) or any(a >= b for a, b in zip(dates, dates[1:])):
                return None
            if dates and (dates[0] < PREHISTORY_START or dates[-1] > body["through"]):
                return None
            if not all(_price(c) and _price(a) for c, a in zip(close, adjusted)):
                return None
            out[s] = dict(zip(dates, zip(close, adjusted)))
        if PREHISTORY_START not in out["SOXX"]:
            return None
        return body["through"], out
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, AttributeError, RecursionError):
        return None


def read_snapshot(data):
    """(through, {symbol: {date: (close, adjclose)}}) of the bytes of a market.json; InputError(input_market_pin_invalid)
    when they are not one."""
    got = _snapshot(data) if type(data) is bytes else None
    if got is None:
        raise InputError("input_market_pin_invalid", "market")
    return got


def series_of(through, by_symbol, digest):
    """The core's MarketSeries of a pinned snapshot: the SOXX dates and adjusted close, SPY and IEF adjusted close (the
    dates where both exist), the SOXL close. input_manifest is the sha256 of market.json."""
    soxx = by_symbol["SOXX"]
    dates = sorted(d for d in soxx if PREHISTORY_START <= d <= through)
    spy = {d: v[1] for d, v in by_symbol["SPY"].items() if d <= through}
    ief = {d: v[1] for d, v in by_symbol["IEF"].items() if d <= through}
    soxl = {d: v[0] for d, v in by_symbol["SOXL"].items() if d <= through}
    meta = {"source": SOURCE + " (pinned)", "price_definition": PRICE_DEF_SOXX,
            "soxl_close_definition": PRICE_DEF_SOXL_CLOSE, "prehistory_start": PREHISTORY_START,
            "input_manifest": [{"file": NAME, "sha256": digest}]}
    return MarketSeries(dates, [soxx[d][1] for d in dates], spy, ief, set(spy) & set(ief), soxl_close=soxl, meta=meta)


class MarketPin(object):
    """Reads and writes market.json on refs/heads/<ref> through the Git of the store (the same work directory, so no new
    credential). A push is a fast-forward of a commit that replaces market.json, made on the head that was read."""

    def __init__(self, git, ref, clock):
        self._git, self._ref, self._clock = git, ref, clock
        self.head_after_pin = None

    def read(self):
        """(head SHA, through, {symbol: rows}, sha256 of the bytes) of the pinned snapshot, or four Nones when the ref does
        not exist. InputError(input_market_pin_invalid) when market.json is missing or not a snapshot."""
        head = self._git.fetch(self._ref)
        if head is None:
            return None, None, None, None
        data = self._git.blob(head, NAME)
        if data is None:
            raise InputError("input_market_pin_invalid", "market")
        through, rows = read_snapshot(data)
        return head, through, rows, hashlib.sha256(data).hexdigest()

    def pin(self, head, data, through):
        """Push a commit (parent = head, none for a new ref) that sets market.json to `data`. True only when the remote took
        it; a lost or unknown push is False (the caller reads the ref again)."""
        commit = self._git.commit_with(head, NAME, data, "v2 market through %s" % through, self._clock())
        self.head_after_pin = commit
        return self._git.push(commit, self._ref) == OK
