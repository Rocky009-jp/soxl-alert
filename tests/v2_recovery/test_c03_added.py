"""C-03: ACK/ADDED excludes only the added rows; the stored row and the state stay as they are."""
import unittest

import r_helpers as H
from r_helpers import D, R


class AddedBasics(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]                                # the stored row "R1" for D1
        self.b = H.P.obs("B1", D[1], 40.0, hour=21)              # a second decision for D1 under another id

    def test_the_added_row_alone_is_excluded(self):
        ledger = [self.a, self.b]
        H.expect_code(self, "decision_conflict", H.resolve, self.w, self.rs, ledger, D[1])
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])], ledger, D[1])
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertFalse(res.committed)
        eff = res.effective_ledger
        self.assertEqual(eff.rows, [H.cols(self.a)])
        self.assertEqual(eff.excluded_fingerprints, [H.fp(self.b)])
        self.assertEqual(eff.supplemented, [])

    def test_stored_history_and_state_do_not_change(self):
        before_dict, before_state = self.snap.to_dict(), self.snap.current_state
        ledger = [self.a, self.b]
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])], ledger, D[1])
        self.assertEqual(self.w.snap().to_dict(), before_dict)
        self.assertEqual(self.w.snap().current_state, before_state)
        for rec in res.resolutions.records:
            self.assertEqual(rec["state_after"], before_state)
        # the raw ledger is not touched either
        self.assertEqual(ledger, [self.a, self.b])

    def test_confirmed_set_validates_and_day_stays_applied(self):
        ledger = [self.a, self.b]
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])], ledger, D[1])
        chk = R.validate_resolutions(self.snap, res.resolutions)
        self.assertEqual(chk.record_count, 1)
        day = R.prepare_resolved_day(self.snap, res.resolutions, D[1], self.w.series, self.w.sessions, ledger)
        self.assertEqual(day.status, "ALREADY_APPLIED")

    def test_added_row_with_other_offset_is_the_same_row(self):
        ledger = [self.a, self.b]
        tz9 = H.P.timezone(H.P.timedelta(hours=9))
        b_jst = H.P.obs("B1", D[1], 40.0, hour=21)
        # the same instant written in UTC+9: next day 11:00 JST == D1 21:00 at -05:00 -> 02:00Z next day == 11:00 JST
        y, m, d = (int(x) for x in D[2].split("-"))
        b_jst["observed_at_iso8601"] = H.P.datetime(y, m, d, 11, 0, tzinfo=tz9).isoformat()
        self.assertEqual(H.fp(b_jst), H.fp(self.b))
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])], [self.a, b_jst], D[1])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.a)])


class AddedRefusals(unittest.TestCase):
    def setUp(self):
        self.w = H.world(2)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a1, self.a2 = self.w.ledger
        self.b = H.P.obs("B1", D[1], 40.0, hour=21)

    def plan(self, cmds, ledger, check_d=D[2]):
        return H.plan_for(self.w, self.rs, cmds, ledger, check_d)

    def test_it_cannot_hide_the_fixed_row_of_another_apply(self):
        cmd = H.ack(self.snap, "ADDED", D[1], [H.fp(self.a2)])
        H.expect_rule(self, "exclude_applied", self.plan, [cmd], [self.a1, self.a2, self.b])

    def test_it_cannot_hide_its_own_fixed_row(self):
        cmd = H.ack(self.snap, "ADDED", D[1], [H.fp(self.a1)])
        H.expect_rule(self, "exclude_applied", self.plan, [cmd], [self.a1, self.a2, self.b])

    def test_no_evidence_when_the_original_is_missing(self):
        ledger = [self.a2, self.b]                                  # R1 is gone and nothing explains it
        cmd = H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])
        H.expect_rule(self, "ack_evidence", self.plan, [cmd], ledger)

    def test_same_record_id_is_a_changed_row_not_an_added_one(self):
        changed = H.P.obs("R1", D[1], 31.0, hour=21)
        cmd = H.ack(self.snap, "ADDED", D[1], [H.fp(changed)])
        H.expect_rule(self, "ack_evidence", self.plan, [cmd], [self.a1, self.a2, changed])

    def test_wrong_target_row_or_empty_or_unknown_fingerprint(self):
        elsewhere = H.P.obs("B9", D[5], 40.0)                      # another day, outside D1's window
        other_role = H.P.obs("B8", D[1], 40.0, role="supplemental", hour=21)
        for name, fps in {"elsewhere": [H.fp(elsewhere)], "supplemental": [H.fp(other_role)], "empty": [],
                          "unknown": ["0" * 64]}.items():
            with self.subTest(name):
                cmd = H.ack(self.snap, "ADDED", D[1], fps)
                H.expect_rule(self, "ack_evidence", self.plan, [cmd],
                              [self.a1, self.a2, self.b, elsewhere, other_role])

    def test_wrong_reference(self):
        base = H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])
        variants = {
            "fingerprint": dict(base["applied_ref"], fingerprint="1" * 64),
            "event_hash": dict(base["applied_ref"], event_hash="2" * 64),
            "other_apply": H.ref_of(self.snap, 2),
            "unknown_seq": dict(base["applied_ref"], seq=9),
        }
        for name, ref in variants.items():
            with self.subTest(name):
                cmd = dict(base, applied_ref=ref)
                H.expect_rule(self, "ack_evidence", self.plan, [cmd], [self.a1, self.a2, self.b])
        no_ref = dict(base, applied_ref=None)
        H.expect_rule(self, "ack_evidence", self.plan, [no_ref], [self.a1, self.a2, self.b])
        with_missing = dict(base, missing_ref={"kind": "APPLY", "seq": 1, "event_hash": self.snap.events[1]["event_hash"]})
        H.expect_rule(self, "ack_evidence", self.plan, [with_missing], [self.a1, self.a2, self.b])

    def test_target_equal_to_check_d_is_accepted(self):
        b2 = H.P.obs("B2", D[2], 41.0, hour=21)
        cmd = H.ack(self.snap, "ADDED", D[2], [H.fp(b2)], seq=2)
        plan = self.plan([cmd], [self.a1, self.a2, b2], check_d=D[2])
        self.assertEqual(plan.status, "READY")


class RemovedPlusAdded(unittest.TestCase):
    """N-02: the original row was deleted and another id was typed instead."""

    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]
        self.b = H.P.obs("B1", D[1], 40.0, hour=21)
        self.ledger = [self.b]                                       # A is deleted, B takes its place

    def commands(self, order):
        removed = H.ack(self.snap, "ROW_REMOVED", D[1], [])
        added = H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])
        return [removed, added] if order == "removed_first" else [added, removed]

    def test_both_orders_give_the_same_result(self):
        results = []
        for order in ("removed_first", "added_first"):
            with self.subTest(order):
                res = H.run(self.w, self.rs, self.commands(order), self.ledger, D[1])
                eff = res.effective_ledger
                self.assertEqual(eff.rows, [H.cols(self.a)])               # A supplemented once, B excluded
                self.assertEqual(len(eff.supplemented), 1)
                self.assertEqual(eff.excluded_fingerprints, [H.fp(self.b)])
                results.append(eff.effective_digest)
        self.assertEqual(results[0], results[1])

    def test_the_result_is_accepted_by_the_day_preparation(self):
        res = H.run(self.w, self.rs, self.commands("added_first"), self.ledger, D[1])
        day = R.prepare_resolved_day(self.snap, res.resolutions, D[1], self.w.series, self.w.sessions, self.ledger)
        self.assertEqual(day.status, "ALREADY_APPLIED")

    def test_added_alone_is_refused(self):
        added = H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, [added], self.ledger, D[1])

    def test_changed_plus_added(self):
        changed = H.P.obs("R1", D[1], 31.0, hour=21)
        ledger = [changed, self.b]
        cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)]),
                H.ack(self.snap, "CHANGED", D[1], [H.fp(changed)])]
        res = H.run(self.w, self.rs, cmds, ledger, D[1])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.a)])
        self.assertEqual(len(res.effective_ledger.supplemented), 1)

    def test_an_already_acknowledged_row_that_is_edited_again_stops(self):
        added = H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])
        res = H.run(self.w, self.rs, [added], [self.a, self.b], D[1])
        edited = H.P.obs("B1", D[1], 41.0, hour=21)                # B1 changed after the acknowledgement
        H.expect_code(self, "decision_conflict", H.resolve, self.w, res.resolutions, [self.a, edited], D[1])
        # both versions present: the acknowledged one is excluded and the new one would be an implicit choice
        H.expect_rule(self, "version_selection", H.resolve, self.w, res.resolutions, [self.a, self.b, edited], D[1])


if __name__ == "__main__":
    unittest.main()
