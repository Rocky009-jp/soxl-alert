"""C-04 ACK/CHANGED and C-05 ACK/ROW_REMOVED: the stored decision is supplemented only when it is really missing."""
import unittest

import r_helpers as H
from r_helpers import D, R


class Base(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]
        self.stored = H.cols(self.a)

    def changed(self, value=31.0, **extra):
        row = H.P.obs("R1", D[1], value, hour=21)
        row.update(extra)
        return row


class Changed(Base):
    def test_replacement_without_the_original_supplements_exactly_one_row(self):
        c = self.changed()
        res = H.run(self.w, self.rs, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c)])], [c], D[1])
        eff = res.effective_ledger
        self.assertEqual(eff.rows, [self.stored])
        self.assertEqual(len(eff.supplemented), 1)
        self.assertEqual(eff.excluded_fingerprints, [H.fp(c)])
        day = R.prepare_resolved_day(self.snap, res.resolutions, D[1], self.w.series, self.w.sessions, [c])
        self.assertEqual(day.status, "ALREADY_APPLIED")

    def test_original_alongside_the_changed_row_is_not_supplemented_twice(self):
        c = self.changed()
        res = H.run(self.w, self.rs, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c)])], [self.a, c], D[1])
        eff = res.effective_ledger
        self.assertEqual(eff.rows, [self.stored])
        self.assertEqual(eff.supplemented, [])

    def test_the_original_at_another_utc_offset_counts_as_present(self):
        c = self.changed()
        tz9 = H.P.timezone(H.P.timedelta(hours=9))
        y, m, d = (int(x) for x in D[2].split("-"))
        a_jst = dict(self.a, observed_at_iso8601=H.P.datetime(y, m, d, 10, 0, tzinfo=tz9).isoformat())  # 20:00 at -05:00
        self.assertEqual(H.fp(a_jst), H.fp(self.a))
        res = H.run(self.w, self.rs, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c)])], [a_jst, c], D[1])
        self.assertEqual(res.effective_ledger.supplemented, [])
        self.assertEqual(len(res.effective_ledger.rows), 1)

    def test_changed_role_or_status_is_bound_by_fingerprint_and_not_adopted(self):
        for name, extra in {"role": dict(observation_role="supplemental"),
                            "status": dict(observation_status="not_checked", current_fg_value="",
                                           observed_at_iso8601="")}.items():
            with self.subTest(name):
                c = self.changed(**extra)
                res = H.run(self.w, self.rs, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c)])], [c], D[1])
                self.assertEqual(res.effective_ledger.rows, [self.stored])
                self.assertEqual(res.effective_ledger.supplemented[0]["seq"], 1)

    def test_refusals(self):
        c = self.changed()
        other_id = H.P.obs("Z1", D[1], 31.0, hour=21)
        cases = {
            "original_fingerprint": [H.fp(self.a)],
            "other_record_id": [H.fp(other_id)],
            "empty": [],
            "unknown": ["3" * 64],
        }
        for name, fps in cases.items():
            with self.subTest(name):
                cmd = H.ack(self.snap, "CHANGED", D[1], fps)
                expect = "exclude_applied" if name == "original_fingerprint" else "ack_evidence"
                H.expect_rule(self, expect, H.plan_for, self.w, self.rs, [cmd], [self.a, c, other_id], D[1])

    def test_a_not_yet_acknowledged_third_version_stops(self):
        c1, c2 = self.changed(31.0), self.changed(33.0)
        res = H.run(self.w, self.rs, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c1)])], [c1], D[1])
        # a second changed version appears later: the result is never a silent choice between versions
        H.expect_rule(self, "version_selection", H.resolve, self.w, res.resolutions, [c1, c2], D[1])


class RowRemoved(Base):
    def test_empty_ledger_is_confirmed_then_supplemented_then_checked(self):
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ROW_REMOVED", D[1], [])], [], D[1])
        eff = res.effective_ledger
        self.assertEqual(eff.rows, [self.stored])
        self.assertEqual(len(eff.supplemented), 1)
        self.assertEqual(eff.excluded_fingerprints, [])
        day = R.prepare_resolved_day(self.snap, res.resolutions, D[1], self.w.series, self.w.sessions, [])
        self.assertEqual(day.status, "ALREADY_APPLIED")

    def test_the_row_comes_back_and_is_not_supplemented_twice(self):
        res = H.run(self.w, self.rs, [H.ack(self.snap, "ROW_REMOVED", D[1], [])], [], D[1])
        eff = H.resolve(self.w, res.resolutions, [self.a], D[1])
        self.assertEqual(eff.rows, [self.stored])
        self.assertEqual(eff.supplemented, [])

    def test_refusals(self):
        base = H.ack(self.snap, "ROW_REMOVED", D[1], [])
        c = self.changed()
        bad = {
            "apply_ref_missing": (dict(base, applied_ref=None), []),
            "wrong_hash": (dict(base, applied_ref=dict(base["applied_ref"], event_hash="4" * 64)), []),
            "wrong_fingerprint": (dict(base, applied_ref=dict(base["applied_ref"], fingerprint="5" * 64)), []),
            "non_empty": (dict(base, record_fingerprints=[H.fp(c)]), [c]),
            "original_present": (base, [self.a]),
            "unacknowledged_changed_version": (base, [c]),
        }
        for name, (cmd, ledger) in bad.items():
            with self.subTest(name):
                H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, [cmd], ledger, D[1])

    def test_removed_plus_added_in_one_batch_and_added_alone(self):
        b = H.P.obs("B1", D[1], 40.0, hour=21)
        removed, added = H.ack(self.snap, "ROW_REMOVED", D[1], []), H.ack(self.snap, "ADDED", D[1], [H.fp(b)])
        res = H.run(self.w, self.rs, [removed, added], [b], D[1])
        self.assertEqual(res.effective_ledger.rows, [self.stored])
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, [added], [b], D[1])

    def test_one_supplement_per_apply_even_with_two_records_for_it(self):
        c = self.changed()
        removed_like = H.ack(self.snap, "CHANGED", D[1], [H.fp(c)])
        res = H.run(self.w, self.rs, [removed_like], [c], D[1], rid="req-1")
        # a later separate request about the same APPLY (another changed version) never supplements a second time
        c2 = self.changed(33.0)
        res2 = H.run(self.w, res.resolutions, [H.ack(self.snap, "CHANGED", D[1], [H.fp(c2)])], [c, c2], D[1],
                     rid="req-2")
        self.assertEqual(res2.effective_ledger.rows, [self.stored])
        self.assertEqual(len(res2.effective_ledger.supplemented), 1)


if __name__ == "__main__":
    unittest.main()
