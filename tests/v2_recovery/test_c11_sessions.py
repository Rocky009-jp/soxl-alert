"""C-11: stored session ranges, the next(D) projection, whole-list digest for plans, ledger order and notation."""
import unittest

import r_helpers as H
from r_helpers import D, R


def row(record_id, d, value, hour=20):
    return H.P.obs(record_id, d, value, hour=hour)


def shifted(day, **kw):
    """A SessionList override that changes one session of the standard list."""
    def make(s):
        open_at = s.open_at + kw.get("open", H.P.timedelta(0))
        close_at = s.close_at + kw.get("close", H.P.timedelta(0))
        return s.__class__(s.date, open_at, close_at, kw.get("confirmed", s.confirmed))
    return H.P.make_sessions(overrides={day: make})


class AppliedWindow(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.rs = R.empty_resolutions()
        self.led = list(self.w.ledger)

    def resolve(self, sessions, check_d=D[1]):
        return R.resolve_observations(self.w.snap(), self.rs, sessions, self.led, check_d)

    def test_a_changed_open_time_of_the_next_session_stops(self):
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[2], open=H.P.timedelta(hours=1)))

    def test_changes_of_the_applied_day_or_before_stop(self):
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[1], close=H.P.timedelta(minutes=1)))
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[0], open=H.P.timedelta(minutes=1)))

    def test_only_close_time_or_confirmed_flag_of_the_next_session_is_accepted(self):
        for name, sl in {"close": shifted(D[2], close=H.P.timedelta(hours=1)),
                         "confirmed": shifted(D[2], confirmed=False)}.items():
            with self.subTest(name):
                self.assertEqual(self.resolve(sl).rows, [H.cols(self.led[0])])
                res = R.prepare_resolved_day(self.w.snap(), self.rs, D[1], self.w.series, sl, self.led)
                self.assertEqual(res.status, "ALREADY_APPLIED")

    def test_a_missing_session_stops(self):
        w = H.world(2)
        without_boundary = H.P.make_sessions(dates=D[1:])        # APPLY 1 saved D0 as the start of its context
        H.expect_code(self, "session_context_missing", R.resolve_observations, w.snap(), R.empty_resolutions(),
                      without_boundary, list(w.ledger), D[2])


class DeclaredWindow(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.led = list(self.w.ledger)
        self.rs = H.run(self.w, R.empty_resolutions(), [H.declare(D[2])], self.led, D[2], rid="d2").resolutions

    def resolve(self, sessions, check_d=D[1]):
        return R.resolve_observations(self.w.snap(), self.rs, sessions, self.led, check_d)

    def test_declared_context_is_compared_with_the_same_projection(self):
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[2], open=H.P.timedelta(hours=1)))
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[3], open=H.P.timedelta(hours=1)))
        H.expect_code(self, "session_context_mismatch", self.resolve, shifted(D[2], confirmed=False))
        self.resolve(shifted(D[3], close=H.P.timedelta(hours=1)))
        self.resolve(shifted(D[3], confirmed=False))

    def test_a_missing_needed_session_stops(self):
        short = H.P.make_sessions(dates=D[:3])               # ends at D2: next(D2) = D3 is missing
        H.expect_code(self, "session_context_missing", self.resolve, short)

    def test_a_time_revision_stops_in_the_run_of_a_new_day_too(self):
        with self.assertRaises(H.PersistenceError) as cm:
            R.prepare_resolved_day(self.w.snap(), self.rs, D[3], self.w.series,
                                   shifted(D[2], open=H.P.timedelta(hours=2)), self.led + [row("R3", D[3], 27.0)])
        self.assertEqual(cm.exception.code, "session_context_mismatch")


class NextSessionChangesOnlyInTheOrdinaryRun(unittest.TestCase):
    def test_the_plan_digest_is_stricter_than_the_ordinary_projection(self):
        w = H.world(1)
        rs = R.empty_resolutions()
        b = row("B1", D[1], 40.0, hour=21)
        led = list(w.ledger) + [b]
        plan = H.plan_for(w, rs, [H.ack(w.snap(), "ADDED", D[1], [H.fp(b)])], led, D[1])
        flipped = shifted(D[2], confirmed=False)
        done = R.confirm_resolution_plan(plan, plan.plan_hash, w.snap(), rs, w.sessions, led)
        # the ordinary projection accepts it ...
        R.resolve_observations(w.snap(), done.resolutions, flipped, led, D[1])
        # ... a plan made before the flip does not
        H.expect_code(self, "resolution_plan_stale", R.confirm_resolution_plan, plan, plan.plan_hash, w.snap(), rs,
                      flipped, led)


class LedgerOrderAndRepeats(unittest.TestCase):
    def test_order_notation_and_duplicates(self):
        w = H.world(1)
        rs = R.empty_resolutions()
        a = w.ledger[0]
        tz9 = H.P.timezone(H.P.timedelta(hours=9))
        y, m, d = (int(x) for x in D[2].split("-"))
        a_jst = dict(a, observed_at_iso8601=H.P.datetime(y, m, d, 10, 0, tzinfo=tz9).isoformat())
        e0 = R.resolve_observations(w.snap(), rs, w.sessions, [a], D[1])
        e1 = R.resolve_observations(w.snap(), rs, w.sessions, [a_jst], D[1])
        e2 = R.resolve_observations(w.snap(), rs, w.sessions, [a, a, a_jst], D[1])
        self.assertEqual(e0.rows, e1.rows)
        self.assertEqual(e0.rows, e2.rows)                    # identical rows become one in the final ledger
        self.assertEqual(e0.ledger_digest, e1.ledger_digest)  # the notation does not matter
        self.assertNotEqual(e0.ledger_digest, e2.ledger_digest)   # the count of identical rows does
        b = row("B1", D[1], 40.0, hour=21)
        c = row("C1", D[1], 41.0, hour=21)
        s1 = H.plan_for(w, rs, [H.ack(w.snap(), "ADDED", D[1], sorted([H.fp(b), H.fp(c)]))], [a, b, c], D[1])
        s2 = H.plan_for(w, rs, [H.ack(w.snap(), "ADDED", D[1], sorted([H.fp(b), H.fp(c)]))], [c, a, b], D[1])
        self.assertEqual(s1.plan_hash, s2.plan_hash)          # ledger order is not part of the plan


if __name__ == "__main__":
    unittest.main()
