"""S4D-03: the sessions come from the table of section 4.1 and the New York rule: the dates equal the research data's
SOXX dates for 2026, the holidays and early closes are the table's, the open and close times in UTC are fixed by hand around
every daylight-saving change of 2026-2028, `confirmed` follows confirmed_through, the end of the table is guarded by 14 days,
and calendar_sha256 follows the table."""
import hashlib
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import s4d_helpers as H
import v2_inputs.xnys as XN

I = H.I

UTC = timezone.utc
SOME_NOW = datetime(2026, 7, 28, 7, 40, tzinfo=H.JST)

# (date, open UTC, close UTC), written by hand: 09:30 and 16:00 New York time; 13:30Z / 20:00Z in summer time (UTC-4),
# 14:30Z / 21:00Z in winter time (UTC-5). Four weekdays around each change (2026, 2027, 2028; March and November).
SWITCH = [
    ("2026-03-05", "14:30", "21:00"), ("2026-03-06", "14:30", "21:00"), ("2026-03-09", "13:30", "20:00"),
    ("2026-03-10", "13:30", "20:00"),
    ("2026-10-29", "13:30", "20:00"), ("2026-10-30", "13:30", "20:00"), ("2026-11-02", "14:30", "21:00"),
    ("2026-11-03", "14:30", "21:00"),
    ("2027-03-11", "14:30", "21:00"), ("2027-03-12", "14:30", "21:00"), ("2027-03-15", "13:30", "20:00"),
    ("2027-03-16", "13:30", "20:00"),
    ("2027-11-04", "13:30", "20:00"), ("2027-11-05", "13:30", "20:00"), ("2027-11-08", "14:30", "21:00"),
    ("2027-11-09", "14:30", "21:00"),
    ("2028-03-09", "14:30", "21:00"), ("2028-03-10", "14:30", "21:00"), ("2028-03-13", "13:30", "20:00"),
    ("2028-03-14", "13:30", "20:00"),
    ("2028-11-02", "13:30", "20:00"), ("2028-11-03", "13:30", "20:00"), ("2028-11-06", "14:30", "21:00"),
    ("2028-11-07", "14:30", "21:00")]


def utc_at(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


class Calendar(H.Case):
    @classmethod
    def setUpClass(cls):
        cls.all = I.build_sessions(SOME_NOW, None).sessions
        cls.by_date = {s.date: s for s in cls.all}

    def test_2026_dates_equal_the_soxx_dates_of_the_research_data(self):
        mine = [s.date for s in self.all if "2026-01-02" <= s.date <= "2026-10-01"]
        research = [d for d in H.DAILY_DATES if "2026-01-02" <= d <= "2026-10-01"]
        self.assertEqual(len(research), 188)
        self.assertEqual(mine, research)

    def test_holidays_and_early_closes_are_the_table_and_there_is_no_weekend_session(self):
        dates = [s.date for s in self.all]
        self.assertEqual(dates, sorted(set(dates)))
        self.assertEqual((dates[0], dates[-1]), ("2026-01-02", "2028-12-29"))
        for d in dates:
            self.assertLess(date.fromisoformat(d).weekday(), 5, d)
        weekdays, day = [], date(2026, 1, 2)
        while day <= date(2028, 12, 29):
            if day.weekday() < 5:
                weekdays.append(day.isoformat())
            day += timedelta(1)
        # the table has 29 holidays; 2026-01-01 is before the first day of the range
        self.assertEqual([d for d in weekdays if d not in set(dates)], [d for d in H.HOLIDAYS if d >= H.FIRST_DAY])
        self.assertEqual(len(H.HOLIDAYS), 29)
        self.assertEqual(len(H.EARLY), 5)
        early = [s.date for s in self.all if (s.close_at - s.open_at) != timedelta(hours=6, minutes=30)]
        self.assertEqual(early, H.EARLY)
        for d in H.EARLY:
            self.assertIn(d, self.by_date)
        self.assertEqual(dates, H.table_days())

    def test_open_and_close_times_around_every_daylight_saving_change(self):
        for day, opened, closed in SWITCH:
            s = self.by_date[day]
            self.assertEqual(s.open_at.astimezone(UTC), utc_at(day, opened), day)
            self.assertEqual(s.close_at.astimezone(UTC), utc_at(day, closed), day)
            self.assertIsNotNone(s.open_at.utcoffset())

    def test_early_closes_close_at_13_00_new_york(self):
        self.assertEqual(self.by_date["2026-11-27"].close_at.astimezone(UTC), utc_at("2026-11-27", "18:00"))
        self.assertEqual(self.by_date["2028-07-03"].close_at.astimezone(UTC), utc_at("2028-07-03", "17:00"))
        for d in H.EARLY:
            s = self.by_date[d]
            self.assertEqual(s.open_at.astimezone(UTC) + timedelta(hours=3, minutes=30), s.close_at.astimezone(UTC), d)

    def test_confirmed_is_up_to_confirmed_through_only(self):
        for through in (None, "2026-01-02", "2026-07-28", "2026-07-26", "2028-12-29", "2025-12-31"):
            sessions = I.build_sessions(SOME_NOW, through).sessions
            self.assertEqual([s.date for s in sessions], [s.date for s in self.all])
            want = [through is not None and s.date <= through for s in sessions]
            self.assertEqual([s.confirmed for s in sessions], want, through)
        self.assertFalse(any(s.confirmed for s in self.all))

    def test_the_end_of_the_table(self):
        end = date(2028, 12, 29)
        # now + 14 days exactly on the last day of the table: no failure; one day more: not covered
        ok = datetime(2028, 12, 15, 12, 0, tzinfo=UTC)
        self.assertEqual(ok.date() + timedelta(14), end)
        self.assertIsNone(I.coverage_failure(ok))
        short = I.coverage_failure(ok + timedelta(days=1))
        self.assertEqual((short.code, short.field, short.detail), ("input_calendar_not_covered", "calendar", None))
        self.assertIsNone(I.coverage_failure(datetime(2026, 11, 5, tzinfo=UTC)))
        # the sessions are still built in the not-covered window; only a UTC date past the table raises
        for now in (ok + timedelta(days=1), datetime(2028, 12, 29, 23, 59, tzinfo=UTC)):
            self.assertEqual(len(I.build_sessions(now, None).sessions), len(self.all))
        for now in (datetime(2028, 12, 30, 0, 0, tzinfo=UTC), datetime(2029, 1, 2, tzinfo=H.JST)):
            with self.assertRaises(H.InputError) as cm:
                I.build_sessions(now, None)
            self.assertEqual((cm.exception.code, cm.exception.field), ("input_calendar_ended", "calendar"))
        # the UTC date decides: 2028-12-30 08:00 JST is 2028-12-29 23:00 UTC, still inside the table
        self.assertEqual(len(I.build_sessions(datetime(2028, 12, 30, 8, 0, tzinfo=H.JST), None).sessions), len(self.all))

    def test_the_constants(self):
        self.assertEqual((I.CALENDAR_START, I.CALENDAR_END, I.MARGIN_DAYS), (date(2026, 1, 2), date(2028, 12, 29), 14))
        self.assertEqual(I.CLOSE_MARGIN, timedelta(minutes=60))
        self.assertEqual((I.PREHISTORY_START, I.PRICE_MAX, I.SYMBOLS), ("2010-02-11", 1000000, ("SOXX", "SPY", "IEF", "SOXL")))

    def test_calendar_sha256_is_the_table_version(self):
        text = "2026-01-02..2028-12-29|H:%s|E:%s" % (",".join(H.HOLIDAYS), ",".join(H.EARLY))
        want = hashlib.sha256(text.encode("ascii")).hexdigest()
        self.assertEqual(I.calendar_sha256(), want)
        self.assertEqual(I.calendar_sha256(), I.calendar_sha256())
        # one day of the table changed -> another version
        with mock.patch.object(XN, "HOLIDAYS", XN.HOLIDAYS | {date(2026, 7, 6)}):
            self.assertNotEqual(I.calendar_sha256(), want)
        with mock.patch.object(XN, "EARLY_CLOSES", XN.EARLY_CLOSES - {date(2026, 11, 27)}):
            self.assertNotEqual(I.calendar_sha256(), want)
        with mock.patch.object(XN, "CALENDAR_END", date(2028, 12, 28)):
            self.assertNotEqual(I.calendar_sha256(), want)
        self.assertEqual(I.calendar_sha256(), want)


if __name__ == "__main__":
    unittest.main()
