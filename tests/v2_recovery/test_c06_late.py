"""C-06 ACK/LATE: a late row for a skipped or declared day is excluded; no fixed decision, no supplement."""
import unittest

import r_helpers as H
from r_helpers import D, R


class LateAfterSkippedSessions(unittest.TestCase):
    """X-17b: the missing reference is an APPLY whose skipped_sessions contain D."""

    def setUp(self):
        self.w = H.world(0)
        self.w.apply(D[3], 27.0, "R3")                      # D1 and D2 are skipped by this APPLY
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.r3 = self.w.ledger[0]
        self.late1 = H.P.obs("L1", D[1], 20.0)
        self.ref = H.apply_missing(self.snap, 1)

    def test_the_late_row_stops_without_an_acknowledgement(self):
        H.expect_code(self, "late_observation", H.resolve, self.w, self.rs, [self.r3, self.late1], D[3])

    def test_late_is_accepted_without_apply_of_d_and_without_a_supplement(self):
        self.assertEqual(self.snap.events[1]["skipped_sessions"], [D[1], D[2]])
        res = H.run(self.w, self.rs, [H.late(D[1], [H.fp(self.late1)], self.ref)], [self.r3, self.late1], D[3])
        eff = res.effective_ledger
        self.assertEqual(eff.rows, [H.cols(self.r3)])
        self.assertEqual(eff.supplemented, [])
        self.assertEqual(eff.excluded_fingerprints, [H.fp(self.late1)])
        rec = res.resolutions.records[0]
        self.assertIsNone(rec["applied_ref"])
        self.assertEqual(rec["missing_ref"], self.ref)

    def test_wrong_references_are_refused(self):
        row = self.late1
        bad_hash = dict(self.ref, event_hash="6" * 64)
        no_such = dict(self.ref, seq=7)
        for name, ref in {"hash": bad_hash, "no_such_apply": no_such, "none": None}.items():
            with self.subTest(name):
                H.expect_rule(self, "late_missing_ref", H.plan_for, self.w, self.rs,
                              [H.late(D[1], [H.fp(row)], ref)], [self.r3, row], D[3])

    def test_the_day_must_be_in_skipped_sessions_of_that_apply(self):
        row4 = H.P.obs("L4", D[4], 20.0)
        H.expect_rule(self, "late_missing_ref", H.plan_for, self.w, self.rs,
                      [H.late(D[4], [H.fp(row4)], self.ref)], [self.r3, row4], D[4])

    def test_a_day_with_an_apply_is_refused(self):
        row = H.P.obs("L3", D[3], 20.0)
        H.expect_rule(self, "late_missing_ref", H.plan_for, self.w, self.rs,
                      [H.late(D[3], [H.fp(row)], self.ref)], [self.r3, row], D[3])

    def test_empty_list_applied_ref_and_unrelated_row(self):
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, [H.late(D[1], [], self.ref)],
                      [self.r3], D[3])
        with_applied = dict(H.late(D[1], [H.fp(self.late1)], self.ref), applied_ref=H.ref_of(self.snap, 1))
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, [with_applied], [self.r3, self.late1], D[3])
        elsewhere = H.P.obs("L9", D[7], 20.0)
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs,
                      [H.late(D[1], [H.fp(elsewhere)], self.ref)], [self.r3, elsewhere], D[3])
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs,
                      [H.late(D[1], ["7" * 64], self.ref)], [self.r3], D[3])        # a changed fingerprint

    def test_it_cannot_hide_a_fixed_row(self):
        H.expect_rule(self, "exclude_applied", H.plan_for, self.w, self.rs,
                      [H.late(D[1], [H.fp(self.r3)], self.ref)], [self.r3], D[3])

    def test_excluding_one_version_of_a_shared_id_is_a_version_choice(self):
        x1 = H.P.obs("X1", D[1], 20.0)
        x2 = H.P.obs("X1", D[2], 21.0)                      # the same id, another unprocessed day
        H.expect_rule(self, "version_selection", H.plan_for, self.w, self.rs,
                      [H.late(D[1], [H.fp(x1)], self.ref)], [self.r3, x1, x2], D[3])
        both = [H.late(D[1], [H.fp(x1)], self.ref), H.late(D[2], [H.fp(x2)], self.ref)]
        res = H.run(self.w, self.rs, both, [self.r3, x1, x2], D[3])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r3)])


class LateAfterDeclaration(unittest.TestCase):
    """X-17c: the missing reference is an earlier DECLARE_MISSING record of the set."""

    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.r1 = self.w.ledger[0]
        res = H.run(self.w, R.empty_resolutions(), [H.declare(D[2])], [self.r1], D[2], rid="decl-1")
        self.rs = res.resolutions
        self.ref = H.declare_missing(self.rs, 1)
        self.late2 = H.P.obs("L2", D[2], 20.0)

    def test_new_row_after_the_declaration_stops_then_late_resolves_it(self):
        ledger = [self.r1, self.late2]
        H.expect_code(self, "late_observation", H.resolve, self.w, self.rs, ledger, D[2])
        res = H.run(self.w, self.rs, [H.late(D[2], [H.fp(self.late2)], self.ref)], ledger, D[2], rid="late-1")
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])
        self.assertEqual(res.effective_ledger.supplemented, [])
        self.assertEqual(R.validate_resolutions(self.snap, res.resolutions).record_count, 2)

    def test_the_declaration_is_found_by_number_hash_and_day(self):
        ledger = [self.r1, self.late2]
        for name, ref in {"hash": dict(self.ref, resolution_hash="8" * 64),
                          "number": dict(self.ref, resolution_seq=2),
                          "apply_namespace": H.apply_missing(self.snap, 1)}.items():
            with self.subTest(name):
                H.expect_rule(self, "late_missing_ref", H.plan_for, self.w, self.rs,
                              [H.late(D[2], [H.fp(self.late2)], ref)], ledger, D[2], rid="late-1")
        other_day = H.P.obs("L3", D[3], 20.0)
        H.expect_rule(self, "late_missing_ref", H.plan_for, self.w, self.rs,
                      [H.late(D[3], [H.fp(other_day)], self.ref)], [self.r1, other_day], D[3], rid="late-1")

    def test_a_target_day_after_check_d_is_refused_and_equal_is_accepted(self):
        ledger = [self.r1, self.late2]
        plan = H.plan_for(self.w, self.rs, [H.late(D[2], [H.fp(self.late2)], self.ref)], ledger, D[2], rid="l")
        self.assertEqual(plan.status, "READY")                 # D == check_d
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs,
                      [H.late(D[2], [H.fp(self.late2)], self.ref)], ledger, D[1], rid="l")   # D > check_d

    def test_a_declaration_set_does_not_stop_a_rerun_of_the_latest_apply(self):
        day = R.prepare_resolved_day(self.snap, self.rs, D[1], self.w.series, self.w.sessions, [self.r1])
        self.assertEqual(day.status, "ALREADY_APPLIED")


if __name__ == "__main__":
    unittest.main()
