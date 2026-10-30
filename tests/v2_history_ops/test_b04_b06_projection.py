"""B2-04 (all segments and the current segment, example V), B2-05 (order and rules of the projection) and B2-06
(session ranges)."""
import copy
import random
import unittest
from unittest import mock

import ho_helpers as T
import v2_history_ops as O
import v2_recovery.project as RP

H, D, P, RH = T.H, T.D, T.P, T.RH


class ExampleV(unittest.TestCase):
    def setUp(self):
        self.b = T.example_v()
        self.h = self.b.history()
        self.w = self.b.w

    def test_1_old_segment_apply_is_compared(self):
        changed = P.obs("R-" + D[1], D[1], 31.0)                    # same id, another value
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, [changed], D[4])
        self.assertEqual((e.code, e.field, e.detail), ("ledger_mismatch", "observations", D[1]))

    def test_2_ack_for_an_old_segment_apply_and_check_d_at_the_boundary(self):
        changed = P.obs("R-" + D[1], D[1], 31.0)
        cmds = [T.ack_cmd(self.h, "CHANGED", D[1], [T.fp(changed)], 1)]
        plan = T.plan_for(self.h, cmds, self.w.sessions, [changed], D[4], "q3")
        self.assertEqual(plan.status, "READY")
        res = O.confirm_history_resolution_plan(plan, plan.plan_hash, self.h, self.w.sessions, [changed])
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["seq"], rec["kind"], rec["variant"], rec["parent_seq"]), (4, "ACK", "CHANGED", 3))
        self.assertEqual(rec["applied_ref"]["seq"], 1)
        # the stored row is supplemented, the changed version excluded
        self.assertEqual(res.ledger.supplemented, [rec["applied_ref"]])
        self.assertEqual(res.ledger.excluded_fingerprints, [T.fp(changed)])
        e = T.refusal(T.plan_for, self.h, cmds, self.w.sessions, [changed], D[3], "q3")
        self.assertEqual((e.code, e.field), ("target_not_after_boundary", "target_session_date"))

    def test_3_late_for_an_old_declaration(self):
        l2 = P.obs("L2", D[2], 22.0)
        ledger = list(self.w.ledger) + [l2]
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, ledger, D[4])
        self.assertEqual((e.code, e.detail), ("late_observation", D[2]))
        cmd = T.late_cmd(D[2], [T.fp(l2)], T.mref_decl(self.h, 2))
        plan, res = T.run_plan(self.h, [cmd], self.w.sessions, ledger, D[4], "q4")
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(res.batch.body["records"][0]["missing_ref"], T.mref_decl(self.h, 2))
        # the projection with the new LATE passes and excludes the late row
        self.assertEqual(res.ledger.excluded_fingerprints, [T.fp(l2)])

    def test_4_new_declaration_frontier_is_the_boundary(self):
        plan = T.plan_for(self.h, [T.decl_cmd(D[4])], self.w.sessions, self.w.ledger, D[4], "q5")
        rec = plan.basis["candidate_history"]["events"][-1]
        self.assertEqual((rec["kind"], rec["d"], rec["frontier_before"]), ("DECLARE_MISSING", D[4], D[3]))
        # the boundary day itself and the old declaration day cannot be declared again
        self.assertEqual(T.err(T.plan_for, self.h, [T.decl_cmd(D[3])], self.w.sessions, self.w.ledger, D[4], "q5"),
                         ("resolution_invalid", "commands", "declare_frontier"))
        self.assertEqual(T.err(T.plan_for, self.h, [T.decl_cmd(D[2])], self.w.sessions, self.w.ledger, D[4], "q5"),
                         ("resolution_invalid", "commands", "declare_frontier"))

    def test_5_day_after_the_restart(self):
        for d in (D[2], D[3]):
            e = T.refusal(O.prepare_history_day, self.h, d, self.w.series, self.w.sessions, self.w.ledger)
            self.assertEqual((e.code, e.field), ("target_not_after_boundary", "target_session_date"))
        ledger = list(self.w.ledger) + [P.obs("R4", D[4], 29.0)]
        res = O.prepare_history_day(self.h, D[4], self.w.series, self.w.sessions, ledger)
        self.assertEqual(res.status, "PREPARED")
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["seq"], rec["parent_seq"], rec["skipped_sessions"]), (4, 3, []))
        self.assertFalse(res.core_result.gap)
        # only GENESIS(D3) and the current segment's APPLY go to S1
        from v2_history_ops.chain import Chain
        import v2_history as V
        snap = Chain(self.h, V.validate_history(self.h)).current_snapshot()
        self.assertEqual([e["kind"] for e in snap.events], ["GENESIS"])
        self.assertEqual(snap.events[0]["start_after"], D[3])

    def test_5b_parent_is_the_physical_head_after_an_ack(self):
        changed = P.obs("R-" + D[1], D[1], 31.0)
        ledger = [changed, P.obs("R4", D[4], 29.0)]
        _, res = T.run_plan(self.h, [T.ack_cmd(self.h, "CHANGED", D[1], [T.fp(changed)], 1)], self.w.sessions,
                            ledger, D[4], "q3")
        h2 = T.extend(self.h, res)
        out = O.prepare_history_day(h2, D[4], self.w.series, self.w.sessions, ledger)
        rec = out.batch.body["records"][0]
        self.assertEqual((rec["seq"], rec["parent_seq"]), (5, 4))

    def test_6_boundary_day_decision_is_neither_processed_nor_a_late(self):
        l3 = P.obs("L3", D[3], 22.0)
        ledger = list(self.w.ledger) + [l3]
        led = O.project_history_ledger(self.h, self.w.sessions, ledger, D[4])      # not a stop
        self.assertEqual(len(led.rows), 2)
        # no command can name it as a LATE of the boundary day (not a skipped day, not a declared day)
        cmd = T.late_cmd(D[3], [T.fp(l3)], T.mref_decl(self.h, 2))
        self.assertEqual(T.err(T.plan_for, self.h, [cmd], self.w.sessions, ledger, D[4], "q7")[2], "late_missing_ref")
        # parsing and the record_id conflict check still apply to rows of that day
        clash = P.obs("L3", D[3], 23.0)
        e = T.refusal(O.project_history_ledger, self.h, self.w.sessions, ledger + [clash], D[4])
        self.assertEqual(e.code, "record_id_conflict")
        self.assertEqual(T.err(O.project_history_ledger, self.h, self.w.sessions, ledger + [{"record_id": "x"}], D[4])[0],
                         "status_unknown")

    def test_old_segment_declaration_and_apply_do_not_move_the_frontier(self):
        # the frontier of a declaration made now is the boundary, although an APPLY at D1 and a declaration at D2
        # exist in the old segment
        from v2_history_ops.chain import Chain
        facts = Chain(self.h, T.V.validate_history(self.h)).facts
        self.assertEqual(facts.latest_apply_day(facts.head_seq), D[3])
        self.assertEqual(facts.latest_day, D[1])
        self.assertEqual([x["d"] for x in facts.declares], [D[2]])


class OrderAndRules(unittest.TestCase):
    """B2-05"""

    def setUp(self):
        w, snap, rs, ledger, cd = H.example_m2_world()
        self.h = H.migrate(w, snap, rs, ledger, cd)
        self.w, self.ledger, self.cd = w, ledger, cd

    def project(self, ledger=None, check_d=None):
        return O.project_history_ledger(self.h, self.w.sessions, self.ledger if ledger is None else ledger,
                                        self.cd if check_d is None else check_d)

    def test_migrated_example_passes_with_exclusions_and_supplements(self):
        led = self.project()
        self.assertGreater(len(led.excluded_fingerprints), 0)
        self.assertGreater(len(led.supplemented), 0)
        self.assertEqual(led.check_d, self.cd)
        self.assertEqual(led.history_digest, self.h.digest)

    def test_spy_order_exclude_supplement_versions_final(self):
        calls = []

        def spy(name):
            real = getattr(RP, name)

            def wrapper(*a, **k):
                calls.append(name)
                return real(*a, **k)
            return wrapper
        with mock.patch.object(RP, "apply_records", spy("apply_records")), \
                mock.patch.object(RP, "check_versions", spy("check_versions")), \
                mock.patch.object(RP, "final_checks", spy("final_checks")), \
                mock.patch("v2_history_ops.read.resolve_core", spy("resolve_core")):
            self.project()
        self.assertEqual(calls, ["resolve_core", "apply_records", "check_versions", "final_checks"])

    def test_resolve_core_is_the_s3a_function(self):
        import v2_history_ops.read as read
        self.assertIs(read.resolve_core, RP.resolve_core)
        import v2_recovery.facts as F
        self.assertIs(F.slice_check, RP.slice_check)

    def test_supplement_once_per_apply(self):
        led = self.project()
        seqs = [s["seq"] for s in led.supplemented]
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_every_row_is_parsed_before_any_exclusion(self):
        calls = []
        with mock.patch("v2_history_ops.read.resolve_core",
                        lambda *a, **k: (calls.append("resolve"), RP.resolve_core(*a, **k))[1]):
            e = T.refusal(O.project_history_ledger, self.h, self.w.sessions,
                          self.ledger + [{"record_id": "bad"}], self.cd)
        self.assertEqual(calls, [])                      # the parse error comes before resolve_core
        self.assertEqual(e.code, "status_unknown")
        # a bad row stops even though an effective ACK excludes other rows
        self.assertGreater(len(self.project().excluded_fingerprints), 0)

    def test_inputs_are_not_changed(self):
        ledger = copy.deepcopy(self.ledger)
        sessions_before = list(self.w.sessions.sessions)
        text = self.h.to_dict()
        digest = self.h.digest
        led = self.project(ledger=ledger)
        self.assertEqual(ledger, self.ledger)
        self.assertEqual(list(self.w.sessions.sessions), sessions_before)
        self.assertEqual(self.h.digest, digest)
        self.assertEqual(self.h.to_dict(), text)
        # the result does not alias the input rows
        rows = led.rows
        rows[0]["record_id"] = "mutated"
        self.assertNotEqual(led.rows[0]["record_id"], "mutated")
        for r in ledger:
            self.assertNotEqual(r.get("record_id"), "mutated")

    def test_row_order_does_not_matter(self):
        base = self.project()
        rnd = random.Random(7)
        for _ in range(5):
            shuffled = list(self.ledger)
            rnd.shuffle(shuffled)
            led = self.project(ledger=shuffled)
            self.assertEqual(led.rows, base.rows)
            self.assertEqual(led.effective_digest, base.effective_digest)
            self.assertEqual(led.excluded_fingerprints, base.excluded_fingerprints)
            self.assertEqual(led.supplemented, base.supplemented)
        self.assertEqual(base.rows, sorted(base.rows, key=T.cj))

    def test_version_selection_is_refused(self):
        # D2's stored row exists in two versions and no effective record acknowledges the other one
        sessions = self.w.sessions
        extra = P.obs("R2", D[2], 33.0, hour=21)           # same record_id as the stored D2 row, other content
        e = T.refusal(O.project_history_ledger, self.h, sessions, self.ledger + [extra], self.cd)
        self.assertIn(e.code, ("record_id_conflict", "ledger_mismatch", "decision_conflict"))

    def test_result_is_a_value_not_the_s3a_ledger(self):
        led = self.project()
        self.assertIsInstance(led, O.HistoryLedger)
        self.assertFalse(hasattr(led, "resolutions_digest"))
        self.assertEqual(sorted(led.to_dict()), ["check_d", "effective_digest", "excluded_fingerprints",
                                                 "history_digest", "ledger_digest", "rows", "supplemented"])
        self.assertEqual(repr(led), "HistoryLedger(rows=%d, excluded=%d, supplemented=%d)" % (
            len(led.rows), len(led.excluded_fingerprints), len(led.supplemented)))


class SessionRanges(unittest.TestCase):
    """B2-06"""

    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)                  # context [D0, D1, D2]
        self.b, self.h, self.w = b, b.history(), b.w

    def sessions(self, overrides=None, unconfirmed=()):
        return P.make_sessions(overrides=overrides, unconfirmed=unconfirmed)

    @staticmethod
    def shift(**kw):
        def fn(s):
            return s.__class__(s.date, kw.get("open_at", s.open_at), kw.get("close_at", s.close_at),
                               kw.get("confirmed", s.confirmed))
        return fn

    def proj(self, sl, d=None):
        return O.project_history_ledger(self.h, sl, self.w.ledger, D[1] if d is None else d)

    def test_1_next_day_close_or_confirmed_changes_are_harmless(self):
        s = self.w.sessions.get(D[2])
        self.proj(self.sessions({D[2]: self.shift(close_at=s.close_at.replace(hour=15))}))
        self.proj(self.sessions({D[2]: self.shift(confirmed=False)}))
        e = T.refusal(O.prepare_history_day, self.h, D[2], self.w.series, self.sessions(unconfirmed={D[2]}),
                      self.w.ledger + [P.obs("R2", D[2], 28.0)])
        self.assertEqual(e.code, "target_unconfirmed")

    def test_2_open_close_and_boundary_changes_stop(self):
        sl = self.w.sessions
        cases = {
            "next open": (D[2], self.shift(open_at=sl.get(D[2]).open_at.replace(minute=45))),
            "day close": (D[1], self.shift(close_at=sl.get(D[1]).close_at.replace(hour=15))),
            "boundary open": (D[0], self.shift(open_at=sl.get(D[0]).open_at.replace(minute=15))),
            "boundary confirmed": (D[0], self.shift(confirmed=False)),
        }
        for name, (d, fn) in cases.items():
            with self.subTest(name):
                e = T.refusal(self.proj, self.sessions({d: fn}))
                self.assertEqual((e.code, e.field), ("session_context_mismatch", "sessions"))
        missing = P.make_sessions(dates=[x for x in P.DATES if x != D[0]])
        e = T.refusal(self.proj, missing, D[2])
        self.assertEqual((e.code, e.detail), ("session_context_missing", D[0]))

    def test_boundary_session_of_a_restart_is_compared_too(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restart(D[2], "q1")
        b.apply(D[3], 29.0)
        h = b.history()
        sl = b.w.sessions
        bad = self.sessions({D[2]: self.shift(open_at=sl.get(D[2]).open_at.replace(minute=45))})
        e = T.refusal(O.project_history_ledger, h, bad, b.w.ledger, D[3])
        self.assertEqual((e.code, e.detail), ("session_context_mismatch", D[2]))
        # an old segment's boundary is compared too (the GENESIS session D0)
        bad0 = self.sessions({D[0]: self.shift(close_at=sl.get(D[0]).close_at.replace(hour=15))})
        e = T.refusal(O.project_history_ledger, h, bad0, b.w.ledger, D[3])
        self.assertEqual((e.code, e.detail), ("session_context_mismatch", D[0]))

    def test_old_declaration_range_is_compared(self):
        b = T.example_v()
        sl = b.w.sessions
        # the declaration at D2 stores [D1, D2, D3]; change D2's open
        bad = self.sessions({D[2]: self.shift(open_at=sl.get(D[2]).open_at.replace(minute=45))})
        e = T.refusal(O.project_history_ledger, b.history(), bad, b.w.ledger, D[4])
        self.assertEqual(e.code, "session_context_mismatch")

    def test_3_intermediate_sessions(self):
        # D3 is processed after D1; D2 sits in between
        ledger = self.w.ledger + [P.obs("R3", D[3], 31.0)]
        e = T.refusal(O.prepare_history_day, self.h, D[3], self.w.series, self.sessions(unconfirmed={D[2]}), ledger)
        self.assertEqual((e.code, e.detail), ("intermediate_session_unconfirmed", D[2]))
        e = T.refusal(O.prepare_history_day, self.h, D[3], self.w.series, self.w.sessions,
                      ledger + [P.obs("R2", D[2], 28.0)])
        self.assertEqual((e.code, e.detail), ("intermediate_session_unprocessed", D[2]))
        early = P.obs("E2", D[2], 28.0, hour=10)                # targets D2 but observed before D2 closed
        e = T.refusal(O.prepare_history_day, self.h, D[3], self.w.series, self.w.sessions, ledger + [early])
        self.assertEqual(e.code, "decision_outside_window")

    def test_context_reads_do_not_use_the_sessions_object_identity(self):
        before = list(self.w.sessions.sessions)
        self.proj(self.w.sessions)
        self.assertEqual(list(self.w.sessions.sessions), before)
        e = T.refusal(O.project_history_ledger, self.h, "not sessions", self.w.ledger, D[1])
        self.assertEqual((e.code, e.field), ("sessions_invalid", "sessions"))


if __name__ == "__main__":
    unittest.main()
