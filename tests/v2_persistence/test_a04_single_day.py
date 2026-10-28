"""A-04: preparing and committing a single D, re-running the same latest D, and what counts as the same input."""
import dataclasses
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import p_helpers as h
from v2_core import engine as core_engine
from v2_core.errors import InputError
from v2_persistence.errors import PersistenceError
from v2_persistence.recompute import validate_snapshot

D = h.DATES


def err(case, fn, *a, **k):
    with case.assertRaises((PersistenceError, InputError)) as cm:
        fn(*a, **k)
    return cm.exception


class PrepareThenCommit(unittest.TestCase):
    def test_new_day_is_prepared_only_then_committed(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        before = w.snap()
        res = w.prepare(D[1])
        self.assertEqual((res.status, res.committed), ("PREPARED", False))
        self.assertIsNotNone(res.plan)
        self.assertTrue(res.core_result.state_updated)          # core meaning: a new transition candidate
        self.assertEqual(w.snap(), before)                      # nothing stored by preparing
        self.assertEqual(w.snap().head_seq, 0)
        self.assertEqual((res.plan.expected_head_seq, res.plan.expected_head_hash), (0, before.head_hash))
        done = w.store.commit(res.plan)
        self.assertEqual((done.status, done.committed), ("COMMITTED", True))
        self.assertEqual(w.snap().head_seq, 1)
        self.assertEqual(len(w.snap().events), 2)
        self.assertEqual(done.snapshot, w.snap())

    def test_prepared_is_never_reported_as_committed(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        res = w.prepare(D[1])
        self.assertNotEqual(res.status, "COMMITTED")
        self.assertFalse(res.committed)
        self.assertFalse(hasattr(res, "snapshot"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            res.status = "COMMITTED"

    def test_no_decision_means_no_plan_and_nothing_appended(self):
        w = h.World()
        before = w.snap()
        res = w.prepare(D[1])
        self.assertEqual((res.status, res.plan, res.committed), ("NO_COMMIT", None, False))
        self.assertEqual(res.core_result.run_class.value, "WAITING_FG")
        self.assertFalse(res.core_result.state_updated)
        self.assertEqual(w.snap(), before)
        # supplemental / not_checked rows alone are not a decision
        w.ledger.append(h.obs("S1", D[1], 27.0, role="supplemental"))
        w.ledger.append(h.obs("N1", D[1], None, status="not_checked"))
        res = w.prepare(D[1])
        self.assertEqual(res.status, "NO_COMMIT")
        self.assertEqual(w.snap(), before)

    def test_immediate_rerun_is_already_applied_with_nothing_to_append(self):
        w = h.World()
        w.apply(D[1], 27.0)
        after = w.snap()
        res = w.prepare(D[1])
        self.assertEqual((res.status, res.plan, res.committed), ("ALREADY_APPLIED", None, False))
        self.assertFalse(res.core_result.state_updated)         # the core meaning is kept, not "saved"
        self.assertEqual(w.snap(), after)
        self.assertEqual(w.snap().head_seq, 1)

    def test_gap_then_commit_then_same_input_rerun(self):
        w = h.World()
        w.apply(D[1], 40.0)
        w.apply(D[4], 41.0)                                      # D2, D3 skipped
        snap = w.snap()
        self.assertEqual(snap.events[2]["skipped_sessions"], [D[2], D[3]])
        for _ in range(2):
            self.assertEqual(w.prepare(D[4]).status, "ALREADY_APPLIED")
        self.assertEqual(w.snap(), snap)

    def test_first_run_after_a_long_gap_records_skipped_sessions_but_core_gap_stays_false(self):
        w = h.World()
        res = w.apply(D[4], 27.0)
        ev = w.snap().events[1]
        self.assertEqual(ev["skipped_sessions"], [D[1], D[2], D[3]])
        self.assertFalse(ev["transition_result"]["gap"])         # as_of_d was null: the core's gap stays false
        self.assertEqual(res.status, "PREPARED")
        self.assertEqual(w.prepare(D[4]).status, "ALREADY_APPLIED")

    def test_older_days_are_still_intact_for_each_later_rerun(self):
        w = h.World()
        for i, v in ((1, 27.0), (2, 40.0), (3, 41.0), (6, 42.0)):
            w.apply(D[i], v)
            self.assertEqual(w.prepare(D[i]).status, "ALREADY_APPLIED", D[i])
        validate_snapshot(w.snap())


class SameInputIdentity(unittest.TestCase):
    def setUp(self):
        self.w = h.World()
        self.w.apply(D[1], 27.5)
        self.w.apply(D[2], 40.0)
        self.snap = self.w.snap()

    def rerun(self):
        res = self.w.prepare(D[2])
        self.assertEqual(res.status, "ALREADY_APPLIED")
        self.assertEqual(self.w.snap(), self.snap)
        return res

    def test_utc_spelling_duplicates_unrelated_rows_and_future_rows(self):
        from datetime import datetime
        base = self.w.ledger[1]
        other_tz = timezone(timedelta(hours=9))
        at = datetime.fromisoformat(base["observed_at_iso8601"]).astimezone(other_tz).isoformat()
        self.w.ledger[1] = dict(base, observed_at_iso8601=at)
        self.rerun()
        self.w.ledger.append(dict(self.w.ledger[1]))                                     # same row submitted twice
        utc_at = datetime.fromisoformat(base["observed_at_iso8601"]).astimezone(timezone.utc).isoformat()
        self.w.ledger.append(dict(base, observed_at_iso8601=utc_at))                     # same instant, UTC spelling
        self.rerun()
        self.w.ledger.append(h.obs("SUP", D[2], 12.0, role="supplemental"))               # supplemental for D
        self.w.ledger.append(h.obs("NC", D[2], None, status="not_checked"))
        self.rerun()
        self.w.ledger.append(h.obs("FUT", D[3], 55.0))                                    # a later day's decision
        self.w.ledger.append(h.obs("FUT2", D[9], 30.0))
        self.rerun()
        self.w.ledger.reverse()
        self.rerun()

    def test_next_session_confirmed_and_close_at_updates_do_not_matter(self):
        stored = self.snap.events[2]["confirmed_inputs"]["session_context"][-1]
        self.assertEqual(stored["date"], D[3])

        def newer(**changes):
            def f(s):
                return dataclasses.replace(s, **changes)
            return f
        later_close = datetime(2026, 3, 5, 16, 45, tzinfo=h.TZ)
        for overrides in ({D[3]: newer(confirmed=False)},
                          {D[3]: newer(close_at=later_close)},
                          {D[3]: newer(confirmed=False, close_at=later_close)}):
            self.w.sessions = h.make_sessions(overrides=overrides)
            self.rerun()
        # stored copy and hashes never change
        self.assertEqual(self.w.snap().events[2]["confirmed_inputs"]["session_context"][-1], stored)

    def test_next_session_open_at_or_date_change_stops(self):
        shifted = lambda s: dataclasses.replace(s, open_at=s.open_at + timedelta(minutes=30))
        self.w.sessions = h.make_sessions(overrides={D[3]: shifted})
        e = err(self, self.w.prepare, D[2])
        self.assertEqual((e.code, e.field), ("session_context_mismatch", "sessions"))
        self.assertEqual(self.w.snap(), self.snap)
        # the saved next session (D3) is gone from the list: its date is absent
        self.w.sessions = h.make_sessions([d for d in D if d != D[3]])
        e = err(self, self.w.prepare, D[2])
        self.assertEqual((e.code, e.field), ("session_context_missing", "sessions"))
        # an extra session squeezed between D2 and the saved next session
        self.w.sessions = h.make_sessions(overrides={D[2]: lambda s: dataclasses.replace(
            s, close_at=s.close_at + timedelta(hours=2))})
        e = err(self, self.w.prepare, D[2])
        self.assertEqual((e.code, e.field), ("session_context_mismatch", "sessions"))     # D's own close_at counts
        self.assertEqual(self.w.snap(), self.snap)

    def test_market_number_change_stops_even_when_the_judgement_would_not_change(self):
        for per_date in ({D[2]: dict(soxx=111.0)},                  # D row, no change in market side
                         {D[2]: dict(soxx=90.0)},                   # D row, market side changes
                         {D[1]: dict(soxx=111.0)},                  # previous day row
                         {D[2]: dict(rsi=50.5)}, {D[2]: dict(shd=-1.5)}, {D[2]: dict(sma=100.5)},
                         {D[2]: dict(prev_rsi=48.0)}):
            self.w.series = h.make_series(per_date=per_date)
            e = err(self, self.w.prepare, D[2])
            self.assertEqual((e.code, e.field), ("recompute_mismatch", "confirmed_inputs"), per_date)
            self.assertEqual(self.w.snap(), self.snap)

    def test_unusable_previous_row_changes_the_saved_input(self):
        series = h.make_series()
        series.rows.pop(D[1])                                         # previous row no longer available
        series.dates = sorted(series.rows)
        self.w.series = series
        e = err(self, self.w.prepare, D[2])
        self.assertIn(e.code, ("recompute_mismatch", "session_series_mismatch"))

    def test_recompute_mismatch_order_is_input_then_transition_then_state(self):
        real = core_engine.apply_transition
        for change, field in (({"effective_streak": 9}, "transition_result"),
                              ({"gap": True}, "transition_result")):
            def altered(*a, **k):
                return dataclasses.replace(real(*a, **k), **change)
            with mock.patch.object(core_engine, "apply_transition", altered):
                e = err(self, self.w.prepare, D[2])
            self.assertEqual((e.code, e.field), ("recompute_mismatch", field), change)

        def other_state(*a, **k):
            t = real(*a, **k)
            ns = t.next_state
            return dataclasses.replace(t, next_state=dataclasses.replace(ns, armed=ns.armed.__class__.FALSE))
        with mock.patch.object(core_engine, "apply_transition", other_state):
            e = err(self, self.w.prepare, D[2])
        self.assertEqual((e.code, e.field), ("recompute_mismatch", "state"))
        self.assertEqual(self.w.snap(), self.snap)

    def test_an_input_change_wins_over_a_transition_change(self):
        real = core_engine.apply_transition
        self.w.series = h.make_series(per_date={D[2]: dict(soxx=111.0)})
        with mock.patch.object(core_engine, "apply_transition",
                               lambda *a, **k: dataclasses.replace(real(*a, **k), effective_streak=9)):
            e = err(self, self.w.prepare, D[2])
        self.assertEqual((e.code, e.field), ("recompute_mismatch", "confirmed_inputs"))


if __name__ == "__main__":
    unittest.main()
