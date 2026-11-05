"""XNYS sessions from a fixed table (no calendar library, no tz database): the weekdays of the table's range minus the
holidays, 09:30-16:00 New York time (13:00 on an early close), with the US daylight-saving rule (second Sunday of March to
the day before the first Sunday of November: UTC-4, otherwise UTC-5).

The table is the one of the NYSE announcement "NYSE Group Announces 2026, 2027 and 2028 Holiday and Early Closings Calendar"
(ICE, 2025-12-23, https://ir.theice.com/press/news-details/2025/NYSE-Group-Announces-2026-2027-and-2028-Holiday-and-Early-
Closings-Calendar/default.aspx). Every one of the 29 holidays and 5 early closes below was compared with that announcement
on 2026-11-05 (review 33894b2, docs/reviews/V2_INPUTS_S4D_DESIGN_REVIEW_20261105.md). When a year is added, read the
announcement, compare every day, and record the source and the date here. A change of a day after its session was stored
makes the stored session list differ from the table (session_context_mismatch): change the table before the day."""
import datetime as dt
import hashlib

from v2_core.errors import InputError
from v2_core.sessions import Session, SessionList

CALENDAR_START = dt.date(2026, 1, 2)
CALENDAR_END = dt.date(2028, 12, 29)
MARGIN_DAYS = 14

HOLIDAYS = frozenset(dt.date.fromisoformat(x) for x in (
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
    "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19", "2028-07-04", "2028-09-04", "2028-11-23",
    "2028-12-25"))
EARLY_CLOSES = frozenset(dt.date.fromisoformat(x) for x in (
    "2026-11-27", "2026-12-24", "2027-11-26", "2028-07-03", "2028-11-24"))
SOURCE = "ICE 2025-12-23 NYSE Group Holiday and Early Closings Calendar 2026-2028; compared on 2026-11-05 (review 33894b2)"


def _nth_sunday(year, month, n):
    day = dt.date(year, month, 1)
    day += dt.timedelta((6 - day.weekday()) % 7)
    return day + dt.timedelta(7 * (n - 1))


def ny_offset(day):
    """The UTC offset of New York on a date (no session is on the Sunday of a change, so the date decides)."""
    summer = _nth_sunday(day.year, 3, 2) <= day < _nth_sunday(day.year, 11, 1)
    return dt.timedelta(hours=-4 if summer else -5)


def _at(day, hour, minute):
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=dt.timezone(ny_offset(day)))


def _aware(now):
    return isinstance(now, dt.datetime) and now.utcoffset() is not None


def session_days():
    """Every session date of the table, oldest first."""
    day, out = CALENDAR_START, []
    while day <= CALENDAR_END:
        if day.weekday() < 5 and day not in HOLIDAYS:
            out.append(day)
        day += dt.timedelta(1)
    return out


def calendar_sha256():
    """The version of the table: the sha256 of its canonical ASCII text
    "<CALENDAR_START>..<CALENDAR_END>|H:<holidays, sorted, comma-separated>|E:<early closes, sorted, comma-separated>"."""
    text = "%s..%s|H:%s|E:%s" % (CALENDAR_START, CALENDAR_END, ",".join(sorted(d.isoformat() for d in HOLIDAYS)),
                                 ",".join(sorted(d.isoformat() for d in EARLY_CLOSES)))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def coverage_failure(now):
    """None, or InputError(input_calendar_not_covered) when now + MARGIN_DAYS is past the table (the sessions can still be
    built, so the run stops with the right D and sends its notice)."""
    if not _aware(now):
        raise InputError("input_args_invalid", "inputs")
    if (now.astimezone(dt.timezone.utc) + dt.timedelta(days=MARGIN_DAYS)).date() > CALENDAR_END:
        return InputError("input_calendar_not_covered", "calendar")
    return None


def build_sessions(now, confirmed_through):
    """Every session of the table from CALENDAR_START; confirmed only up to confirmed_through (a date text, or None for
    none). Raises InputError(input_calendar_ended) when the UTC date of now is past the table."""
    if not _aware(now):
        raise InputError("input_args_invalid", "inputs")
    if now.astimezone(dt.timezone.utc).date() > CALENDAR_END:
        raise InputError("input_calendar_ended", "calendar")
    out = []
    for day in session_days():
        close = _at(day, 13, 0) if day in EARLY_CLOSES else _at(day, 16, 0)
        confirmed = confirmed_through is not None and day.isoformat() <= confirmed_through
        out.append(Session(day.isoformat(), _at(day, 9, 30), close, confirmed))
    return SessionList(out)
