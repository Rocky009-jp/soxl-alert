"""S4D-10, S4D-12: each input failure that load_inputs returns stops the morning as a STOPPED report of the right target
day with one "no verdict" notice, the reason code in the text and the history unchanged; holes, days the table does not
have, and the rows of a session that is still open."""
import json
import unittest
from datetime import timedelta

import s4d_helpers as H

I = H.I
D, START = H.D, H.START


class EveryFailureStops(H.Case):
    def test_each_returned_failure_is_a_stopped_morning_with_one_notice_of_the_right_day(self):
        self.assertEqual(len(H.CODES), 16)
        for name in H.CODES:
            with self.subTest(code=name):
                rig, report, inp, day = H.run_case(self, name)
                self.see(report, inp, rig.sender.texts)
                field = H.FIELD.get(name, "market")
                self.assertEqual((inp.failure.code, inp.failure.field, inp.failure.detail), (name, field, H.DETAIL.get(name)))
                self.assertIsNone(inp.series)
                self.assertEqual(inp.raw_observations, [])
                self.assertEqual(len(inp.sessions.sessions), len(I.build_sessions(H.jst_morning(D), None).sessions))
                self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery),
                                 ("STOPPED", name, "halt", "SENT"))
                self.assertEqual(len(rig.sender.texts), 1)
                text = rig.sender.texts[0]
                self.assertEqual(H.kind_of(text), "halt")
                self.assertIn("対象D=" + day, text)
                self.assertIn("理由コード: %s（%s）" % (name, field), text)
                files = rig.remote.files("v2-state")
                self.assertEqual(len(rig.remote.log("v2-state")), 1)                 # only the genesis, nothing saved
                self.assertEqual(sorted(files), ["history.json"])
                self.assertNoMark()
                self.shown.clear()

    def test_the_failure_does_not_change_the_history_and_the_notice_is_the_keyed_halt_of_the_day(self):
        rig, report, inp, day = H.run_case(self, "input_market_fetch_failed")
        statuses = [(e.kind, e.status) for e in H.N.outbox_status(rig.clone.outbox, day)]
        self.assertEqual(statuses[0], ("morning", "NONE"))
        self.assertEqual(statuses[1], ("halt", "SENT"))

    def test_the_end_of_the_table_is_raised_by_load_inputs_not_returned(self):
        rig = H.Rig(self)
        with self.assertRaises(H.InputError) as cm:
            rig.inputs("2029-01-01", H.Provider(D))
        self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.detail),
                         ("input_calendar_ended", "calendar", None))
        self.assertEqual(rig.remote.refs().get("refs/heads/v2-market"), None)

    def test_the_same_morning_after_the_input_is_right_gives_the_verdict(self):
        rig, report, inp, day = H.run_case(self, "input_market_fetch_failed")
        again, inp2 = rig.morning(day, H.Provider(day))
        self.assertIsNone(inp2.failure)
        self.assertEqual((again.run_outcome, again.kind, again.delivery), ("DONE", "morning", "SENT"))
        self.assertEqual(rig.sent_kinds(), ["halt", "morning"])


class Holes(H.Case):
    def test_a_hole_before_the_target_stops_and_the_fixed_data_catches_up(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-24", H.Provider("2026-07-24", drop=("2026-07-22",)))
        self.assertEqual((inp.failure.code, inp.failure.detail), ("input_market_rows_missing", "2026-07-22"))
        self.assertEqual((report.run_outcome, report.code, report.delivery), ("STOPPED", "input_market_rows_missing", "SENT"))
        self.assertIsNone(rig.remote.sha("v2-market"))                                # nothing was pinned
        fixed, inp = rig.morning("2026-07-24", H.Provider("2026-07-24"))
        self.assertIsNone(inp.failure)
        self.assertEqual((fixed.run_outcome, fixed.kind, fixed.delivery), ("DONE", "morning", "SENT"))
        history = json.loads(rig.remote.blob("v2-state", "history.json").decode("utf-8"))
        applied = [e["d"] for e in history["events"] if e["kind"] == "APPLY"]
        self.assertEqual(applied, ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"])

    def test_two_holes_name_the_first(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-24", H.Provider("2026-07-24", drop=("2026-07-21", "2026-07-23")))
        self.assertEqual((inp.failure.code, inp.failure.detail), ("input_market_rows_missing", "2026-07-21"))

    def test_two_holes_in_a_row_name_the_first(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-24", H.Provider("2026-07-24", drop=("2026-07-21", "2026-07-22")))
        self.assertEqual((inp.failure.code, inp.failure.detail), ("input_market_rows_missing", "2026-07-21"))

    def test_a_day_missing_for_one_symbol_only_is_a_hole(self):
        for symbol in H.SYMBOLS:
            rows = H.research()
            del rows[symbol]["2026-07-22"]
            rig = H.Rig(self)
            report, inp = rig.morning("2026-07-24", H.Provider("2026-07-24", rows=rows))
            self.assertEqual((inp.failure.code, inp.failure.detail), ("input_market_rows_missing", "2026-07-22"), symbol)

    def test_a_trailing_gap_with_nothing_after_it_is_not_an_error(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-24", H.Provider("2026-07-24", drop=("2026-07-24",)))
        self.assertIsNone(inp.failure)
        self.assertEqual(inp.provenance["market_through"], "2026-07-23")
        self.assertEqual((report.run_outcome, report.code), ("STALE", "run_session_unconfirmed"))


class NothingClosedYet(H.Case):
    def test_before_the_close_of_the_first_session_there_is_no_target_and_no_exception(self):
        rig = H.Rig(self, start=START)
        provider = H.Provider(D)
        now = H.ny_to_utc("2026-01-02", 15, 0)                  # the first session of the table is still open
        inp, _now = rig.inputs(D, provider, now=now)
        self.assertEqual((inp.failure.code, inp.failure.field), ("input_market_unavailable", "market"))
        self.assertEqual(provider.calls, 0)
        self.assertTrue(all(not s.confirmed for s in inp.sessions.sessions))
        self.assertIsNone(rig.remote.sha("v2-market"))


class DaysTheTableDoesNotHave(H.Case):
    def failure_of(self, symbol, extra_day, start=START):
        rig = H.Rig(self, start=start)
        rig.sync_ledger(D)
        rows = H.research()
        source = {"SOXX": rows["SOXX"], "SPY": rows["SPY"], "IEF": rows["IEF"], "SOXL": rows["SOXL"]}
        source[symbol][extra_day] = (50.0, 50.0)
        inp, _now = rig.inputs(D, H.Provider(D, rows=rows))
        return inp.failure

    def test_a_row_on_a_holiday_or_a_weekend_is_a_mismatch_for_soxx_spy_and_ief(self):
        for symbol in ("SOXX", "SPY", "IEF"):
            for extra_day in ("2026-07-03", "2026-07-25", "2026-07-26", "2026-05-25"):
                failure = self.failure_of(symbol, extra_day)
                self.assertEqual((failure.code, failure.detail), ("input_calendar_data_mismatch", extra_day), (symbol, extra_day))

    def test_the_first_such_day_of_all_symbols_is_named(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        rows = H.research()
        rows["IEF"]["2026-07-25"] = (50.0, 50.0)
        rows["SOXX"]["2026-07-03"] = (50.0, 50.0)
        inp, _now = rig.inputs(D, H.Provider(D, rows=rows))
        self.assertEqual(inp.failure.detail, "2026-07-03")

    def test_a_soxl_only_row_on_such_a_day_is_not_checked(self):
        self.assertIsNone(self.failure_of("SOXL", "2026-07-03"))

    def test_rows_before_the_table_starts_are_not_checked(self):
        for extra_day in ("2026-01-01", "2025-12-25", "2025-12-27", "2012-12-25"):
            self.assertIsNone(self.failure_of("SPY", extra_day), extra_day)


class SessionStillOpen(H.Case):
    """Z1 and Z2 of the review: a fetch made while the next session is open returns its unfinished bar (or two rows of the
    same date). Those rows are after the target day: dropped, not pinned, not an error."""

    def run_midday(self, extra):
        rig = H.Rig(self, start=START)
        now = H.ny_to_utc("2026-07-29", 10, 40)
        self.assertEqual(now.isoformat(), "2026-07-29T14:40:00+00:00")
        provider = H.Provider(D, extra=extra)
        report, inp = rig.morning(D, provider, now=now)
        self.see(report, inp)
        return rig, report, inp

    def check(self, rig, report, inp):
        self.assertIsNone(inp.failure)
        self.assertEqual((report.run_outcome, report.kind, report.delivery), ("DONE", "morning", "SENT"))
        self.assertEqual(inp.provenance["market_through"], D)
        pinned = json.loads(rig.remote.blob("v2-market", "market.json").decode("ascii"))
        for symbol in H.SYMBOLS:
            self.assertEqual(max(pinned["symbols"][symbol]["dates"]), D)
            self.assertNotIn("2026-07-29", pinned["symbols"][symbol]["dates"])
        self.assertEqual(pinned["through"], D)

    def test_one_unfinished_row_of_the_open_session(self):
        extra = {s: [("2026-07-29", 99.0, 99.0)] for s in H.SYMBOLS}
        self.check(*self.run_midday(extra))

    def test_two_rows_of_the_open_session_with_the_same_date(self):
        extra = {s: [(H.ny_stamp("2026-07-29", 9, 30), 99.0, 99.0), (H.ny_stamp("2026-07-29", 10, 39), 99.5, 99.5)]
                 for s in H.SYMBOLS}
        self.check(*self.run_midday(extra))

    def test_a_row_of_the_open_session_with_a_bad_value_or_a_null(self):
        extra = {s: [("2026-07-29", float("nan"), 5e9)] for s in H.SYMBOLS}
        self.check(*self.run_midday(extra))
        extra = {s: [("2026-07-29", None, None), ("2026-07-30", 1.0, 1.0)] for s in H.SYMBOLS}
        self.check(*self.run_midday(extra))

    def test_two_rows_of_the_target_day_itself_are_still_a_wrong_shape(self):
        extra = {s: [(H.ny_stamp(D, 15, 59), 77.0, 77.0)] for s in H.SYMBOLS}
        rig = H.Rig(self, start=START)
        report, inp = rig.morning(D, H.Provider(D, extra=extra))
        self.assertEqual(inp.failure.code, "input_market_response_invalid")
        self.assertEqual((report.run_outcome, report.kind), ("STOPPED", "halt"))


if __name__ == "__main__":
    unittest.main()
