"""C-10: a plan binds every input; confirming re-checks and rebuilds; a request id means one request."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

import r_helpers as H
from r_helpers import D, R


UNSET = object()


def row(record_id, d, value, hour=20):
    return H.P.obs(record_id, d, value, hour=hour)


class Base(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]
        self.b = row("B1", D[1], 40.0, hour=21)
        self.ledger = [self.a, self.b]
        self.cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])]

    def plan(self, **kw):
        args = dict(cmds=self.cmds, ledger=self.ledger, check_d=D[1], rid="req-1", when=H.WHEN, rs=self.rs)
        args.update(kw)
        return H.plan_for(self.w, args["rs"], args["cmds"], args["ledger"], args["check_d"], rid=args["rid"],
                          when=args["when"])

    def confirm(self, plan, rs=None, ledger=None, snap=None, sessions=None, hash_=UNSET):
        return R.confirm_resolution_plan(plan, plan.plan_hash if hash_ is UNSET else hash_,
                                         snap or self.w.snap(), rs or self.rs, sessions or self.w.sessions,
                                         ledger if ledger is not None else self.ledger)


class PlanForm(Base):
    def test_ready_plan_is_deterministic_and_not_applied(self):
        p1, p2 = self.plan(), self.plan()
        self.assertEqual((p1.status, p1.committed), ("READY", False))
        self.assertEqual(p1.plan_hash, p2.plan_hash)
        self.assertEqual(p1, p2)
        self.assertEqual(self.rs.head_resolution_seq, 0)             # preparing changes nothing
        basis = p1.basis
        for key in ("snapshot_digest", "expected_head_seq", "expected_head_hash", "resolutions_before_digest",
                    "request_id", "request_hash", "requested_at", "check_d", "ledger_digest", "sessions_digest",
                    "commands", "candidate_resolutions", "candidate_digest", "expected_state_digest"):
            self.assertIn(key, basis)
        for rec in basis["candidate_resolutions"]["records"]:
            self.assertNotIn("plan_hash", rec)                       # no circular hash definition

    def test_summary_is_a_whitelist(self):
        p = self.plan()
        s = p.summary()
        self.assertEqual(s["commands"], [{"kind": "ACK", "variant": "ADDED", "d": D[1], "fingerprints": 1}])
        text = repr(p) + repr(s)
        self.assertNotIn(H.fp(self.b), text)
        self.assertNotIn("40.0", text)

    def test_confirm_returns_a_new_set_and_projection_in_memory_only(self):
        res = self.confirm(self.plan())
        self.assertEqual((res.status, res.committed, res.state_unchanged), ("CONFIRMED_IN_MEMORY", False, True))
        self.assertEqual(res.resolutions.head_resolution_seq, 1)
        self.assertEqual(self.w.snap().head_seq, 1)

    def test_input_validation_of_the_request(self):
        H.expect_rule(self, "request_id", self.plan, rid="has space")
        H.expect_rule(self, "request_id", self.plan, rid="x" * 65)
        H.expect_rule(self, "command_shape", self.plan, cmds=[])
        H.expect_rule(self, "reason_code", H.plan_for, self.w, self.rs, self.cmds, self.ledger, D[1], "r",
                      "MARK_SESSION_MISSING")
        naive = datetime(2026, 6, 1)
        H.expect_code(self, "datetime_missing_timezone", self.plan, when=naive)
        H.expect_code(self, "datetime_invalid", self.plan, when="2026-06-01T00:00:00Z")
        bad = dict(self.cmds[0], kind="NOTE")
        H.expect_rule(self, "command_shape", self.plan, cmds=[bad])
        extra_key = dict(self.cmds[0], note="free text")
        H.expect_rule(self, "command_shape", self.plan, cmds=[extra_key])
        missing_key = {k: v for k, v in self.cmds[0].items() if k != "missing_ref"}
        H.expect_rule(self, "command_shape", self.plan, cmds=[missing_key])
        H.expect_rule(self, "command_shape", R.prepare_resolution_plan, self.w.snap(), self.rs, ["x"], self.w.sessions,
                      self.ledger, D[1], "req-1", H.ACK_REASON, H.WHEN)
        dup = dict(self.cmds[0], record_fingerprints=[H.fp(self.b), H.fp(self.b)])
        H.expect_rule(self, "command_shape", self.plan, cmds=[dup])

    def test_the_time_zone_of_requested_at_does_not_matter(self):
        jst = datetime(2026, 6, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(self.plan(when=jst).plan_hash, self.plan().plan_hash)


class TamperingAndStaleness(Base):
    def test_wrong_confirmation_hash_or_object(self):
        p = self.plan()
        other = self.plan(rid="req-2")
        for bad in (other.plan_hash, "z" * 64, "", None, 7):
            with self.subTest(bad=bad):
                H.expect_code(self, "resolution_plan_mismatch", self.confirm, p, hash_=bad)
        H.expect_code(self, "resolution_plan_mismatch", R.confirm_resolution_plan, "plan", p.plan_hash, self.w.snap(),
                      self.rs, self.w.sessions, self.ledger)

    def test_edited_plan_is_refused_by_its_hash(self):
        d = self.plan().to_dict()
        d["basis"]["check_d"] = D[2]
        forged = R.ResolutionPlan.from_dict(d)
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged, hash_=forged.plan_hash)
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged, hash_=self.plan().plan_hash)

    def test_forged_plan_with_a_recomputed_hash_is_refused_by_the_rebuild(self):
        d = self.plan().to_dict()
        cand = d["basis"]["candidate_resolutions"]
        cand["records"][0]["record_fingerprints"] = []                 # a candidate that excludes nothing
        import hashlib
        d["plan_hash"] = hashlib.sha256(H.cj(d["basis"]).encode("utf-8")).hexdigest()
        forged = R.ResolutionPlan.from_dict(d)
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, forged)

    def test_forged_plan_whose_commands_cannot_be_rebuilt_is_a_mismatch(self):
        import hashlib
        d = self.plan().to_dict()
        d["basis"]["commands"][0]["record_fingerprints"] = ["0" * 64]      # unknown row: the rebuild itself fails
        d["plan_hash"] = hashlib.sha256(H.cj(d["basis"]).encode("utf-8")).hexdigest()
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, R.ResolutionPlan.from_dict(d))

    def test_malformed_plan_dict(self):
        H.expect_rule(self, "plan_shape", R.ResolutionPlan.from_dict, {"basis": {}})
        d = self.plan().to_dict()
        del d["basis"]["commands"]
        broken = R.ResolutionPlan.from_dict(dict(d, plan_hash="a" * 64))
        H.expect_code(self, "resolution_plan_mismatch", self.confirm, broken)

    def test_every_input_change_after_the_plan_is_stale(self):
        p = self.plan()
        H.expect_code(self, "resolution_plan_stale", self.confirm, p, ledger=self.ledger + [row("U1", D[7], 27.0)])
        H.expect_code(self, "resolution_plan_stale", self.confirm, p, ledger=[self.a, self.b, self.b])
        moved = H.P.make_sessions(overrides={D[5]: lambda s: s.__class__(s.date, s.open_at, s.close_at, False)})
        H.expect_code(self, "resolution_plan_stale", self.confirm, p, sessions=moved)
        # sessions: only the confirmed flag of the session after check_d changed -> the whole-list digest still notices
        flipped = H.P.make_sessions(overrides={D[2]: lambda s: s.__class__(s.date, s.open_at, s.close_at, False)})
        H.expect_code(self, "resolution_plan_stale", self.confirm, p, sessions=flipped)

    def test_a_grown_snapshot_stops_the_old_plan(self):
        p = self.plan()
        w2 = H.world(1)
        grown = H.extend_with_s1(w2, D[2], list(w2.ledger) + [row("R2", D[2], 27.0)])
        # the latest APPLY is now after the plan's check_d: the existing core error stops it before any digest compare
        H.expect_code(self, "state_ahead_of_target", self.confirm, p, snap=grown)

    def test_the_snapshot_digest_is_part_of_the_basis(self):
        d = self.plan().to_dict()
        import hashlib
        d["basis"]["snapshot_digest"] = "0" * 64
        d["plan_hash"] = hashlib.sha256(H.cj(d["basis"]).encode("utf-8")).hexdigest()
        forged = R.ResolutionPlan.from_dict(d)
        H.expect_code(self, "resolution_plan_stale", self.confirm, forged)

    def test_two_plans_from_the_same_set(self):
        e = row("E1", D[1], 41.0, hour=21)
        ledger = [self.a, self.b, e]
        p1 = H.plan_for(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], sorted([H.fp(self.b), H.fp(e)]))], ledger, D[1], rid="req-1")
        p2 = H.plan_for(self.w, self.rs, [H.ack(self.snap, "ADDED", D[1], sorted([H.fp(self.b)]))] + [H.ack(self.snap, "ADDED", D[1], [H.fp(e)])], ledger, D[1], rid="req-2")
        done = R.confirm_resolution_plan(p1, p1.plan_hash, self.w.snap(), self.rs, self.w.sessions, ledger)
        H.expect_code(self, "resolution_plan_stale", R.confirm_resolution_plan, p2, p2.plan_hash, self.w.snap(),
                      done.resolutions, self.w.sessions, ledger)

    def test_nothing_is_changed_when_one_command_of_a_batch_fails(self):
        before = (copy.deepcopy(self.ledger), self.snap.to_dict(), self.rs.to_dict(), copy.deepcopy(self.cmds))
        bad = self.cmds + [H.ack(self.snap, "ADDED", D[1], ["0" * 64])]
        H.expect_rule(self, "ack_evidence", H.plan_for, self.w, self.rs, bad, self.ledger, D[1])
        after = (self.ledger, self.w.snap().to_dict(), self.rs.to_dict(), self.cmds)
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1:], after[1:])


class RequestIdentity(Base):
    def setUp(self):
        super().setUp()
        self.done = self.confirm(self.plan())

    def test_same_request_again_is_no_change(self):
        p = H.plan_for(self.w, self.done.resolutions, self.cmds, self.ledger, D[1], rid="req-1")
        self.assertEqual(p.status, "NO_CHANGE")
        res = self.confirm(p, rs=self.done.resolutions)
        self.assertEqual((res.status, res.committed), ("NO_CHANGE", False))
        self.assertEqual(res.resolutions, self.done.resolutions)

    def test_only_a_newer_time_keeps_the_original_record_and_time(self):
        later = H.WHEN + timedelta(days=3)
        p = H.plan_for(self.w, self.done.resolutions, self.cmds, self.ledger, D[1], rid="req-1", when=later)
        self.assertEqual(p.status, "NO_CHANGE")
        res = self.confirm(p, rs=self.done.resolutions)
        self.assertEqual(res.resolutions.records[0]["requested_at"], "2026-06-01T00:00:00Z")
        self.assertEqual(res.resolutions.digest, self.done.resolutions.digest)
        self.assertEqual(res.resolutions.records[0]["ledger_digest"], self.done.resolutions.records[0]["ledger_digest"])

    def test_same_id_with_different_content_is_a_conflict(self):
        e = row("E1", D[1], 41.0, hour=21)
        other_cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b), H.fp(e)])]
        variants = {
            "commands": dict(cmds=other_cmds, ledger=self.ledger + [e]),
            "check_d": dict(check_d=D[2]),
            "reason": dict(reason=H.BATCH_REASON),
        }
        for name, kw in variants.items():
            with self.subTest(name):
                cmds = kw.get("cmds", self.cmds)
                ledger = kw.get("ledger", self.ledger)
                check_d = kw.get("check_d", D[1])
                H.expect_code(self, "resolution_request_conflict", H.plan_for, self.w, self.done.resolutions, cmds,
                              ledger, check_d, "req-1", kw.get("reason"))

    def test_no_change_still_checks_the_current_projection(self):
        broken = self.ledger + [row("Z1", D[1], 43.0, hour=22)]        # a new second decision for D1
        H.expect_code(self, "decision_conflict", H.plan_for, self.w, self.done.resolutions, self.cmds, broken, D[1])

    def test_confirming_the_same_plan_again_against_its_own_candidate(self):
        p = self.plan()
        res = self.confirm(p, rs=self.done.resolutions)
        self.assertEqual(res.status, "NO_CHANGE")
        self.assertEqual(res.resolutions, self.done.resolutions)
        # a set that moved on is never merged
        extra = H.run(self.w, self.done.resolutions, [H.declare(D[2])], self.ledger, D[2], rid="req-2")
        H.expect_code(self, "resolution_plan_stale", self.confirm, p, rs=extra.resolutions)


class CheckDBoundaries(Base):
    def test_the_latest_apply_day_can_be_run_again_and_earlier_or_unknown_days_cannot(self):
        w = H.world(2)
        rs = R.empty_resolutions()
        led = list(w.ledger)
        self.assertEqual(R.resolve_observations(w.snap(), rs, w.sessions, led, D[2]).rows, [H.cols(led[0]), H.cols(led[1])])
        H.expect_code(self, "state_ahead_of_target", R.resolve_observations, w.snap(), rs, w.sessions, led, D[1])
        H.expect_code(self, "target_not_after_genesis", R.resolve_observations, w.snap(), rs, w.sessions, led, D[0])
        H.expect_code(self, "target_not_in_sessions", R.resolve_observations, w.snap(), rs, w.sessions, led, "2030-01-01")
        H.expect_code(self, "next_session_missing", R.resolve_observations, w.snap(), rs, w.sessions, led, D[-1])
        H.expect_code(self, "invalid_date", R.resolve_observations, w.snap(), rs, w.sessions, led, "x")
        w2 = H.P.World(unconfirmed=(D[3],))
        H.expect_code(self, "target_unconfirmed", R.resolve_observations, w2.snap(), rs, w2.sessions, [], D[3])

    def test_an_existing_record_after_check_d_is_not_rejected_for_that_reason_alone(self):
        decl = H.run(self.w, self.rs, [H.declare(D[2])], [self.a], D[2], rid="d2")
        e_cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])]
        p = H.plan_for(self.w, decl.resolutions, e_cmds, [self.a, self.b], D[1], rid="req-1")
        self.assertEqual(p.status, "READY")
        res = R.prepare_resolved_day(self.snap, decl.resolutions, D[1], self.w.series, self.w.sessions, [self.a])
        self.assertEqual(res.status, "ALREADY_APPLIED")

    def test_new_ack_and_new_declaration_are_bounded_by_check_d(self):
        H.expect_rule(self, "declare_frontier", H.plan_for, self.w, self.rs, [H.declare(D[2])], [self.a], D[1])


if __name__ == "__main__":
    unittest.main()
