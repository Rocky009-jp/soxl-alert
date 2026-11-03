"""A5-06 the floor of a restore at the last adoption record (B-1 and B-4) and A5-07 the later stages on an adopted
history (B-2 day, ACK and DECLARE, B-3 restart, the request ids, the effective view).

The adopted history is the candidate of the design: GENESIS + APPLY D1..D5 (the verified prefix, k = 6) and the
adoption record at seq 6, written by the independent builder."""
import unittest

import a5_helpers as Z
from a5_helpers import D, H, P, R3, R4, T, V
import v2_history_ops as O

BEFORE = (0, 3, 5)
FLOOR = "restore_before_adoption"


def adopted_world():
    b0, data, k = Z.new_world()
    events = Z.adopted_events(data, k)
    return H.HB(world=b0.w, events=events), data, k


def with_restart_and_apply():
    """... 6 adoption, 7 RESTART_UNKNOWN (D5), 8 APPLY D6: a restore at 6 can drop the restart and apply D6 again."""
    b, data, k = adopted_world()
    b.restart(D[5], "qs")
    b.apply(D[6])
    return b, data, k


def drop_all_after(events, point):
    chain = H.chain_of(events)
    return [{"op": "DROP", "from_seq": s} for s in chain[chain.index(point) + 1:]]


class FloorOfRestoreB1(unittest.TestCase):
    def test_a_restore_before_the_adoption_is_refused(self):
        b, _data, _k = with_restart_and_apply()
        for point in BEFORE:
            with self.subTest(point):
                events = H.hand_restore(b.events, point, drop_all_after(b.events, point))
                got = H.expect_error(self, "history_invalid", FLOOR, V.validate_history, H.history_of(events))
                self.assertEqual(got.rule, FLOOR)

    def test_a_restore_to_the_adoption_record_itself_is_accepted(self):
        b, _data, k = with_restart_and_apply()
        b.restore(k, {7: "DROP", 8: "REAPPLY"}, "qr1")
        chk = b.check()
        self.assertEqual(chk.effective_seqs[: k + 1], tuple(range(k + 1)))
        restores = [e for e in b.events if e["kind"] == "RECOVERY_RESTORE"]
        self.assertEqual([(e["parent_seq"], e["superseded_seqs"]) for e in restores], [(k, [7, 8])])

    def test_the_floor_is_the_last_adoption_on_the_chain(self):
        b, data, k = with_restart_and_apply()
        second = Z.record_of(b.events, dict(Z.evidence_of(data, k), discarded_from_seq=len(b.events)), "ad2")
        events = b.events + [second]
        self.assertEqual(second["seq"], 9)
        V.validate_history(H.history_of(events))
        # the first adoption and the APPLY before the second one are now below the floor
        for point in (k, 8):
            with self.subTest(point):
                got = H.hand_restore(events, point, drop_all_after(events, point))
                H.expect_error(self, "history_invalid", FLOOR, V.validate_history, H.history_of(got))

    def test_the_floor_is_not_a_rule_when_there_is_no_adoption(self):
        b = H.example_r1()
        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", [e["kind"] for e in b.events])
        V.validate_history(b.history())


class FloorOfRestoreB4(unittest.TestCase):
    def setUp(self):
        self.b, self.data, self.k = with_restart_and_apply()

    def test_the_same_points_are_refused_in_the_plan_with_the_planning_reason(self):
        for point in BEFORE:
            with self.subTest(point):
                self.assertEqual(R4.rule_of(R4.prep, self.b, point, {"*": "REAPPLY"}, D[6], "rr3"),
                                 ("restore_invalid", "restore_point", FLOOR))

    def test_the_adoption_record_as_the_restore_point_is_ready_and_confirmed(self):
        plan, res = R4.run(self.b, self.k, {7: "DROP", 8: "REAPPLY"}, D[6], "rr2")
        self.assertEqual((plan.status, res.status), ("READY", "CONFIRMED_IN_MEMORY"))
        chk = V.validate_history(res.history)
        self.assertEqual(res.history.events[self.k]["kind"], "RECOVERY_PREFIX_ADOPTION")
        self.assertEqual([e["kind"] for e in res.history.events[-2:]], ["RECOVERY_RESTORE", "APPLY"])
        self.assertEqual(chk.effective_seqs[: self.k + 1], tuple(range(self.k + 1)))

    def test_the_plan_and_the_checker_agree_on_which_points_are_below_the_floor(self):
        for point in range(0, len(self.b.events)):
            planned = None
            try:
                R4.prep(self.b, point, {"*": "REAPPLY"}, D[6], "rr3")
            except Exception as e:                                             # noqa: BLE001
                planned = getattr(e, "rule", None)
            if point < self.k:
                self.assertEqual(planned, FLOOR, point)
            else:
                self.assertNotEqual(planned, FLOOR, point)


def adopted_history():
    b, data, k = adopted_world()
    return b, b.history(), data, k


class LaterStages(unittest.TestCase):
    def setUp(self):
        self.b, self.h, self.data, self.k = adopted_history()
        self.w = self.b.w

    def test_b2_day_after_the_adoption_has_the_adoption_as_parent(self):
        res = T.day(self.h, D[6], self.w)
        self.assertEqual(res.status, "PREPARED")
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["kind"], rec["seq"], rec["parent_seq"], rec["parent_hash"]),
                         ("APPLY", self.k + 1, self.k, self.b.events[self.k]["event_hash"]))
        grown = T.extend(self.h, res)
        chk = V.validate_history(grown)
        self.assertEqual(chk.head_seq, self.k + 1)
        self.assertEqual(chk.effective_seqs, tuple(range(self.k + 2)))
        self.assertEqual(chk.latest_apply_d, D[6])

    def test_b2_day_already_applied_before_the_damage_is_not_applied_twice(self):
        res = T.day(self.h, D[5], self.w)
        self.assertEqual(res.status, "ALREADY_APPLIED")

    def test_b2_ack_and_declare_on_the_adopted_history(self):
        extra = P.obs("X5", D[5], 41.0, hour=21)
        cmds = [T.ack_cmd(self.h, "ADDED", D[5], [T.fp(extra)], 5)]
        plan, res = T.run_plan(self.h, cmds, self.w.sessions, list(self.w.ledger) + [extra], D[5], "ak1")
        self.assertEqual((plan.status, res.status), ("READY", "CONFIRMED_IN_MEMORY"))
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["kind"], rec["parent_seq"]), ("ACK", self.k))
        V.validate_history(T.extend(self.h, res))
        led = [r for r in self.w.ledger if r.get("record_id") != "R-" + D[6]]
        self.assertEqual(len(led), len(self.w.ledger) - 1)
        plan, res = T.run_plan(self.h, [T.decl_cmd(D[6])], self.w.sessions, led, D[6], "dc1")
        self.assertEqual((plan.status, res.status), ("READY", "CONFIRMED_IN_MEMORY"))
        rec = res.batch.body["records"][0]
        self.assertEqual((rec["kind"], rec["d"], rec["parent_seq"]), ("DECLARE_MISSING", D[6], self.k))
        V.validate_history(T.extend(self.h, res))

    def test_b3_restart_on_the_adopted_history(self):
        plan, res = R3.run(self.h, self.w, D[9], D[9], "rs1")
        self.assertEqual((plan.status, res.status), ("READY", "CONFIRMED_IN_MEMORY"))
        events = res.history.events
        self.assertEqual((events[-1]["kind"], events[-1]["parent_seq"]), ("RESTART_UNKNOWN", self.k))
        V.validate_history(res.history)

    def test_the_id_of_the_adoption_record_is_taken_in_b2_b3_and_b4_plans(self):
        extra = P.obs("X5", D[5], 41.0, hour=21)
        cmds = [T.ack_cmd(self.h, "ADDED", D[5], [T.fp(extra)], 5)]
        taken = ("history_request_conflict", "request_id", None)
        self.assertEqual(T.err(T.plan_for, self.h, cmds, self.w.sessions, list(self.w.ledger) + [extra], D[5], "ad1"),
                         taken)
        self.assertEqual(T.err(T.plan_for, self.h, [T.decl_cmd(D[6])], self.w.sessions,
                               [r for r in self.w.ledger if r.get("record_id") != "R-" + D[6]], D[6], "ad1"), taken)
        e = R3.refusal(R3.prep, self.h, self.w, D[9], D[9], "ad1")
        self.assertEqual(e, taken)
        b, _data, _k = with_restart_and_apply()
        self.assertEqual(R4.rule_of(R4.prep, b, self.k, {7: "DROP", 8: "REAPPLY"}, D[6], "ad1")[:2],
                         ("history_request_conflict", "request_id"))

    def test_a_new_request_id_is_not_taken(self):
        plan, res = R3.run(self.h, self.w, D[9], D[9], "ad2")
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")

    def test_the_effective_view_lists_the_adoption_request(self):
        view = O.read_effective(self.h).to_dict()
        found = [r for r in view["requests"] if r["record_kind"] == "RECOVERY_PREFIX_ADOPTION"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["request_id"], "ad1")
        self.assertEqual(found[0]["seqs"], [self.k])
        self.assertTrue(found[0]["effective"])
        self.assertEqual(found[0]["request_hash"], self.b.events[self.k]["request_hash"])
        self.assertEqual(set(found[0]), {"request_id", "record_kind", "request_hash", "seqs", "effective", "source"})
        # the interval, the applies and the resolutions are the prefix's own
        before = O.read_effective(H.history_of(self.b.events[: self.k])).to_dict()
        for key in ("segments", "applies", "resolutions", "current_boundary", "latest_apply_d", "processing_after"):
            self.assertEqual(view[key], before[key], key)

    def test_the_view_of_a_history_without_an_adoption_is_unchanged(self):
        view = O.read_effective(H.example_r().history()).to_dict()
        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", [r["record_kind"] for r in view["requests"]])


if __name__ == "__main__":
    unittest.main()
