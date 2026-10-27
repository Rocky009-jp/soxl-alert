"""Market input series: validation, pre-history metadata, cut at the target session D.

Only explicit fixture files or arrays are read. No fetching. Prices after D are never used.
"""
import bisect
import csv
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal

from .errors import InputError
from .indicators import rsi_wilder, shd_by_date, sma_running

PRICE_DEF_SOXX = "adj_close_total_return"
PRICE_DEF_SOXL_CLOSE = "close_split_adjusted_not_dividend_adjusted"


@dataclass(frozen=True)
class MarketRow:
    date: str
    soxx: float
    sma: float
    rsi: float
    shd: float
    prev_rsi: float


def parse_iso_date(text, field):
    try:
        if not isinstance(text, str):
            raise ValueError
        parsed = _date.fromisoformat(text)
    except ValueError:
        raise InputError("invalid_date", field)
    if parsed.isoformat() != text:
        raise InputError("invalid_date", field)
    return text


def validate_dates(dates, field):
    previous = None
    for d in dates:
        parse_iso_date(d, field)
        if previous is not None and d <= previous:
            raise InputError("date_order_or_duplicate", field)
        previous = d


def _finite_positive(x):
    return (not isinstance(x, bool)) and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def validate_prices(values, field):
    for x in values:
        if not _finite_positive(x):
            raise InputError("price_not_finite_positive", field)


def _git_blob_sha1(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class MarketSeries:
    """SOXX adjusted-close based series with Wilder RSI, SMA200 and SHD, plus optional SOXL raw close."""

    def __init__(self, dates, soxx, spy, ief, market_dates, soxl_close=None, meta=None):
        meta = dict(meta or {})
        if meta.get("price_definition") != PRICE_DEF_SOXX:
            raise InputError("price_definition_unknown", "meta")
        if soxl_close and meta.get("soxl_close_definition") != PRICE_DEF_SOXL_CLOSE:
            raise InputError("soxl_price_definition_unknown", "meta")
        validate_dates(dates, "dates")
        if len(soxx) != len(dates):
            raise InputError("series_misaligned", "soxx")
        validate_prices(soxx, "soxx")
        self.dates = list(dates)
        self.soxx = list(soxx)
        self.rsi = rsi_wilder(self.soxx)
        self.sma = sma_running(self.soxx)
        self._shd = shd_by_date(self.dates, spy, ief, set(market_dates))
        self._spy, self._ief, self._market_dates = spy, ief, market_dates
        self._soxl = dict(soxl_close or {})
        for v in self._soxl.values():
            if not _finite_positive(v):
                raise InputError("price_not_finite_positive", "soxl_close")
        self.meta = meta
        self._index = {d: i for i, d in enumerate(self.dates)}

    def through(self, d):
        """Slice at D. Indicators are causal, so later prices cannot reach rows up to D."""
        parse_iso_date(d, "target_session_date")
        n = bisect.bisect_right(self.dates, d)
        cut = object.__new__(MarketSeries)
        cut.dates = self.dates[:n]
        cut.soxx = self.soxx[:n]
        cut.rsi = self.rsi[:n]
        cut.sma = self.sma[:n]
        cut._shd = {k: v for k, v in self._shd.items() if k <= d}
        cut._spy = cut._ief = cut._market_dates = None
        cut._soxl = {k: v for k, v in self._soxl.items() if k <= d}
        cut.meta = dict(self.meta)
        cut._index = {x: i for i, x in enumerate(cut.dates)}
        return cut

    def has(self, d):
        return d in self._index

    def previous_date(self, d):
        i = self._index.get(d)
        if i is None or i == 0:
            return None
        return self.dates[i - 1]

    def row(self, d):
        i = self._index.get(d)
        if i is None:
            raise InputError("target_row_missing", "market")
        if i == 0 or None in (self.sma[i], self.rsi[i], self.rsi[i - 1], self._shd.get(d)):
            raise InputError("insufficient_history", "market")
        return MarketRow(d, self.soxx[i], self.sma[i], self.rsi[i], self._shd[d], self.rsi[i - 1])

    def shd_at(self, d):
        return self._shd.get(d)

    def soxl_close(self, d):
        v = self._soxl.get(d)
        return None if v is None else Decimal(str(v))

    def description(self):
        d = dict(self.meta)
        d["rows"] = len(self.dates)
        d["first_date"] = self.dates[0] if self.dates else None
        d["last_date"] = self.dates[-1] if self.dates else None
        return d


def _read(root, name):
    with open(os.path.join(root, name), "rb") as fh:
        return fh.read()


def _num(text):
    if text is None or text == "":
        return None
    try:
        v = float(text)
    except ValueError:
        raise InputError("price_not_finite_positive", "market_csv")
    if not _finite_positive(v):
        raise InputError("price_not_finite_positive", "market_csv")
    return v


def load_research_fixture(root, through=None):
    """Load the public research fixture (daily.json, daily_adjclose.csv, fear-greed.csv).

    Returns (MarketSeries, fear_greed) where fear_greed maps date -> float in [0, 100].
    Data after `through` is dropped before any indicator is computed.
    """
    try:
        return _load_research_fixture(root, through)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        raise InputError("fixture_unreadable_or_invalid", "fixture")


def _load_research_fixture(root, through):
    names = ["daily.json", "daily_adjclose.csv", "fear-greed.csv"]
    raw = [_read(root, n) for n in names]
    manifest = [
        {"file": n, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "git_blob": _git_blob_sha1(b)}
        for n, b in zip(names, raw)
    ]
    daily = json.loads(raw[0])
    dates = list(daily["date"])
    soxx = list(daily["references"]["SOXX"]["adjClose"])
    ohlcv = daily["funds"]["SOXL"]["ohlcv"]
    soxl = dict(zip(ohlcv["date"], ohlcv["close"]))
    market = {}
    for r in csv.DictReader(raw[1].decode("utf-8").splitlines()):
        market[r["Date"]] = r
    fg = {}
    for r in csv.DictReader(raw[2].decode("utf-8").splitlines()):
        try:
            v = float(r["Fear Greed"])
        except ValueError:
            raise InputError("fg_value_invalid", "fear_greed_csv")
        if not (math.isfinite(v) and 0 <= v <= 100):
            raise InputError("fg_value_invalid", "fear_greed_csv")
        fg[r["Date"]] = v
    if through is not None:
        parse_iso_date(through, "through")
        n = bisect.bisect_right(dates, through)
        dates, soxx = dates[:n], soxx[:n]
        market = {k: v for k, v in market.items() if k <= through}
        soxl = {k: v for k, v in soxl.items() if k <= through}
        fg = {k: v for k, v in fg.items() if k <= through}
    spy = {k: _num(v["SPY"]) for k, v in market.items()}
    ief = {k: _num(v["IEF"]) for k, v in market.items()}
    meta = {
        "source": "research fixture (public)",
        "price_definition": PRICE_DEF_SOXX,
        "soxl_close_definition": PRICE_DEF_SOXL_CLOSE,
        "prehistory_start": dates[0] if dates else None,
        "input_manifest": manifest,
    }
    series = MarketSeries(dates, soxx, spy, ief, set(market), soxl_close=soxl, meta=meta)
    return series, fg
