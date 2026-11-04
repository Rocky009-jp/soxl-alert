"""S4A-02 (arguments, before the store is touched) and S4A-03 (the target session)."""
import unittest
from datetime import datetime, timedelta, timezone, tzinfo

import s4a_helpers as S
import v2_daily_run as R
from v2_core.errors import CoreError
from v2_core.sessions import SessionList

D, P = S.D, S.P


class NoOffset(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return None


class Arguments(S.RootCase):
    def refusal(self, store, now, sessions, field):
        try:
            R.run_morning(store, now, self.w.series, sessions, self.w.ledger)
        except R.RunError as e:
            self.assertEqual((e.code, e.field), ("run_args_invalid", field))
            self.assertIsInstance(e, CoreError)
            self.assertEqual(e.exit_code, 1)
            return e
        self.fail("no RunError")

    def test_a_now_that_is_not_an_aware_datetime_is_refused_and_the_store_is_not_touched(self):
        bad = [datetime(2026, 3, 5, 18, 0), "2026-03-05T18:00:00-05:00", None, 1.0, S.now_at(D[3]).date(),
               datetime(2026, 3, 5, 18, 0, tzinfo=NoOffset())]
        for now in bad:
            silent = S.Silent()
            self.refusal(silent, now, self.w.sessions, "now")
            self.assertEqual(silent.calls, [], repr(now))

    def test_sessions_that_are_not_a_session_list_are_refused_and_the_store_is_not_touched(self):
        for sessions in (list(self.w.sessions.sessions), None, "sessions", self.w.sessions.sessions[0]):
            silent = S.Silent()
            self.refusal(silent, S.now_at(D[3]), sessions, "sessions")
            self.assertEqual(silent.calls, [])

    def test_a_store_without_the_three_methods_is_refused(self):
        class Only(object):
            pass
        for missing in ("read", "publish", "reconcile"):
            obj = Only()
            for name in ("read", "publish", "reconcile"):
                if name != missing:
                    setattr(obj, name, lambda *a, **k: None)
            self.refusal(obj, S.now_at(D[3]), self.w.sessions, "store")
        stale = Only()
        stale.read, stale.publish, stale.reconcile = None, lambda p: None, lambda p: None
        self.refusal(stale, S.now_at(D[3]), self.w.sessions, "store")
        self.refusal(object(), S.now_at(D[3]), self.w.sessions, "store")

    def test_the_first_wrong_argument_names_its_field_in_the_order_now_sessions_store(self):
        self.refusal(object(), datetime(2026, 3, 5), None, "now")
        self.refusal(object(), S.now_at(D[3]), None, "sessions")

    def test_no_session_closed_yet_is_a_run_error_before_the_store_is_touched(self):
        silent = S.Silent()
        for now in (S.close_at(D[0]) - timedelta(microseconds=1), datetime(2020, 1, 1, tzinfo=timezone.utc)):
            with self.assertRaises(R.RunError) as cm:
                R.run_morning(silent, now, self.w.series, self.w.sessions, self.w.ledger)
            self.assertEqual((cm.exception.code, cm.exception.field), ("run_no_closed_session", "sessions"))
        with self.assertRaises(R.RunError) as cm:
            R.run_morning(silent, S.now_at(D[3]), self.w.series, SessionList([]), self.w.ledger)
        self.assertEqual(cm.exception.code, "run_no_closed_session")
        self.assertEqual(silent.calls, [])


class Target(S.RootCase):
    def test_now_equal_to_the_close_is_that_session_and_a_microsecond_before_is_the_previous_one(self):
        store = self.store()
        for i in (3, 5, 9):
            at = S.close_at(D[i])
            self.assertEqual(S.run(store, self.w, at).target_d, D[i])
            self.assertEqual(S.run(store, self.w, at - timedelta(microseconds=1)).target_d, D[i - 1])
            self.assertEqual(S.run(store, self.w, at + timedelta(microseconds=1)).target_d, D[i])

    def test_the_same_instant_in_other_time_zones_gives_the_same_target_and_the_same_report(self):
        store = self.store()
        S.decide(self.w, [1, 2, 3])
        at = S.close_at(D[4])
        first = S.run(store, self.w, at)
        for zone in (timezone.utc, timezone(timedelta(hours=9)), timezone(timedelta(hours=-5)),
                     timezone(timedelta(hours=14))):
            again = S.run(store, self.w, at.astimezone(zone))
            self.assertEqual(again.target_d, D[4])
            self.assertEqual((again.outcome, again.message, again.history_digest, again.target_status),
                             (first.outcome, first.message, first.history_digest, first.target_status))

    def test_a_later_session_that_has_not_closed_is_never_the_target(self):
        store = self.store()
        report = S.run(store, self.w, S.now_at(D[4], hour=10))      # 10:00 on D4: D4 is open, D3 is the last closed
        self.assertEqual(report.target_d, D[3])

    def test_sessions_that_all_lie_in_the_future_raise_run_no_closed_session(self):
        store = self.store()
        with self.assertRaises(R.RunError) as cm:
            S.run(store, self.w, datetime(2026, 3, 1, tzinfo=S.TZ))
        self.assertEqual(cm.exception.code, "run_no_closed_session")


if __name__ == "__main__":
    unittest.main()
