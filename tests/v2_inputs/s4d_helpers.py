"""Helpers for the S4-D (inputs of the morning run) tests (never imported by the runtime).

Sockets are disabled by the helpers this file imports. The S4-C, S4-B and S4-A helpers (and through them the existing ones)
are only imported, never changed. The only remotes are bare repositories in a temporary directory whose path carries the
mark SECRETMARK_. The market responses are bytes in the shape of the chart API, made here from the research data
(daily.json, daily_adjclose.csv, fear-greed.csv) that this file reads on its own with json / csv. The expected values come
from the table of section 4.1 of the design copied below (not from the code under test), from the research fixture, from
`git` called directly, and from what the sender double received. The New York time rule used to make the responses is
written here again, apart from the runtime.
"""
import csv
import json
import hashlib
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_git_store")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import s4c_helpers as C  # noqa: E402  (existing helper; it also disables sockets)
import v2_inputs as I  # noqa: E402
from v2_core.errors import CoreError, InputError  # noqa: E402
from v2_history_publish import publish_genesis  # noqa: E402

B, S, N, GS = C.B, C.S, C.N, C.GS
tgit = C.tgit
WORKER = os.path.join(HERE, "s4d_worker.py")
MARK = C.MARK
UTC = timezone.utc
JST = timezone(timedelta(hours=9))
DATA_DIR = os.path.join(ROOT, "research", "SOXL_initial_trend_20261023", "data")
REFS = {"market": "v2-market", "ledger": "v2-ledger"}
PRE = "2010-02-11"
SYMBOLS = ("SOXX", "SPY", "IEF", "SOXL")

# --- the table of section 4.1 of the design, copied (the expected values of the calendar tests) --------------------------
HOLIDAY_TABLE = {
    2026: "01-01 01-19 02-16 04-03 05-25 06-19 07-03 09-07 11-26 12-25",
    2027: "01-01 01-18 02-15 03-26 05-31 06-18 07-05 09-06 11-25 12-24",
    2028: "01-17 02-21 04-14 05-29 06-19 07-04 09-04 11-23 12-25"}
EARLY_TABLE = {2026: "11-27 12-24", 2027: "11-26", 2028: "07-03 11-24"}


def _expand(table):
    return sorted("%d-%s" % (y, md) for y, text in table.items() for md in text.split())


HOLIDAYS = _expand(HOLIDAY_TABLE)
EARLY = _expand(EARLY_TABLE)
FIRST_DAY, LAST_DAY = "2026-01-02", "2028-12-29"


def table_days(lo=FIRST_DAY, hi=LAST_DAY):
    """The session dates of the table between lo and hi (inclusive): the weekdays that are not holidays."""
    out, day = [], date.fromisoformat(lo)
    while day <= date.fromisoformat(hi):
        if day.weekday() < 5 and day.isoformat() not in HOLIDAYS:
            out.append(day.isoformat())
        day += timedelta(1)
    return out


def _nth_sunday(year, month, n):
    day = date(year, month, 1)
    while day.weekday() != 6:
        day += timedelta(1)
    return day + timedelta(7 * (n - 1))


def ny_hours(day):
    """-4 in summer time (second Sunday of March .. the day before the first Sunday of November), else -5."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return -4 if _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1) else -5


def ny_to_utc(day, hour, minute=0):
    """The UTC time of a New York wall-clock time on a date."""
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone(timedelta(hours=ny_hours(d)))).astimezone(UTC)


def ny_stamp(day, hour=9, minute=30):
    return int(ny_to_utc(day, hour, minute).timestamp())


def next_day(day, n=1):
    return (date.fromisoformat(day) + timedelta(n)).isoformat()


def jst_morning(day, hour=7, minute=40):
    """The morning (JST) of the calendar day after `day`: the time of a run for the target day `day`."""
    d = date.fromisoformat(next_day(day))
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=JST)


# --- the research data, read on its own ---------------------------------------------------------------------------------------
def _load_src():
    with open(os.path.join(DATA_DIR, "daily.json"), "rb") as f:
        daily = json.loads(f.read().decode("utf-8"))
    with open(os.path.join(DATA_DIR, "daily_adjclose.csv"), "rb") as f:
        adjusted = list(csv.DictReader(f.read().decode("utf-8").splitlines()))
    with open(os.path.join(DATA_DIR, "fear-greed.csv"), "rb") as f:
        fg = {r["Date"]: r["Fear Greed"] for r in csv.DictReader(f.read().decode("utf-8").splitlines())}
    ohlcv = daily["funds"]["SOXL"]["ohlcv"]
    src = {"SOXX": {d: (a, a) for d, a in zip(daily["date"], daily["references"]["SOXX"]["adjClose"]) if a},
           "SOXL": {d: (c, c) for d, c in zip(ohlcv["date"], ohlcv["close"])},
           "SPY": {r["Date"]: (float(r["SPY"]), float(r["SPY"])) for r in adjusted if r["SPY"]},
           "IEF": {r["Date"]: (float(r["IEF"]), float(r["IEF"])) for r in adjusted if r["IEF"]}}
    return src, fg


_SRC, FG = _load_src()
DAILY_DATES = sorted(_SRC["SOXX"])          # the SOXX dates of the research data
HOLIDAY_ROW = "2026-05-25"                  # the csv has a row on this holiday (the values are empty); responses leave it out


def research(upto=None):
    """A copy of the research rows {symbol: {date: (close, adjclose)}} up to a date (the 2026-05-25 holiday row left out)."""
    return {s: {d: v for d, v in rows.items() if (upto is None or d <= upto) and d != HOLIDAY_ROW}
            for s, rows in _SRC.items()}


def synthetic(upto):
    """Rows for the pre-history start and for every session of the table up to a date (any symbol, small steady values):
    for the tests at the far end of the table, where the research data does not reach."""
    days = [PRE] + table_days(FIRST_DAY, upto)
    return {s: {d: (50.0 + 0.01 * i + k, 50.0 + 0.01 * i + k) for i, d in enumerate(days)}
            for k, s in enumerate(SYMBOLS)}


# --- responses in the shape of the chart API ------------------------------------------------------------------------------------
def chart_body(symbol, items):
    """items: [(date text or UTC seconds, close, adjclose)] in the order given."""
    stamps = [ny_stamp(t) if isinstance(t, str) else t for t, _c, _a in items]
    return {"chart": {"result": [{"meta": {"symbol": symbol, "exchangeTimezoneName": "America/New_York"},
                                  "timestamp": stamps,
                                  "indicators": {"quote": [{"close": [c for _t, c, _a in items]}],
                                                 "adjclose": [{"adjclose": [a for _t, _c, a in items]}]}}],
                      "error": None}}


def chart_bytes(symbol, rows, upto=None, scale=1.0, drop=(), extra=()):
    """The response for one symbol: the rows up to a date (sorted), the adjusted close times `scale`, without the dates in
    `drop`, then the `extra` items [(date, close, adjclose)] as they are (a live bar after the target day, and so on)."""
    items = [(d, v[0], None if v[1] is None else v[1] * scale) for d, v in sorted(rows.items()) if (upto is None or d <= upto) and d not in drop]
    return json.dumps(chart_body(symbol, items + list(extra))).encode("utf-8")


class Provider(object):
    """A fetch function of the tests. It answers from `rows` ({symbol: {date: (close, adjclose)}}, default the research
    data) up to `upto`; `scale` revises the adjusted close; `drop` leaves dates out; `extra` is {symbol: [items]} appended
    after the rows; `bad` is {symbol: bytes or exception} that is answered instead; `before(symbol)` runs first."""

    def __init__(self, upto, rows=None, scale=1.0, drop=(), extra=None, bad=None, fail=False, before=None):
        self.upto, self.rows = upto, rows if rows is not None else research()
        self.scale, self.drop, self.extra, self.bad = scale, drop, extra or {}, dict(bad or {})
        self.fail, self.before, self.args = fail, before, []

    @property
    def calls(self):
        return len(self.args)

    def __call__(self, symbol, start, end):
        self.args.append((symbol, start, end))
        if self.before is not None:
            self.before(symbol)
        if self.fail:
            raise OSError("network " + MARK)
        if symbol in self.bad:
            answer = self.bad[symbol]
            if isinstance(answer, BaseException):
                raise answer
            return answer
        return chart_bytes(symbol, self.rows[symbol], self.upto, self.scale, self.drop, self.extra.get(symbol, ()))


# --- the ledger ---------------------------------------------------------------------------------------------------------------------
COLUMNS = ("record_id", "target_us_session_date", "observation_role", "observation_status", "current_fg_value",
           "observed_at_iso8601")
HEADER = ",".join(COLUMNS) + "\n"


def decision_line(day, value=None):
    """The ledger line of the decision for `day`: observed at 07:05 JST the next morning with the research F&G value."""
    value = FG.get(day, "50") if value is None else value
    return "fg-%s,%s,decision,observed,%s,%sT07:05+09:00\n" % (day, day, value, next_day(day))


def ledger_text(days, extra=""):
    return HEADER + "".join(decision_line(d) for d in days) + extra


def ledger_rows(text):
    """The rows the core should receive, read apart from the code under test (BOM and CRLF are dropped by splitting)."""
    lines = [x for x in text.lstrip("﻿").replace("\r\n", "\n").split("\n") if x.strip()]
    return [dict(zip(COLUMNS, (c.strip() for c in x.split(",")))) for x in lines[1:]]


def sessions_days(lo, hi):
    return table_days(lo, hi)


# --- the rig: a remote, clones, the stores and the morning -----------------------------------------------------------------
class Rig(object):
    """A bare remote (path with the mark) with an initialized history and outbox, and the first clone. `morning` is what the
    entry of S4-E will do: load_inputs once with the one `now`, guarded_store, morning_job."""

    def __init__(self, case, start="2026-07-20", clk=C.clock, ledger_days=None):
        self.case, self.start = case, start
        self.remote = C.Remote(case)
        self.clone = C.Clone(case, self.remote, clk)
        self.sender = B.Sender()
        sessions = I.build_sessions(jst_morning(next_day(start)), start)
        self.clone.hist.initialize(publish_genesis(start, sessions))
        self.clone.outbox.initialize()
        self.ledger = ""
        if ledger_days is not None:
            self.set_ledger(ledger_days)

    def set_ledger(self, days, extra=""):
        self.ledger = ledger_text(days, extra)
        self.put_ledger(self.ledger)

    def put_ledger(self, text):
        self.ledger = text
        self.remote.plant("v2-ledger", {"observations.csv": text.encode("utf-8")}, parent="HEAD~")

    def another(self):
        """A second clone of the same remote (another runner)."""
        return C.Clone(self.case, self.remote)

    def sync_ledger(self, day, extra=""):
        """The ledger holds the decision of every session day after the start up to `day` (what the user has written by the
        morning of the day after `day`), plus `extra` lines; it is written only when it differs."""
        want = ledger_text(table_days(next_day(self.start), day), extra)
        if want != self.ledger:
            self.put_ledger(want)

    def inputs(self, day, provider, now=None, git=None):
        now = now or jst_morning(day)
        return I.load_inputs(git or self.clone.git, provider, now, REFS, C.clock), now

    def morning(self, day, provider, now=None, clone=None, sender=None, sync=True, extra="", git=None):
        """`git` is the Git of load_inputs only (the stores keep the clone's own)."""
        clone = clone or self.clone
        if sync:
            self.sync_ledger(day, extra)
        inp, now = self.inputs(day, provider, now, git or clone.git)
        report = N.morning_job(I.guarded_store(clone.hist, inp.failure), clone.outbox, sender or self.sender, now,
                               inp.series, inp.sessions, inp.raw_observations)
        return report, inp

    def with_decisions(self, upto):
        """Alias of sync_ledger (the ledger up to a day)."""
        self.sync_ledger(upto)

    def sent_kinds(self):
        return [kind_of(t) for t in self.sender.texts]


def kind_of(text):
    return B.kind_of(text)


def plain_run(clone, sender, now, series, sessions, rows):
    """The morning over the given series, sessions and rows directly (the reference of the end-to-end test)."""
    return N.morning_job(clone.hist, clone.outbox, sender, now, series, sessions, rows)


def pinned_bytes(remote):
    return remote.blob("v2-market", "market.json")


def ledger_sha(remote):
    return remote.sha("v2-ledger")


def blob_sha256(data):
    return hashlib.sha256(data).hexdigest()


class Case(C.Case):
    """A fresh sender double per test and the leak collector of the S4-C tests."""


class Child(C.Child):
    def __init__(self, spec, timeout=600):
        self.timeout = timeout
        self.proc = subprocess.Popen([sys.executable, "-B", "-I", WORKER, json.dumps(spec)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def read_source(relative):
    return S.read_source(relative)


# --- the input failures that load_inputs returns, one scenario each (S4D-10 and the sweep of S4D-16) ------------------------
D = "2026-07-28"
START = "2026-07-27"


def failing_git(clone, mark_ref):
    """The Git of load_inputs on the clone's own work directory, whose commands that mention a ref all fail."""
    return C.Scripted(clone.dir, rule=lambda args: C.proc(128, b"", ("fatal: " + MARK).encode())
                        if args[0] in ("fetch", "ls-remote") and any(mark_ref in a for a in args) else None)


def run_case(case, name):
    """(rig, report, inputs) of the morning of D with the input made wrong in the way `name` says."""
    rig = Rig(case, start=START)
    rows, provider_kw, extra, git, day, now = research(), {}, "", None, D, None
    sync = True
    if name == "input_calendar_not_covered":
        rig = Rig(case, start="2028-12-18")
        rows, day = synthetic("2028-12-19"), "2028-12-19"
    elif name == "input_market_fetch_failed":
        provider_kw["fail"] = True
    elif name == "input_market_response_invalid":
        provider_kw["bad"] = {"SPY": b"not json " + MARK.encode()}
    elif name == "input_market_value_invalid":
        rows["SOXL"][D] = (2e6, 2e6)
    elif name == "input_market_history_short":
        del rows["SOXX"][PRE]
    elif name == "input_calendar_data_mismatch":
        rows["SPY"]["2026-07-03"] = rows["SPY"]["2026-07-02"]
    elif name == "input_market_rows_missing":
        provider_kw["drop"] = ("2026-07-27",)
    elif name == "input_market_pin_invalid":
        rig.remote.plant("v2-market", {"market.json": b"{}"}, parent=None)
    elif name == "input_market_pin_failed":
        rig.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/v2-market ] && exit 1; done; exit 0')
    elif name == "input_market_unavailable":
        rows = {s: {PRE: (10.0, 10.0)} for s in SYMBOLS}
    elif name == "input_ledger_missing":
        sync = False
    elif name == "input_ledger_unreadable":
        sync = False
        rig.put_ledger("x")
        rig.remote.plant("v2-ledger", {"observations.csv": b"\xff\xfe\x00bad"}, parent="HEAD~")
    elif name == "input_ledger_header_invalid":
        sync = False
        rig.put_ledger(HEADER.replace("record_id", "id") + decision_line("2026-07-27"))
    elif name == "input_ledger_row_invalid":
        sync = False
        rig.put_ledger(HEADER + "fg-x,2026-07-27,decision,observed,50\n")
    elif name == "input_ledger_observation_after_now":
        extra = "fg-x,2026-07-27,supplemental,observed,50,2026-12-01T07:00+09:00\n"
    elif name == "input_git_failed":
        git = failing_git(rig.clone, "v2-market")
    else:
        raise AssertionError(name)
    provider = Provider(day, rows=rows, **provider_kw)
    report, inp = rig.morning(day, provider, extra=extra, git=git, sync=sync, now=now)
    return rig, report, inp, day


FIELD = {"input_calendar_not_covered": "calendar", "input_ledger_missing": "ledger", "input_ledger_unreadable": "ledger",
         "input_ledger_header_invalid": "ledger", "input_ledger_row_invalid": "ledger",
         "input_ledger_observation_after_now": "observed_at_iso8601", "input_git_failed": "inputs"}
CODES = ["input_calendar_not_covered", "input_market_fetch_failed", "input_market_response_invalid",
         "input_market_value_invalid", "input_market_history_short", "input_calendar_data_mismatch",
         "input_market_rows_missing", "input_market_pin_invalid", "input_market_pin_failed", "input_market_unavailable",
         "input_ledger_missing", "input_ledger_unreadable", "input_ledger_header_invalid", "input_ledger_row_invalid",
         "input_ledger_observation_after_now", "input_git_failed"]
DETAIL = {"input_market_value_invalid": D, "input_market_history_short": "2010-02-11",
          "input_calendar_data_mismatch": "2026-07-03", "input_market_rows_missing": "2026-07-27"}


