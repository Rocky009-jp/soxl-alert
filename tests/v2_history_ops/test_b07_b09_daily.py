"""B2-07 (day results), B2-08 (the re-run invariant) and B2-09 (the day after a restart)."""
import unittest
from unittest import mock

import ho_helpers as T
import v2_history_ops as O
from v2_persistence.plan import AppendPlan, PrepareResult
from v2_persistence.runner import make_genesis, prepare_day

H, D, P, RH, V = T.H, T.D, T.P, T.RH, T.V

SIX = ("d", "confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after")


def s1_event(sessions, series, start_after, applies, d, ledger):
    """An independent S1 run: GENESIS(start_after) plus S1 APPLYs of `applies` (day, ledger) via prepare_day."""
    from v2_persistence.events import append_event
    snap = make_genesis(start_after, sessions)
    for ad in applies:
        res = prepare_day(snap, ad, series, sessions, ledger)
        snap = append_event(snap, res.plan.event)
    return prepare_day(snap, d, series, sessions, ledger)


class GenesisOnly(unittest.TestCase):
    """Design 12.1"""

    def setUp(self):
        self.w = P.World()
        self.h0 = V.make_history_genesis(self.w.start_after, self.w.sessions)
        self.ledger = [P.obs("R1", D[1], 27.0)]

    def day(self, h, d, ledger=None):
        return O.prepare_history_day(h, d, self.w.series, self.w.sessions, self.ledger if ledger is None else ledger)

    def test_flow_1(self):
        r1 = self.day(self.h0, D[1])
        self.assertEqual((r1.status, r1.committed, r1.committable), ("PREPARED", False, False))
        rec = r1.batch.body["records"][0]
        self.assertEqual((rec["kind"], rec["seq"], rec["parent_seq"], rec["skipped_sessions"]), ("APPLY", 1, 0, []))
        h1 = O.check_append_batch(self.h0, r1.batch)
        self.assertEqual(h1.head_seq, 1)
        r2 = self.day(h1, D[1])
        self.assertEqual((r2.status, r2.batch, r2.candidate_digest), ("ALREADY_APPLIED", None, None))
        # NO_COMMIT without a decision
        self.assertEqual(self.day(self.h0, D[1], []).status, "NO_COMMIT")
        self.assertEqual(self.day(h1, D[2]).status, "NO_COMMIT")
        # D3 with a decision after D2 (no decision): D2 is skipped
        ledger = self.ledger + [P.obs("R3", D[3], 31.0)]
        r3 = self.day(h1, D[3], ledger)
        self.assertEqual(r3.status, "PREPARED")
        self.assertEqual(r3.batch.body["records"][0]["skipped_sessions"], [D[2]])
        # D0 and an old batch
        e = T.refusal(self.day, self.h0, D[0])
        self.assertEqual((e.code, e.field), ("target_not_after_boundary", "target_session_date"))
        e = T.refusal(O.check_append_batch, h1, r1.batch)
        self.assertEqual((e.code, e.field), ("batch_stale", "head"))

    def test_core_result_keeps_its_core_meaning(self):
        r1 = self.day(self.h0, D[1])
        s1 = prepare_day(make_genesis(self.w.start_after, self.w.sessions), D[1], self.w.series, self.w.sessions,
                         self.ledger)
        self.assertEqual(r1.core_result, s1.core_result)
        self.assertTrue(r1.core_result.state_updated)
        h1 = O.check_append_batch(self.h0, r1.batch)
        again = self.day(h1, D[1])
        s1b = prepare_day(self.w.snap() if False else _snap_with(self.w, D[1], self.ledger), D[1], self.w.series,
                          self.w.sessions, self.ledger)
        self.assertEqual(again.core_result, s1b.core_result)
        self.assertEqual(again.status, "ALREADY_APPLIED")
        self.assertEqual(again.committed, False)


def _snap_with(w, d, ledger):
    from v2_persistence.events import append_event
    snap = make_genesis(w.start_after, w.sessions)
    res = prepare_day(snap, d, w.series, w.sessions, ledger)
    return append_event(snap, res.plan.event)


class ResultTable(unittest.TestCase):
    """Design 7.3"""

    def setUp(self):
        self.b = H.HB()
        self.b.apply(D[1], 27.0)
        self.b.apply(D[2], 28.0)
        self.h, self.w = self.b.history(), self.b.w

    def day(self, d, ledger=None, sessions=None, series=None, h=None):
        return O.prepare_history_day(self.h if h is None else h, d, self.w.series if series is None else series,
                                     self.w.sessions if sessions is None else sessions,
                                     self.w.ledger if ledger is None else ledger)

    def test_before_boundary_and_state_ahead(self):
        self.assertEqual(T.err(self.day, D[0])[:2], ("target_not_after_boundary", "target_session_date"))
        self.assertEqual(T.err(self.day, D[1])[:2], ("state_ahead_of_target", "state"))

    def test_same_day_re_run_and_recompute_mismatch(self):
        self.assertEqual(self.day(D[2]).status, "ALREADY_APPLIED")
        series = P.make_series(per_date={D[2]: {"soxx": 120.0}})
        e = T.refusal(self.day, D[2], series=series)
        self.assertEqual((e.code, e.field), ("recompute_mismatch", "confirmed_inputs"))

    def test_declared_day_and_undecided_day(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        h = b.history()
        r = O.prepare_history_day(h, D[2], b.w.series, b.w.sessions, b.w.ledger)
        self.assertEqual((r.status, r.batch), ("NO_COMMIT", None))
        self.assertEqual(self.day(D[3]).status, "NO_COMMIT")

    def test_decision_problems(self):
        ledger = self.w.ledger + [P.obs("R4", D[4], 31.0)]
        other = dict(P.obs("X4", D[4], 33.0, hour=20), target_us_session_date=D[5])   # in D4's window, targets D5
        e = T.refusal(self.day, D[4], ledger + [other])
        self.assertEqual((e.code, e.field), ("target_mismatch", "target_us_session_date"))
        self.assertEqual(T.refusal(self.day, D[4], ledger, sessions=P.make_sessions(unconfirmed={D[4]})).code,
                         "target_unconfirmed")
        short = P.make_sessions(dates=P.DATES[:5])
        self.assertEqual(T.refusal(self.day, D[4], ledger, sessions=short).code, "next_session_missing")
        self.assertEqual(T.err(self.day, D[4], ledger, sessions=P.make_sessions(dates=P.DATES[2:]))[0:2],
                         ("session_context_missing", "sessions"))

    def test_old_apply_ledger_and_skipped_days(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[3], 31.0)                               # skips D2
        h = b.history()
        late = P.obs("L2", D[2], 22.0)
        e = T.refusal(O.prepare_history_day, h, D[4], b.w.series, b.w.sessions, b.w.ledger + [late])
        self.assertEqual((e.code, e.detail), ("late_observation", D[2]))
        changed = [P.obs("R-" + D[1], D[1], 30.0)] + b.w.ledger[1:]
        e = T.refusal(O.prepare_history_day, h, D[4], b.w.series, b.w.sessions, changed)
        self.assertEqual((e.code, e.detail), ("ledger_mismatch", D[1]))
        # the ledger projection comes before the intermediate-session checks: both problems -> ledger_mismatch
        both = O.prepare_history_day
        e = T.refusal(both, h, D[4], b.w.series, P.make_sessions(unconfirmed={D[3]}), changed)
        self.assertIn(e.code, ("ledger_mismatch", "session_context_mismatch", "target_unconfirmed"))


class Delegation(unittest.TestCase):
    """prepare_day is called exactly once, on the current segment and the final ledger; the APPLY keeps the six items."""

    def test_one_call_with_the_current_segment_and_the_final_ledger(self):
        b = T.example_v()
        h, w = b.history(), b.w
        # a ledger where the final ledger differs from the raw one: an effective ACK excludes a row
        extra = P.obs("B1", D[1], 40.0, hour=21)
        changed_ledger = list(w.ledger) + [extra, P.obs("R4", D[4], 29.0)]
        cmd = T.ack_cmd(h, "ADDED", D[1], [T.fp(extra)], 1)
        _, res = T.run_plan(h, [cmd], w.sessions, changed_ledger, D[4], "q3")
        h2 = T.extend(h, res)
        calls = []
        real = prepare_day

        def spy(snapshot, d, series, sessions, ledger):
            calls.append((snapshot, d, ledger))
            return real(snapshot, d, series, sessions, ledger)
        with mock.patch("v2_history_ops.daily.prepare_day", spy):
            out = O.prepare_history_day(h2, D[4], w.series, w.sessions, changed_ledger)
        self.assertEqual(len(calls), 1)
        snapshot, d, ledger = calls[0]
        self.assertEqual(d, D[4])
        events = snapshot.events
        self.assertEqual([e["kind"] for e in events], ["GENESIS"])
        self.assertEqual(events[0]["start_after"], D[3])                    # only the current segment
        self.assertEqual(len(ledger), 2)                                    # the final ledger: extra excluded
        self.assertNotIn(T.fp(extra), [T.fp(r) for r in ledger])
        self.assertEqual(out.status, "PREPARED")

    def test_six_items_equal_the_s1_event_and_only_the_position_differs(self):
        for name, hb in (("genesis", None), ("restart", T.example_v())):
            with self.subTest(name):
                b = hb or H.HB()
                if hb is None:
                    b.apply(D[1], 27.0)
                    b.apply(D[2], 28.0)
                h, w = b.history(), b.w
                start = D[0] if hb is None else D[3]
                applies = [D[1], D[2]] if hb is None else []
                target = D[3] if hb is None else D[5]
                ledger = list(w.ledger) + [P.obs("RT", target, 31.0)]
                out = O.prepare_history_day(h, target, w.series, w.sessions, ledger)
                s1 = s1_event(w.sessions, w.series, start, applies, target, ledger)
                rec = out.batch.body["records"][0]
                for k in SIX:
                    self.assertEqual(T.cj(rec[k]), T.cj(s1.plan.event[k]), k)
                self.assertEqual((rec["seq"], rec["parent_seq"], rec["parent_hash"]),
                                 (h.head_seq + 1, h.head_seq, h.head_hash))
                if name == "restart":      # the temporary S1 numbering differs from the v2 one: so does the hash
                    self.assertNotEqual(rec["event_hash"], s1.plan.event["event_hash"])
                else:                      # genesis only: S1 and v2 number the first APPLY the same way
                    self.assertEqual(rec["event_hash"], s1.plan.event["event_hash"])
                from v2_persistence.codec import compute_event_hash
                self.assertEqual(rec["event_hash"], compute_event_hash(rec))
                self.assertEqual(out.core_result, s1.core_result)

    def test_parent_may_be_any_effective_head(self):
        # DECLARE_MISSING head
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        ledger = list(b.w.ledger) + [P.obs("R3", D[3], 31.0)]
        out = O.prepare_history_day(b.history(), D[3], b.w.series, b.w.sessions, ledger)
        self.assertEqual(out.batch.body["records"][0]["parent_seq"], 2)
        self.assertEqual(out.batch.body["records"][0]["skipped_sessions"], [D[2]])  # the declared day is skipped
        # RECOVERY_RESTORE head (a restore that drops an ACK and creates nothing)
        b2 = H.HB()
        b2.apply(D[1], 27.0)
        b2.apply(D[2], 28.0)
        extra = P.obs("B2", D[2], 40.0, hour=21)
        b2.ack("ADDED", D[2], [T.fp(extra)], "q1", applied=2)
        b2.restore(2, {3: "DROP"}, "q2")
        self.assertEqual(b2.events[-1]["kind"], "RECOVERY_RESTORE")
        ledger2 = list(b2.w.ledger) + [P.obs("R3", D[3], 31.0)]
        out2 = O.prepare_history_day(b2.history(), D[3], b2.w.series, b2.w.sessions, ledger2)
        rec2 = out2.batch.body["records"][0]
        self.assertEqual((rec2["seq"], rec2["parent_seq"]), (5, 4))
        h3 = O.check_append_batch(b2.history(), out2.batch)
        self.assertEqual(O.read_effective(h3).effective_seqs, [0, 1, 2, 4, 5])   # the restore is transparent
        # SCHEMA_MIGRATION head
        hb, (w, snap, rs, ledger3, cd) = H.example_m()
        led = ledger3 + [P.obs("R5", D[5], 31.0)]
        out3 = O.prepare_history_day(hb.history(), D[5], w.series, w.sessions, led)
        self.assertEqual(out3.batch.body["records"][0]["parent_seq"], 7)

    def test_no_s1_plan_is_returned(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        out = O.prepare_history_day(b.history(), D[1], b.w.series, b.w.sessions, b.w.ledger)
        self.assertFalse(hasattr(out, "plan"))
        self.assertNotIsInstance(out, (AppendPlan, PrepareResult))
        out = O.prepare_history_day(H.HB().history(), D[1], b.w.series, b.w.sessions, b.w.ledger)
        self.assertNotIsInstance(out.batch, (AppendPlan, PrepareResult))
        self.assertFalse(hasattr(out.batch, "expected_head_seq"))
        text = T.cj(out.batch.to_dict())
        # nothing of the temporary S1 numbering: the record carries v2 numbers only
        self.assertEqual(out.batch.body["records"][0]["seq"], 1)


class RerunInvariant(unittest.TestCase):
    """B2-08 / design 7.4"""

    def check_rerun(self, history, d, w, ledger):
        first = O.prepare_history_day(history, d, w.series, w.sessions, ledger)
        self.assertEqual(first.status, "PREPARED")
        second = O.prepare_history_day(history, d, w.series, w.sessions, ledger)
        self.assertEqual(first.batch.batch_hash, second.batch.batch_hash)      # deterministic
        self.assertEqual(first, second)
        new = O.check_append_batch(history, first.batch)
        again = O.prepare_history_day(new, d, w.series, w.sessions, ledger)
        self.assertEqual((again.status, again.batch, again.candidate_digest), ("ALREADY_APPLIED", None, None))
        return new

    def test_genesis_only(self):
        w = P.World()
        h0 = V.make_history_genesis(w.start_after, w.sessions)
        self.check_rerun(h0, D[1], w, [P.obs("R1", D[1], 27.0)])

    def test_after_migration(self):
        hb, (w, snap, rs, ledger, cd) = H.example_m()
        self.check_rerun(hb.history(), D[5], w, ledger + [P.obs("R5", D[5], 31.0)])

    def test_after_restart(self):
        b = T.example_v()
        self.check_rerun(b.history(), D[4], b.w, list(b.w.ledger) + [P.obs("R4", D[4], 29.0)])

    def test_after_restore(self):
        b = H.example_r()
        self.check_rerun(b.history(), D[7], b.w, list(b.w.ledger) + [P.obs("R7", D[7], 35.0)])

    def test_candidate_is_checked_at_preparation_time(self):
        w = P.World()
        h0 = V.make_history_genesis(w.start_after, w.sessions)
        ledger = [P.obs("R1", D[1], 27.0)]
        seen_validate, seen_ledger = [], []
        real_validate, real_ledger_of = V.validate_history, __import__("v2_history_ops.daily", fromlist=["x"]).ledger_of

        def validate(h):
            seen_validate.append(h.digest)
            return real_validate(h)

        def ledger_of(history, *a, **k):
            seen_ledger.append(history.digest)
            return real_ledger_of(history, *a, **k)
        with mock.patch("v2_history_ops.daily.validate_history", validate), \
                mock.patch("v2_history_ops.daily.ledger_of", ledger_of):
            out = O.prepare_history_day(h0, D[1], w.series, w.sessions, ledger)
        self.assertEqual(seen_validate, [h0.digest, out.candidate_digest])
        self.assertEqual(seen_ledger, [h0.digest, out.candidate_digest])

    def test_a_different_d_is_a_new_prepare_not_a_rerun(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        new = self.check_rerun(b.history(), D[2], b.w, list(b.w.ledger) + [P.obs("R2", D[2], 28.0)])
        self.assertEqual(new.head_seq, 2)


class AfterRestart(unittest.TestCase):
    """B2-09: the day rows of example U (S3-B 7.3) and design 12.3 (5)."""

    def setUp(self):
        self.b = H.example_u()                      # GENESIS D0, APPLY D1, APPLY D2, RESTART_UNKNOWN(D3)
        self.h, self.w = self.b.history(), self.b.w

    def day(self, d, ledger):
        return O.prepare_history_day(self.h, d, self.w.series, self.w.sessions, ledger)

    def test_at_or_before_the_boundary(self):
        for d in (D[3], D[2], D[1], D[0]):
            e = T.refusal(self.day, d, self.w.ledger)
            self.assertEqual((e.code, e.field), ("target_not_after_boundary", "target_session_date"), d)

    def test_first_day_after_the_restart(self):
        ledger = list(self.w.ledger) + [P.obs("R4", D[4], 31.0)]
        r = self.day(D[4], ledger)
        self.assertEqual(r.status, "PREPARED")
        self.assertEqual(r.batch.body["records"][0]["skipped_sessions"], [])
        ledger5 = list(self.w.ledger) + [P.obs("R5", D[5], 31.0)]
        r5 = self.day(D[5], ledger5)
        self.assertEqual(r5.batch.body["records"][0]["skipped_sessions"], [D[4]])

    def test_the_new_segment_starts_from_the_initial_state(self):
        ledger = list(self.w.ledger) + [P.obs("R4", D[4], 31.0)]
        r = self.day(D[4], ledger)
        s1 = s1_event(self.w.sessions, self.w.series, D[3], [], D[4], ledger)
        self.assertEqual(r.core_result, s1.core_result)
        self.assertEqual(T.cj(r.batch.body["records"][0]["state_after"]), T.cj(s1.plan.event["state_after"]))

    def test_the_last_day_of_the_previous_segment_is_not_reprocessed(self):
        e = T.refusal(self.day, D[2], self.w.ledger)                # D2 was the last APPLY before the restart
        self.assertEqual(e.code, "target_not_after_boundary")


if __name__ == "__main__":
    unittest.main()
