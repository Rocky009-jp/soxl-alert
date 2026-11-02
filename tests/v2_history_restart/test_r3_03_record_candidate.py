"""B3-06 (record and candidate), B3-07 (physical head as the parent), B3-08 (request ids), B3-09 (plan binding)."""
import unittest
from unittest import mock

import r3_helpers as R

T, H, X, D, P, V, O = R.T, R.H, R.X, R.D, R.P, R.V, R.O
from v2_history.values import RESTART_KEYS  # noqa: E402

BASIS20 = ["operation", "status", "history_digest", "expected_head_seq", "expected_head_hash", "expected_state_digest",
           "resume_after", "check_d", "request_id", "request_hash", "reason_code", "requested_at", "floor",
           "boundary_session", "ledger_digest", "sessions_digest", "effective_digest", "candidate_history",
           "candidate_digest", "candidate_state_digest"]
CONFLICT = ("history_request_conflict", "request_id", None)


class RecordAndCandidate(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.h = self.b.history()
        self.w = self.b.w
        self.plan = R.prep(self.h, self.w, D[3], D[4], "r1")
        self.basis = self.plan.basis
        self.cand = X.confirm_restart_plan(self.plan, self.plan.plan_hash, self.h, self.w.sessions, self.w.ledger).history

    def test_the_record_has_the_fifteen_keys_and_the_fixed_values(self):
        rec = self.basis["candidate_history"]["events"][-1]
        self.assertEqual(set(rec), set(RESTART_KEYS))
        self.assertEqual(len(rec), 15)
        self.assertEqual((rec["kind"], rec["seq"], rec["parent_seq"]), ("RESTART_UNKNOWN", 3, 2))
        self.assertEqual(rec["parent_hash"], self.h.head_hash)
        self.assertEqual(rec["reason_code"], "RESTART_UNKNOWN")
        self.assertIsNone(rec["replay_of"])
        self.assertEqual(rec["state_after"], H.initial_state())
        self.assertEqual(rec["boundary_session"], H.sess(D[3]))
        self.assertEqual(rec["floor"], {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(rec["event_hash"], H.hash_of(rec))
        self.assertNotIn("plan_hash", rec)
        self.assertNotIn("batch_hash", rec)

    def test_the_request_basis_has_five_keys_and_the_request_hash_leaves_out_the_time(self):
        rec = self.basis["candidate_history"]["events"][-1]
        rb = rec["request_basis"]
        self.assertEqual(sorted(rb), sorted(["request_id", "resume_after", "check_d", "reason_code", "requested_at"]))
        self.assertEqual(rb, {"request_id": "r1", "resume_after": D[3], "check_d": D[4],
                              "reason_code": "RESTART_UNKNOWN", "requested_at": "2026-06-01T00:00:00Z"})
        self.assertEqual(rec["request_hash"], H.request_hash(rb))
        self.assertEqual(rec["requested_at"], rb["requested_at"])

    def test_the_plan_basis_has_the_twenty_keys_and_the_hash_covers_all_of_it(self):
        self.assertEqual(sorted(self.basis), sorted(BASIS20))
        self.assertEqual(len(self.basis), 20)
        self.assertEqual(self.basis["operation"], "soxl-v2-history-restart-plan/1")
        self.assertEqual(self.basis["status"], "READY")
        self.assertEqual(self.plan.plan_hash, H.sha(R.cj(self.basis)))
        self.assertEqual(self.plan.to_dict(), {"basis": self.basis, "plan_hash": self.plan.plan_hash})

    def test_it_equals_what_the_independent_builder_writes(self):
        rec = self.basis["candidate_history"]["events"][-1]
        self.assertEqual(rec, R.expected_restart(self.b, D[3], "r1", D[4]))

    def test_the_candidate_keeps_every_past_event_and_adds_exactly_one(self):
        old, new = self.h.events, self.cand.events
        self.assertEqual(len(new), len(old) + 1)
        self.assertEqual(R.cj(new[:-1]), R.cj(old))
        before, after = V.validate_history(self.h), V.validate_history(self.cand)
        self.assertEqual(after.effective_seqs, before.effective_seqs + (3,))
        self.assertEqual(after.superseded_seqs, before.superseded_seqs)
        self.assertEqual((after.current_boundary.kind, after.current_boundary.seq, after.current_boundary.after),
                         ("RESTART_UNKNOWN", 3, D[3]))
        self.assertEqual(self.cand.current_state, H.initial_state())
        self.assertEqual(after.state_digest, self.basis["candidate_state_digest"])
        self.assertEqual(after.state_digest, H.sha(R.cj(H.initial_state())))
        self.assertEqual(before.state_digest, self.basis["expected_state_digest"])
        self.assertEqual(self.cand.digest, self.basis["candidate_digest"])
        self.assertEqual(self.h.digest, self.basis["history_digest"])
        self.assertEqual((self.basis["expected_head_seq"], self.basis["expected_head_hash"]),
                         (before.head_seq, before.head_hash))

    def test_validate_history_really_runs_on_the_candidate(self):
        real = V.validate_history
        with mock.patch("v2_history_restart.build.validate_history", wraps=real) as spy:
            R.prep(self.h, self.w, D[3], D[4], "r2")
        seen = [c[0][0].digest for c in spy.call_args_list]
        self.assertEqual(seen[0], self.h.digest)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[-1], R.confirm(R.prep(self.h, self.w, D[3], D[4], "r2"), self.h, self.w).history.digest)

    def test_the_effective_facts_do_not_change(self):
        old, new = O.read_effective(self.h), O.read_effective(self.cand)
        self.assertEqual(new.applies, old.applies)
        self.assertEqual(new.resolutions, old.resolutions)
        self.assertEqual(new.segments[:-1], old.segments)
        self.assertEqual(new.segments[-1]["kind"], "RESTART_UNKNOWN")

    def test_a_history_with_retired_records_keeps_them_and_does_not_revive_them(self):
        b = H.example_r()
        h = b.history()
        plan = R.prep(h, b.w, D[7], D[8], "r1")
        cand = R.confirm(plan, h, b.w).history
        before, after = V.validate_history(h), V.validate_history(cand)
        self.assertTrue(before.superseded_seqs)
        self.assertEqual(after.superseded_seqs, before.superseded_seqs)
        self.assertEqual(R.cj(cand.events[:-1]), R.cj(h.events))

    def test_the_plan_does_not_apply_anything_and_the_inputs_stay_as_they_were(self):
        self.assertFalse(self.plan.committed)
        self.assertEqual(self.h.digest, self.basis["history_digest"])


class ParentIsThePhysicalHead(unittest.TestCase):
    def check(self, builder, resume, check_d):
        h = builder.history()
        plan = R.prep(h, builder.w, resume, check_d, "r1")
        rec = plan.basis["candidate_history"]["events"][-1]
        self.assertEqual((rec["parent_seq"], rec["parent_hash"]), (h.head_seq, h.head_hash))
        self.assertEqual(R.confirm(plan, h, builder.w).status, "CONFIRMED_IN_MEMORY")
        return h, rec

    def test_parent_ack(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        extra = P.obs("B1", D[1], 40.0, hour=21)
        b.w.ledger.append(extra)
        b.ack("ADDED", D[1], [T.fp(extra)], "q1", applied=1)
        h, _ = self.check(b, D[2], D[3])
        self.assertEqual(h.events[-1]["kind"], "ACK")

    def test_parent_declare_not_the_last_apply(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        h, rec = self.check(b, D[3], D[3])
        self.assertEqual(h.events[-1]["kind"], "DECLARE_MISSING")
        last_apply = max(e["seq"] for e in h.events if e["kind"] == "APPLY")
        self.assertNotEqual(rec["parent_seq"], last_apply)

    def test_parent_restore(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.restore(1, {2: "REAPPLY"}, "q1")
        h = b.history()
        self.assertEqual(h.events[-1]["kind"], "APPLY")        # the restore is followed by the re-created record
        b2 = H.HB()
        b2.apply(D[1], 27.0)
        b2.declare(D[2], "q1")
        b2.restore(1, {2: "DROP"}, "q2")
        h2, _ = self.check(b2, D[1], D[2])
        self.assertEqual(h2.events[-1]["kind"], "RECOVERY_RESTORE")

    def test_parent_restart(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restart(D[2], "q1")
        h, _ = self.check(b, D[3], D[3])
        self.assertEqual(h.events[-1]["kind"], "RESTART_UNKNOWN")

    def test_parent_migration_and_the_migrated_sources_do_not_change(self):
        b, (w, snap, rs, ledger, cd) = H.example_m()
        h = b.history()
        self.assertEqual(h.events[-1]["kind"], "SCHEMA_MIGRATION")
        plan = X.prepare_restart_plan(h, D[5], w.sessions, ledger, D[5], "r1", R.WHEN)
        res = X.confirm_restart_plan(plan, plan.plan_hash, h, w.sessions, ledger)
        rec = res.history.events[-1]
        self.assertEqual((rec["parent_seq"], rec["parent_hash"]), (h.head_seq, h.head_hash))
        before, after = V.migrated_sources(h), V.migrated_sources(res.history)
        self.assertEqual(R.cj(before[0].events), R.cj(after[0].events))
        self.assertEqual(R.cj(before[1].to_dict()), R.cj(after[1].to_dict()))
        # the migration record itself is untouched
        self.assertEqual(R.cj(res.history.events[:-1]), R.cj(h.events))


class RequestIds(unittest.TestCase):
    def test_a_new_id_is_ready_and_every_used_id_is_a_conflict(self):
        b = H.example_r()
        h = b.history()
        view = O.read_effective(h)
        used = {g["request_id"] for g in view.requests}
        self.assertEqual(used, {"q1", "q2", "q3", "q4", "q5", "q6"})
        for rid in sorted(used):
            self.assertEqual(R.refusal(R.prep, h, b.w, D[7], D[8], rid), CONFLICT, rid)
        self.assertEqual(R.prep(h, b.w, D[7], D[8], "q7").status, "READY")

    def test_native_replayed_and_superseded_only_ids(self):
        # example R up to the first restore: q2 was replayed, its original is superseded
        b = H.example_r1()
        h = b.history()
        groups = {(g["request_id"], g["source"], g["effective"]) for g in O.read_effective(h).requests}
        self.assertIn(("q2", "REPLAYED", True), groups)
        self.assertIn(("q2", "NATIVE", False), groups)                  # the superseded original
        for rid in ("q1", "q2", "q4"):
            self.assertEqual(R.refusal(R.prep, h, b.w, D[5], D[6], rid), CONFLICT, rid)
        dropped = H.HB()
        dropped.apply(D[1], 27.0)
        dropped.restart(D[3], "only-superseded")
        dropped.restore(1, {2: "DROP"}, "q2")
        hd = dropped.history()
        self.assertNotIn(2, V.validate_history(hd).effective_seqs)
        self.assertEqual(R.refusal(R.prep, hd, dropped.w, D[2], D[3], "only-superseded"), CONFLICT)

    def test_migrated_ids_and_other_kinds(self):
        b, (w, snap, rs, ledger, cd) = H.example_m()
        h = b.history()
        used = {g["request_id"]: g["source"] for g in O.read_effective(h).requests}
        self.assertIn("MIGRATED", used.values())
        for rid in list(used) + ["mig-1"]:
            out = T.outcome(X.prepare_restart_plan, h, D[5], w.sessions, ledger, D[5], rid, R.WHEN)
            self.assertEqual(out[:4], ("err", "history_request_conflict", "request_id", None), rid)

    def test_same_id_same_content_or_only_the_time_changed_is_a_conflict_in_prepare(self):
        b = R.example_u()
        h, w = b.history(), b.w
        plan, res = R.run(h, w, D[3], D[3], "r1")
        cand = res.history
        self.assertEqual(R.refusal(R.prep, cand, w, D[3], D[3], "r1"), CONFLICT)
        later = R.WHEN.replace(hour=5)
        self.assertEqual(R.refusal(R.prep, cand, w, D[3], D[3], "r1", None, None, later), CONFLICT)
        # contrast: re-confirming the same plan against its own candidate is NO_CHANGE
        self.assertEqual(R.confirm(plan, cand, w).status, "NO_CHANGE")

    def test_an_old_boundary_time_difference_and_a_used_id(self):
        v = T.example_v()
        h, w = v.history(), v.w
        changed = R.sessions_with({D[3]: R.earlier_close})
        self.assertEqual(R.refusal(R.prep, h, w, D[4], D[5], "q1", changed), CONFLICT)
        self.assertEqual(R.refusal(R.prep, h, w, D[4], D[5], "r9", changed)[:2], ("session_context_mismatch", "sessions"))
        self.assertEqual(R.prep(h, w, D[4], D[5], "r9").status, "READY")

    def test_example_r_used_ids_are_not_changed_for_convenience(self):
        b = H.example_r()
        self.assertEqual([e["request_id"] for e in b.events if e["kind"] == "RECOVERY_RESTORE"], ["q4", "q5", "q6"])


class PlanBinding(unittest.TestCase):
    def setUp(self):
        self.b = R.example_u()
        self.h, self.w = self.b.history(), self.b.w
        self.plan = R.prep(self.h, self.w, D[3], D[4], "r1")

    def test_each_basis_item_is_bound_even_when_the_hash_is_recomputed(self):
        hexs = "f" * 64
        basis = self.plan.basis
        table = {
            "operation": ("x", "history_plan_mismatch"), "status": ("NO_CHANGE", "history_plan_mismatch"),
            "history_digest": (hexs, "history_plan_stale"), "expected_head_seq": (3, "history_plan_mismatch"),
            "expected_head_hash": (hexs, "history_plan_stale"), "expected_state_digest": (hexs, "history_plan_mismatch"),
            "resume_after": (D[4], "history_plan_mismatch"), "check_d": (D[5], "history_plan_mismatch"),
            "request_id": ("r2", "history_plan_mismatch"), "request_hash": (hexs, "history_plan_mismatch"),
            "reason_code": ("X", "history_plan_mismatch"), "requested_at": ("2026-06-02T00:00:00Z", "history_plan_mismatch"),
            "floor": ({"last_apply_d": D[1], "last_declared_d": None, "prev_boundary": D[0]}, "history_plan_mismatch"),
            "boundary_session": (dict(basis["boundary_session"], confirmed=False), "history_plan_mismatch"),
            "ledger_digest": (hexs, "history_plan_stale"), "sessions_digest": (hexs, "history_plan_stale"),
            "effective_digest": (hexs, "history_plan_mismatch"),
            "candidate_history": (dict(basis["candidate_history"], head_seq=7), "history_plan_mismatch"),
            "candidate_digest": (hexs, "history_plan_mismatch"), "candidate_state_digest": (hexs, "history_plan_mismatch")}
        self.assertEqual(sorted(table), sorted(BASIS20))
        for key, (value, code) in table.items():
            def edit(bs, key=key, value=value):
                bs[key] = value
            out = T.outcome(R.confirm, R.refreshed(self.plan, edit), self.h, self.w)
            self.assertEqual(out[:3], ("err", code, "plan"), key)

    def test_the_candidate_record_itself_cannot_be_changed_with_a_fixed_up_hash(self):
        def edit(bs):
            bs["candidate_history"]["events"][-1]["floor"]["last_apply_d"] = D[1]
        out = T.outcome(R.confirm, R.refreshed(self.plan, edit), self.h, self.w)
        self.assertEqual(out[:3], ("err", "history_plan_mismatch", "plan"))

    def test_a_changed_basis_with_the_old_hash_and_a_wrong_confirmed_hash(self):
        def edit(d):
            d["basis"]["check_d"] = D[5]
        bad = R.with_plan_dict(self.plan, edit)
        self.assertEqual(T.outcome(R.confirm, bad, self.h, self.w)[:3], ("err", "history_plan_mismatch", "plan"))
        self.assertEqual(T.outcome(R.confirm, self.plan, self.h, self.w, None, None, "0" * 64)[:3],
                         ("err", "history_plan_mismatch", "plan"))
        self.assertEqual(T.outcome(R.confirm, self.plan, self.h, self.w, None, None, "xyz")[:3],
                         ("err", "history_plan_mismatch", "plan"))

    def test_same_input_same_time_same_hash_and_only_the_time_changes_the_hashes(self):
        again = R.prep(self.h, self.w, D[3], D[4], "r1")
        self.assertEqual(again.plan_hash, self.plan.plan_hash)
        self.assertEqual(again, self.plan)
        later = R.prep(self.h, self.w, D[3], D[4], "r1", None, None, R.WHEN.replace(hour=7))
        self.assertNotEqual(later.plan_hash, self.plan.plan_hash)
        a, b = self.plan.basis, later.basis
        self.assertEqual(a["request_hash"], b["request_hash"])
        self.assertNotEqual(a["candidate_digest"], b["candidate_digest"])
        self.assertNotEqual(a["candidate_history"]["events"][-1]["event_hash"],
                            b["candidate_history"]["events"][-1]["event_hash"])


if __name__ == "__main__":
    unittest.main()
