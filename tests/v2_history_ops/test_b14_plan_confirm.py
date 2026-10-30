"""B2-14: the plan, its hash and the confirmation (design 6.6, 6.7 and 12.7)."""
import copy
import unittest
from unittest import mock

import ho_helpers as T
import v2_history_ops as O
import v2_history_ops.plan as OP
from v2_persistence.codec import canonical_json, sha256_text

H, D, P, RH, V = T.H, T.D, T.P, T.RH, T.V
MISMATCH = ("history_plan_mismatch", "plan")
STALE = ("history_plan_stale", "plan")


def rehash(basis):
    """A plan whose plan_hash fits the (altered) basis: only the contents are wrong."""
    return O.HistoryResolutionPlan.from_dict({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))})


def code_field(e):
    return (e.code, e.field)


class Base(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.h, self.w = b.history(), b.w
        self.x = P.obs("x", D[1], 22.0)
        self.led = list(self.w.ledger) + [self.x]
        self.cmds = [T.ack_cmd(self.h, "ADDED", D[1], [T.fp(self.x)], 1)]
        self.plan = T.plan_for(self.h, self.cmds, self.w.sessions, self.led, D[2], "q1")

    def longer(self, h=None):
        """The history one valid APPLY (D2) further, made from a ledger without the extra row."""
        h = self.h if h is None else h
        return T.extend(h, T.day(h, D[2], self.w, list(self.w.ledger) + [P.obs("R2", D[2], 31.0)]))

    def confirm(self, plan=None, confirmed=None, h=None, sessions=None, ledger=None):
        plan = self.plan if plan is None else plan
        return O.confirm_history_resolution_plan(plan, plan.plan_hash if confirmed is None else confirmed,
                                                 self.h if h is None else h,
                                                 self.w.sessions if sessions is None else sessions,
                                                 self.led if ledger is None else ledger)


class PlanBinding(Base):
    def test_plan_hash_is_the_sha256_of_the_whole_basis_and_records_do_not_carry_it(self):
        basis = self.plan.basis
        self.assertEqual(set(basis), set(OP._BASIS_KEYS))
        self.assertEqual(len(basis), 19)
        self.assertEqual(self.plan.plan_hash, sha256_text(canonical_json(basis)))
        for rec in basis["candidate_history"]["events"]:
            self.assertNotIn("plan_hash", rec)
        self.assertNotIn(self.plan.plan_hash, canonical_json(basis["candidate_history"]))

    def test_every_basis_key_is_bound_by_the_confirmation(self):
        stale_keys = {"history_digest", "expected_head_seq", "expected_head_hash", "ledger_digest", "sessions_digest"}
        changes = {"operation": "other", "status": "NO_CHANGE", "request_id": "q9", "requested_at": "2026-06-02T00:00:00Z",
                   "check_d": D[3], "reason_code": "RESOLUTION_BATCH", "expected_head_seq": 2, "commands": None,
                   "candidate_history": None, "excluded_fingerprints": ["f" * 64], "supplemented": [{"seq": 1}]}
        for key in sorted(self.plan.basis):
            with self.subTest(key):
                basis = self.plan.basis
                if key in changes and changes[key] is not None:
                    basis[key] = changes[key]
                elif key == "commands":
                    basis[key][0]["d"] = D[2]
                elif key == "candidate_history":
                    basis[key]["events"][-1]["reason_code"] = "OTHER"
                else:
                    basis[key] = "0" * 64
                self.assertTrue(basis != self.plan.basis)
                e = T.refusal(O.confirm_history_resolution_plan, rehash(basis), sha256_text(canonical_json(basis)),
                              self.h, self.w.sessions, self.led)
                self.assertEqual(code_field(e), STALE if key in stale_keys else MISMATCH)

    def test_form_and_hash_errors_are_mismatch_before_any_input_is_looked_at(self):
        wrong = "1" * 64
        cases = [("wrong confirmed hash", self.plan, wrong), ("not a hash", self.plan, "xyz"),
                 ("uppercase hash", self.plan, self.plan.plan_hash.upper()), ("int", self.plan, 1),
                 ("none", self.plan, None), ("not a plan", {"basis": self.plan.basis, "plan_hash": self.plan.plan_hash},
                                             self.plan.plan_hash)]
        for name, plan, conf in cases:
            with self.subTest(name):
                # even with a broken history, the plan's own form is judged first
                bad = self.h.to_dict()
                bad["events"][1]["event_hash"] = "0" * 64
                e = T.refusal(O.confirm_history_resolution_plan, plan, conf, V.History.from_dict(bad), self.w.sessions,
                              self.led)
                self.assertEqual(code_field(e), MISMATCH)
        # a changed basis whose hash was not renewed
        basis = self.plan.basis
        basis["check_d"] = D[3]
        tampered = O.HistoryResolutionPlan.from_dict({"basis": basis, "plan_hash": self.plan.plan_hash})
        self.assertEqual(code_field(T.refusal(self.confirm, tampered)), MISMATCH)
        # a missing key or an extra key
        for mut in (lambda b: b.pop("check_d"), lambda b: b.__setitem__("extra", 1)):
            basis = self.plan.basis
            mut(basis)
            self.assertEqual(code_field(T.refusal(O.confirm_history_resolution_plan, rehash(basis),
                                                  sha256_text(canonical_json(basis)), self.h, self.w.sessions, self.led)),
                             MISMATCH)

    def test_confirm_returns_the_candidate_and_changes_nothing(self):
        before = (self.h.digest, self.plan.plan_hash, canonical_json(self.plan.basis), list(self.led))
        res = self.confirm()
        self.assertEqual((res.status, res.committed, res.state_unchanged, res.plan_hash),
                         ("CONFIRMED_IN_MEMORY", False, True, self.plan.plan_hash))
        self.assertEqual(res.history.digest, self.plan.basis["candidate_digest"])
        self.assertEqual(res.history.current_state, self.h.current_state)
        self.assertEqual(res.batch.body["records"], self.plan.basis["candidate_history"]["events"][2:])
        self.assertEqual(before, (self.h.digest, self.plan.plan_hash, canonical_json(self.plan.basis), list(self.led)))


class StaleAndInvalidInputs(Base):
    """A valid but different input is stale; an invalid input keeps its own existing error (separate examples)."""

    def test_valid_changes_are_stale(self):
        self.assertEqual(code_field(T.refusal(self.confirm, h=self.longer())), STALE)
        extra = list(self.led) + [P.obs("unrelated", D[9], 30.0)]
        self.assertEqual(code_field(T.refusal(self.confirm, ledger=extra)), STALE)
        wider = P.make_sessions(dates=P.DATES[:-1])
        plan = T.plan_for(self.h, self.cmds, wider, self.led, D[2], "q1")
        self.assertEqual(code_field(T.refusal(O.confirm_history_resolution_plan, plan, plan.plan_hash, self.h,
                                              self.w.sessions, self.led)), STALE)

    def test_invalid_inputs_keep_their_own_errors(self):
        bad = self.h.to_dict()
        bad["events"][1]["event_hash"] = "0" * 64
        e = T.refusal(self.confirm, h=V.History.from_dict(bad))
        self.assertEqual((e.code, e.rule), ("history_invalid", "event_hash"))
        e = T.refusal(self.confirm, ledger=self.led + [{"record_id": "zz"}])
        self.assertEqual(e.code, "status_unknown")
        e = T.refusal(self.confirm, sessions=[1, 2])
        self.assertEqual(e.code, "sessions_invalid")

    def test_an_invalid_input_wins_over_a_stale_one(self):
        e = T.refusal(self.confirm, h=self.longer(), ledger=self.led + [{"record_id": "zz"}])
        self.assertEqual(e.code, "status_unknown")                  # not history_plan_stale


class BranchesAB(Base):
    def test_branch_a_original_history_needs_the_original_digest_and_head(self):
        res = self.confirm()
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        basis = self.plan.basis
        for key, value in (("history_digest", "0" * 64), ("expected_head_seq", 5), ("expected_head_hash", "0" * 64)):
            b = copy.deepcopy(basis)
            b[key] = value
            e = T.refusal(O.confirm_history_resolution_plan, rehash(b), sha256_text(canonical_json(b)), self.h,
                          self.w.sessions, self.led)
            self.assertEqual(code_field(e), STALE, key)

    def test_branch_b_the_plans_own_candidate_is_no_change(self):
        res = self.confirm()
        cand = res.history
        again = O.confirm_history_resolution_plan(self.plan, self.plan.plan_hash, cand, self.w.sessions, self.led)
        self.assertEqual((again.status, again.batch, again.committed), ("NO_CHANGE", None, False))
        self.assertEqual(again.history.digest, cand.digest)
        self.assertEqual(again.plan_hash, self.plan.plan_hash)
        # the original head is not required: the candidate's head is another record
        self.assertNotEqual(cand.head_seq, self.plan.basis["expected_head_seq"])

    def test_branch_b_expected_basis_differs_in_exactly_four_items(self):
        cand = self.confirm().history
        fresh = T.plan_for(cand, self.cmds, self.w.sessions, self.led, D[2], "q1")        # the same request, now
        old, new = self.plan.basis, fresh.basis
        self.assertEqual(sorted(k for k in old if old[k] != new[k]),
                         ["expected_head_hash", "expected_head_seq", "history_digest", "status"])
        self.assertEqual(new["status"], "NO_CHANGE")
        self.assertEqual((new["history_digest"], new["expected_head_seq"], new["expected_head_hash"]),
                         (cand.digest, cand.head_seq, cand.head_hash))
        # and what the old plan's four items would have to be for a branch B match
        self.assertEqual(old["candidate_digest"], new["history_digest"])

    def test_one_more_record_after_the_candidate_is_stale(self):
        cand = self.confirm().history
        longer = self.longer(cand)
        self.assertEqual(code_field(T.refusal(O.confirm_history_resolution_plan, self.plan, self.plan.plan_hash,
                                              longer, self.w.sessions, self.led)), STALE)

    def test_a_no_change_plan_has_no_branch_b(self):
        cand = self.confirm().history
        nochange = T.plan_for(cand, self.cmds, self.w.sessions, self.led, D[2], "q1")
        self.assertEqual(nochange.status, "NO_CHANGE")
        res = O.confirm_history_resolution_plan(nochange, nochange.plan_hash, cand, self.w.sessions, self.led)
        self.assertEqual((res.status, res.batch), ("NO_CHANGE", None))
        longer = self.longer(cand)
        self.assertEqual(code_field(T.refusal(O.confirm_history_resolution_plan, nochange, nochange.plan_hash,
                                              longer, self.w.sessions, self.led)), STALE)


class WholeCandidate(unittest.TestCase):
    def test_an_existing_conflict_can_be_resolved_by_the_plan(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        h, w = b.history(), b.w
        b1 = P.obs("b", D[1], 27.0)
        e = T.refusal(O.project_history_ledger, h, w.sessions, [b1], D[2])
        self.assertEqual(e.code, "ledger_mismatch")                                  # the history alone is not clean
        cmds = [T.cmd("ACK", "ROW_REMOVED", D[1], [], applied=T.aref(h, 1)), T.ack_cmd(h, "ADDED", D[1], [T.fp(b1)], 1)]
        _plan, res = T.run_plan(h, cmds, w.sessions, [b1], D[2], "q1")
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")

    def test_12_7_6_the_candidate_projection_catches_what_the_evidence_does_not(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[4], 29.0)                                           # D2 and D3 are skipped
        h, w = b.history(), b.w
        e1, l3 = P.obs("e", D[1], 40.0, hour=21), P.obs("l3", D[3], 22.0)
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(e1)], 1)]
        led = list(w.ledger) + [e1, l3]
        self.assertEqual(T.refusal(O.project_history_ledger, h, w.sessions, led, D[5]).code, "decision_conflict")
        with mock.patch.object(OP, "check_commands", wraps=OP.check_commands) as spy:
            e = T.refusal(T.plan_for, h, cmds, w.sessions, led, D[5], "q1")
        self.assertEqual((e.code, e.field), ("late_observation", "observations"))
        self.assertEqual(spy.call_count, 1)                           # the evidence itself was accepted
        # without the late row the same request is READY
        self.assertEqual(T.plan_for(h, cmds, w.sessions, list(w.ledger) + [e1], D[5], "q1").status, "READY")

    def test_candidate_is_checked_by_validate_history_and_the_projection(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        h, w = b.history(), b.w
        x = P.obs("x", D[1], 22.0)
        cmds = [T.ack_cmd(h, "ADDED", D[1], [T.fp(x)], 1)]
        with mock.patch.object(OP, "validate_history", wraps=OP.validate_history) as vh, \
                mock.patch.object(OP, "ledger_of", wraps=OP.ledger_of) as lo:
            T.plan_for(h, cmds, w.sessions, list(w.ledger) + [x], D[2], "q1")
        self.assertEqual(vh.call_count, 2)                            # the given history, then the candidate
        self.assertEqual(lo.call_count, 1)
        self.assertEqual(lo.call_args[0][0].head_seq, 2)              # over the candidate, not the history


if __name__ == "__main__":
    unittest.main()
