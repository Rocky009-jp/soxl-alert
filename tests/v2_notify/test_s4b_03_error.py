"""S4B-06: the ERROR notice (a run that gave no report). The key is the target date D (the UTC date of the call only when
no D can be found); a judgment claim of the same D (in any state) stops it; the text and the files hold a fixed code and the
name of the exception type, never the text of the exception; a program error is raised again as the same object."""
import unittest
from datetime import datetime
from decimal import Decimal

import s4b_helpers as H

N, S, D, P = H.N, H.S, H.D, H.P

SECRET = "boom /secret/path https://example.invalid/token?x=1 hunter2"


class ErrorNotice(H.Case):
    def test_a_run_error_without_a_closed_session_sends_one_error_keyed_by_the_utc_date(self):
        now = H.now_at(D[0], 8)                              # before the first close
        silent = S.Silent()
        report = self.job(now, store=silent)
        self.assertEqual(silent.calls, [])
        key_date = H.utc_date(now)
        self.assertEqual((report.run_outcome, report.kind, report.d, report.delivery, report.exit_code, report.code),
                         (None, "error", key_date, "SENT", 1, "run_no_closed_session"))
        self.assertIsNone(report.report)
        self.assertEqual(H.names(self.oroot), [key_date + "-error.claim.json", key_date + "-error.result.json"])
        text = self.last_text()
        self.assertEqual(text.splitlines()[0], "【SOXL日次】判定なし（実行の誤り） 日付（UTC）=%s" % key_date)
        self.assertIn("理由コード: run_no_closed_session", text)
        self.assertNotIn("（", text.splitlines()[2])           # a RunError names no exception type
        again = self.job(H.now_at(D[0], 9), store=silent)       # the same UTC day
        self.assertEqual((again.delivery, again.existing_status, again.exit_code), ("SKIPPED_CLAIMED", "SENT", 1))
        self.assertEqual(len(self.sender.texts), 1)

    def test_a_wrong_sessions_argument_is_an_error_notice_too(self):
        report = self.job(H.now_at(D[2]), sessions=["not", "a", "list"])
        self.assertEqual((report.kind, report.d, report.code, report.delivery),
                         ("error", H.utc_date(H.now_at(D[2])), "run_args_invalid", "SENT"))

    def test_a_program_error_sends_one_error_and_then_raises_the_same_object(self):
        S.decide(self.w, [1])
        error = ZeroDivisionError(SECRET)
        now = H.now_at(D[2])
        with self.assertRaises(ZeroDivisionError) as ctx:
            self.job(now, series=H.RaisingSeries(error))
        self.assertIs(ctx.exception, error)
        self.assertEqual(len(self.sender.texts), 1)
        text = self.last_text()
        self.assertEqual(text, "【SOXL日次】判定なし（実行の誤り） 対象D=%s\n  今朝は結果を出していません。条件未達ではありません。\n"
                               "  理由コード: unexpected_error（ZeroDivisionError）" % D[2])
        stored = [H.bread(self.oroot, n).decode("utf-8") for n in H.names(self.oroot)]
        self.assertEqual(len(stored), 2)
        for forbidden in ("boom", "/secret", "path", "https", "token", "hunter2", self.oroot, self.hroot):
            self.assertNotIn(forbidden, text)
            for body in stored:
                self.assertNotIn(forbidden, body)
        claim = H.jread(self.oroot, D[2] + "-error.claim.json")
        self.assertEqual((claim["kind"], claim["run_outcome"], claim["code"]), ("error", None, "unexpected_error"))
        self.assertEqual(H.jread(self.oroot, D[2] + "-error.result.json")["status"], "SENT")

    def test_a_big_soxl_close_in_the_core_text_is_the_same_as_any_program_error(self):
        # the S4-A review's P-02 (b): bstar of a close of 1e27 or more raises decimal.InvalidOperation in render_message
        S.decide(self.w, [1, 2, 3])
        series = H.OddSeries(list(self.w.series.rows.values()), Decimal("1e30"))
        import decimal
        with self.assertRaises(decimal.InvalidOperation):
            self.job(H.now_at(D[3]), series=series)
        self.assertEqual(len(self.sender.texts), 1)
        self.assertIn("理由コード: unexpected_error（InvalidOperation）", self.last_text())
        self.assertEqual(H.names(self.oroot), [D[3] + "-error.claim.json", D[3] + "-error.result.json"])

    def test_a_core_error_that_escapes_the_run_is_an_error_notice_and_is_not_raised(self):
        S.decide(self.w, [1, 2, 3])
        series = H.OddSeries(list(self.w.series.rows.values()), Decimal("100"), "some_other_definition")
        report = self.job(H.now_at(D[3]), series=series)
        self.assertEqual((report.run_outcome, report.kind, report.d, report.delivery, report.code),
                         (None, "error", D[3], "SENT", "soxl_price_definition_unknown"))
        self.assertIn("理由コード: soxl_price_definition_unknown（InputError）", self.last_text())

    def test_the_type_name_in_the_text_is_a_plain_identifier(self):
        class Odd(Exception):
            pass
        Odd.__name__ = "x" * 70 + " /secret"
        S.decide(self.w, [1])
        with self.assertRaises(Exception):
            self.job(H.now_at(D[2]), series=H.RaisingSeries(Odd("m")))
        self.assertIn("unexpected_error（Exception）", self.last_text())
        self.assertNotIn("secret", self.last_text())


class KeyIsTheTargetDate(H.Case):
    def test_a_manual_noon_run_and_the_next_scheduled_run_both_get_their_error_notice(self):
        # JST noon of the day after D1 closed is 03:00 UTC of D2's date (target D1); the scheduled run at 21:30 UTC
        # the same UTC day is after D2's close (target D2): the same UTC date, two different target days
        S.decide(self.w, [1])
        y, m, d = (int(x) for x in D[2].split("-"))
        noon_jst = datetime(y, m, d, 3, 0, tzinfo=H.UTC)
        scheduled = datetime(y, m, d, 21, 30, tzinfo=H.UTC)
        self.assertEqual(H.utc_date(noon_jst), H.utc_date(scheduled))
        for now, target in ((noon_jst, D[1]), (scheduled, D[2])):
            with self.assertRaises(ZeroDivisionError):
                self.job(now, series=H.RaisingSeries(ZeroDivisionError("x")))
        self.assertEqual(len(self.sender.texts), 2)
        self.assertEqual(H.names(self.oroot), [D[1] + "-error.claim.json", D[1] + "-error.result.json",
                                               D[2] + "-error.claim.json", D[2] + "-error.result.json"])
        self.assertIn("対象D=%s" % D[1], self.sender.texts[0])
        self.assertIn("対象D=%s" % D[2], self.sender.texts[1])

    def test_the_same_target_day_twice_is_sent_once_and_the_program_error_is_still_raised(self):
        S.decide(self.w, [1])
        for hour in (18, 19):
            with self.assertRaises(ZeroDivisionError):
                self.job(H.now_at(D[2], hour), series=H.RaisingSeries(ZeroDivisionError("x")))
        self.assertEqual(len(self.sender.texts), 1)


class AJudgmentStopsTheError(H.Case):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2, 3])

    def failing_rerun(self):
        error = ZeroDivisionError(SECRET)
        before = H.snapshot(self.oroot)
        with self.assertRaises(ZeroDivisionError) as ctx:                  # R-02: raised although nothing is sent
            self.job(H.now_at(D[3], 21), series=H.RaisingSeries(error), sender=self.rerun_sender)
        self.assertIs(ctx.exception, error)
        self.assertEqual(H.snapshot(self.oroot), before)
        self.assertEqual(self.rerun_sender.texts, [])

    def test_a_judgment_in_any_state_stops_a_later_error_of_the_same_day(self):
        self.rerun_sender = H.Sender()
        cases = (H.Sender("SENT"), H.Sender("NOT_STARTED"), H.Sender(TimeoutError("late")), H.Sender("???"))
        for sender in cases:
            self.setUp()
            self.job(H.now_at(D[3]), sender=sender)
            self.failing_rerun()
            self.assertNotIn(D[3] + "-error.claim.json", H.names(self.oroot))

    def test_a_damaged_judgment_stops_a_later_error_too(self):
        self.rerun_sender = H.Sender()
        self.job(H.now_at(D[3]))
        H.bwrite(self.oroot, D[3] + "-morning.result.json", b"{")
        self.failing_rerun()

    def test_the_report_of_a_skipped_error_says_so(self):
        self.job(H.now_at(D[3]))
        with self.assertRaises(ZeroDivisionError):
            self.job(H.now_at(D[3], 21), series=H.RaisingSeries(ZeroDivisionError("x")))
        # nothing was returned by the raising call; a CoreError that escapes the run is returned, so use that one
        series = H.OddSeries(list(self.w.series.rows.values()), Decimal("100"), "some_other_definition")
        report = self.job(H.now_at(D[3], 22), series=series)
        self.assertEqual((report.kind, report.delivery, report.exit_code), ("error", "SKIPPED_JUDGMENT_EXISTS", 1))

    def test_an_error_does_not_stop_a_judgment_of_the_same_day_that_follows_it(self):
        self.setUp()
        S.decide(self.w, [1, 2, 3])
        with self.assertRaises(ZeroDivisionError):
            self.job(H.now_at(D[3]), series=H.RaisingSeries(ZeroDivisionError("x")))
        report = self.job(H.now_at(D[3], 19))
        self.assertEqual((report.kind, report.delivery, report.exit_code), ("morning", "SENT", 0))
        self.assertEqual(len(self.sender.texts), 2)
        self.assertEqual(H.names(self.oroot), [D[3] + "-error.claim.json", D[3] + "-error.result.json",
                                               D[3] + "-morning.claim.json", D[3] + "-morning.result.json"])


if __name__ == "__main__":
    unittest.main()
