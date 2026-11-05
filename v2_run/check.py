"""check-source: the facts of the daily chart responses that the dry run must record before the live run (the S4-D handoffs:
the design review P-03, the receipt P-02, the re-review R-02). Counts, dates and numbers only: no URL, no body, no text of an
exception. Nothing is written anywhere (the pin is only read)."""
import csv
import datetime as dt
import json
import os

from v2_inputs import CALENDAR_START, PREHISTORY_START, SYMBOLS
from v2_inputs.xnys import ny_offset, session_days

RESEARCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "research", "SOXL_initial_trend_20261023", "data")


def ny_date(now):
    """The New York date of an aware time (the date that load_inputs uses for the end of its fetch)."""
    utc = now.astimezone(dt.timezone.utc)
    return (utc + ny_offset(utc.date())).date()


def end_date(now):
    """The `end` of every fetch: the day after the New York date of now (the same as load_inputs)."""
    return (ny_date(now) + dt.timedelta(days=1)).isoformat()


def _ny(stamp):
    utc = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
    local = utc + ny_offset(utc.date())
    return local.date().isoformat(), local.strftime("%H:%M")


def research_dates():
    """{symbol: set of dates with a value} of the research data (SOXX and SOXL from daily.json, SPY and IEF from the csv)."""
    with open(os.path.join(RESEARCH, "daily.json"), encoding="utf-8") as f:
        daily = json.load(f)
    out = {"SOXX": {d for d, a in zip(daily["date"], daily["references"]["SOXX"]["adjClose"]) if a},
           "SOXL": set(daily["funds"]["SOXL"]["ohlcv"]["date"])}
    with open(os.path.join(RESEARCH, "daily_adjclose.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for symbol in ("SPY", "IEF"):
        out[symbol] = {r["Date"] for r in rows if r[symbol]}
    return out


def table_dates(target):
    """The session dates of the table up to the target day (from CALENDAR_START)."""
    return [d.isoformat() for d in session_days() if d.isoformat() <= target]


def target_day(sessions, now):
    """The last session that has closed at now (the target D), or None."""
    closed = [s.date for s in sessions.sessions if s.close_at <= now]
    return closed[-1] if closed else None


def inspect(data, symbol, target, table, known, pinned=None, through=None):
    """A dict of the facts of one response. target: the target D of now. table: the table dates up to the target. known: the
    research dates of this symbol. pinned: {date: (close, adjclose)} of the pin of this symbol and through: its last day."""
    facts = {}
    try:
        result = json.loads(data.decode("utf-8"))["chart"]["result"][0]
        stamps = result["timestamp"]
        close = result["indicators"]["quote"][0]["close"]
        adjusted = result["indicators"]["adjclose"][0]["adjclose"]
        facts["meta_symbol_ok"] = result["meta"]["symbol"] == symbol
        days_of = [_ny(t) for t in stamps]
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, UnicodeDecodeError, OverflowError, OSError):
        facts["shape"] = "invalid"
        return facts
    facts["shape"] = "ok" if len(stamps) == len(close) == len(adjusted) else "lengths_differ"
    rows, times, nulls, again = {}, {}, [], []
    for (day, clock), c, a in zip(days_of, close, adjusted):
        times[clock] = times.get(clock, 0) + 1
        if day in rows:
            again.append(day)
        rows[day] = (c, a)
        if c is None or a is None:
            nulls.append(day)
    have = {d for d, v in rows.items() if v[0] is not None and v[1] is not None}
    facts["rows"] = len(stamps)
    facts["first"], facts["last"] = (min(rows), max(rows)) if rows else (None, None)
    facts["times_ny"] = ", ".join("%s×%d" % (k, v) for k, v in sorted(times.items(), key=lambda x: (-x[1], x[0]))[:4])
    facts["duplicate_dates"] = ", ".join(sorted(set(again))[-5:]) or "-"
    facts["target_rows"] = sum(1 for day, _clock in days_of if day == target)
    missing = [d for d in table if d not in have]
    facts["table_days_missing_or_null"] = len(missing)
    facts["table_days_missing_examples"] = ", ".join(missing[:5]) or "-"
    facts["null_rows"] = len(nulls)
    border = CALENDAR_START.isoformat()
    before = {d for d in have if d < border}
    ref = {d for d in known if d < border}
    low = min(ref) if ref else None
    facts["pre2026_only_in_response"] = len({d for d in before if low is not None and d >= low} - ref)
    facts["pre2026_only_in_research"] = len(ref - before)
    if pinned is not None and through is not None:        # does the response still agree with what was pinned?
        last = rows.get(through)
        facts["pin_last_close_changed"] = "no_row" if last is None else last[0] != pinned.get(through, (None,))[0]
        facts["pin_older_close_changed"] = sum(1 for d, v in pinned.items()
                                               if d < through and d in rows and rows[d][0] != v[0])
        common = sorted(d for d in pinned if d in have and d <= through)
        steps = [abs(rows[b][1] / rows[a][1] - pinned[b][1] / pinned[a][1]) for a, b in zip(common, common[1:])]
        facts["pin_adj_return_maxdiff"] = "%.2e" % max(steps) if steps else "-"
    return facts


__all__ = ["PREHISTORY_START", "SYMBOLS", "end_date", "inspect", "research_dates", "table_dates", "target_day"]
