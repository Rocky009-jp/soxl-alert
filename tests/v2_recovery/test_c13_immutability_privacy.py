"""C-13: independent copies, one-shot resolution of several places, same-id versions, and no free text in outputs."""
import copy
import unittest

import r_helpers as H
from r_helpers import D, R


def row(record_id, d, value, hour=20, **extra):
    r = H.P.obs(record_id, d, value, hour=hour)
    r.update(extra)
    return r


class Copies(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]
        self.b = row("B1", D[1], 40.0, hour=21)
        self.ledger = [self.a, self.b]
        self.cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])]
        self.plan = H.plan_for(self.w, self.rs, self.cmds, self.ledger, D[1])
        self.done = R.confirm_resolution_plan(self.plan, self.plan.plan_hash, self.snap, self.rs, self.w.sessions,
                                              self.ledger)

    def test_returned_nested_values_cannot_change_the_originals(self):
        before = copy.deepcopy((self.plan.to_dict(), self.done.resolutions.to_dict(), self.done.effective_ledger.rows))
        basis = self.plan.basis
        basis["candidate_resolutions"]["records"].clear()
        basis["commands"][0]["d"] = "x"
        self.plan.to_dict()["basis"]["check_d"] = "x"
        recs = self.done.resolutions.records
        recs[0]["record_fingerprints"].append("f" * 64)
        self.done.resolutions.to_dict()["records"].clear()
        rows = self.done.effective_ledger.rows
        rows[0]["current_fg_value"] = 99
        self.done.effective_ledger.raw_observations().clear()
        self.done.effective_ledger.excluded_fingerprints.append("e" * 64)
        self.done.effective_ledger.supplemented.append({})
        self.assertEqual(before, (self.plan.to_dict(), self.done.resolutions.to_dict(),
                                  self.done.effective_ledger.rows))
        # the plan still confirms after all of that
        R.confirm_resolution_plan(self.plan, self.plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)

    def test_day_result_core_result_is_a_copy(self):
        res = R.prepare_resolved_day(self.snap, self.done.resolutions, D[1], self.w.series, self.w.sessions, self.ledger)
        core = res.core_result
        core.rules.clear()
        core.notes.append("x")
        self.assertTrue(res.core_result.rules)
        self.assertNotIn("x", res.core_result.notes)

    def test_values_are_immutable_objects(self):
        for obj in (self.plan, self.done.resolutions, self.done.effective_ledger):
            with self.assertRaises(AttributeError):
                obj.something = 1
            with self.assertRaises(AttributeError):
                del obj._text
        res = R.prepare_resolved_day(self.snap, self.done.resolutions, D[1], self.w.series, self.w.sessions, self.ledger)
        with self.assertRaises(AttributeError):
            res.committed = True
        with self.assertRaises(TypeError):
            R.ResolutionSet()

    def test_inputs_are_copied_at_the_start(self):
        cmds = copy.deepcopy(self.cmds)
        ledger = copy.deepcopy(self.ledger)
        plan = H.plan_for(self.w, self.rs, cmds, ledger, D[1])
        cmds[0]["d"] = "mutated"
        cmds[0]["record_fingerprints"].append("0" * 64)
        ledger[1]["current_fg_value"] = 1.0
        ledger.clear()
        self.assertEqual(plan.basis["commands"], self.cmds)
        R.confirm_resolution_plan(plan, plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)

    def test_inputs_are_not_modified(self):
        snap_before, rs_before = self.snap.to_dict(), self.rs.to_dict()
        ledger_before, cmds_before = copy.deepcopy(self.ledger), copy.deepcopy(self.cmds)
        H.run(self.w, self.rs, self.cmds, self.ledger, D[1])
        self.assertEqual((self.snap.to_dict(), self.rs.to_dict(), self.ledger, self.cmds),
                         (snap_before, rs_before, ledger_before, cmds_before))

    def test_extra_columns_are_dropped_from_the_final_ledger(self):
        noisy = [dict(r, note="free text", source_url=H.URL) for r in self.ledger]
        eff = R.resolve_observations(self.snap, self.done.resolutions, self.w.sessions, noisy, D[1])
        self.assertEqual(set(eff.rows[0]), set(H.L.LEDGER_KEYS))


class OneShotAndStaleRows(unittest.TestCase):
    def test_several_unresolved_places_are_resolved_in_one_batch_or_not_at_all(self):
        w = H.world(2)
        snap = w.snap()
        rs = R.empty_resolutions()
        both_removed = [H.ack(snap, "ROW_REMOVED", D[1], [], seq=1), H.ack(snap, "ROW_REMOVED", D[2], [], seq=2)]
        # only one of the two days is explained: the other one stops, nothing is returned
        H.expect_code(self, "ledger_mismatch", H.plan_for, w, rs, both_removed[:1], [], D[2])
        res = H.run(w, rs, both_removed, [], D[2])
        self.assertEqual(len(res.effective_ledger.supplemented), 2)
        self.assertEqual(len(res.effective_ledger.rows), 2)

    def test_a_row_that_vanished_later_keeps_the_old_set_structurally_valid(self):
        w = H.world(1)
        snap = w.snap()
        b = row("B1", D[1], 40.0, hour=21)
        done = H.run(w, R.empty_resolutions(), [H.ack(snap, "ADDED", D[1], [H.fp(b)])], [w.ledger[0], b], D[1])
        R.validate_resolutions(snap, done.resolutions)
        eff = R.resolve_observations(snap, done.resolutions, w.sessions, [w.ledger[0]], D[1])   # B1 is gone
        self.assertEqual(eff.excluded_fingerprints, [])
        # a new mismatch is still caught by the final check
        H.expect_code(self, "decision_conflict", R.resolve_observations, snap, done.resolutions, w.sessions,
                      [w.ledger[0], row("Z9", D[1], 44.0, hour=22)], D[1])


class SameIdAcrossUnprocessedDays(unittest.TestCase):
    def test_added_cannot_select_one_of_two_versions(self):
        w = H.world(1)
        snap = w.snap()
        x1 = row("X1", D[1], 40.0, hour=21)                          # in D1's window, for D1
        x2 = row("X1", D[2], 41.0)                                   # the same id for the next unprocessed day
        ledger = [w.ledger[0], x1, x2]
        H.expect_rule(self, "version_selection", H.plan_for, w, R.empty_resolutions(),
                      [H.ack(snap, "ADDED", D[1], [H.fp(x1)])], ledger, D[1])

    def test_changed_next_to_the_fixed_old_version_is_allowed(self):
        w = H.world(1)
        snap = w.snap()
        c = row("R1", D[1], 31.0, hour=21)
        res = H.run(w, R.empty_resolutions(), [H.ack(snap, "CHANGED", D[1], [H.fp(c)])], [w.ledger[0], c], D[1])
        self.assertEqual(res.effective_ledger.rows, [H.cols(w.ledger[0])])


class NoFreeText(unittest.TestCase):
    def test_urls_and_notes_never_reach_a_repr_an_error_or_a_plan(self):
        w = H.world(1)
        snap = w.snap()
        noisy_a = dict(w.ledger[0], note=H.URL, source_url=H.URL)
        b = row("B1", D[1], 40.0, hour=21, note=H.URL, source_url=H.URL)
        cmds = [H.ack(snap, "ADDED", D[1], [H.fp(b)])]
        plan = H.plan_for(w, R.empty_resolutions(), cmds, [noisy_a, b], D[1])
        done = R.confirm_resolution_plan(plan, plan.plan_hash, snap, R.empty_resolutions(), w.sessions, [noisy_a, b])
        day = R.prepare_resolved_day(snap, done.resolutions, D[1], w.series, w.sessions, [noisy_a, b])
        texts = [repr(plan), repr(plan.summary()), repr(done), repr(done.resolutions), repr(done.effective_ledger),
                 repr(day), repr(R.validate_resolutions(snap, done.resolutions)), R.encode_resolutions(done.resolutions),
                 H.cj(plan.to_dict()), repr(sorted(done.effective_ledger.rows[0]))]
        errors = []
        for fn in (lambda: H.plan_for(w, R.empty_resolutions(), cmds, [noisy_a, dict(b, current_fg_value=H.URL)], D[1]),
                   lambda: H.resolve(w, R.empty_resolutions(), [noisy_a, b], D[1]),
                   lambda: H.plan_for(w, R.empty_resolutions(), [H.declare(D[2], [H.fp(b)])], [noisy_a, b], D[2])):
            with self.assertRaises((H.PersistenceError, H.InputError, H.ConflictError)) as cm:
                fn()
            errors.append(str(cm.exception) + repr(cm.exception) + repr(getattr(cm.exception, "detail", None))
                          + repr(getattr(cm.exception, "rule", None)))
        for text in texts + errors:
            self.assertNotIn("secret-token", text)
            self.assertNotIn("example.invalid", text)
            self.assertNotIn("free text", text)

    def test_error_text_is_fixed_code_field_rule_only(self):
        w = H.world(1)
        with self.assertRaises(H.PersistenceError) as cm:
            H.plan_for(w, R.empty_resolutions(), [H.declare(D[2], ["a" * 64])], list(w.ledger), D[2])
        e = cm.exception
        self.assertEqual((e.code, e.field), ("resolution_invalid", "commands"))
        self.assertEqual(str(e), "resolution_invalid:commands")
        self.assertIsNone(e.__cause__)


if __name__ == "__main__":
    unittest.main()
