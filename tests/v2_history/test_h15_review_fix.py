"""Review fix R-01 / R-02 of the B-1 receipt review (regressions kept apart from the original 217 tests).

R-01: integer fields are exact ints, never values that merely compare equal (True == 1, 1.0 == 1).
R-02: the public scalar accessors of an unchecked History / MigrationPlan return independent copies of nested values.
Every refusal case has a matching accepted control (0 / 1, normal history, normal plan).
"""
import unittest

import h_helpers as H
from h_helpers import D, V


def restore_history():
    b = H.HB()
    b.apply(D[1], 30.0)
    b.restore(0, {1: "REAPPLY"}, "restore-zero")
    return b.history()


def migrated_history(apply_days=2):
    w = H.P.World()
    for i in range(1, apply_days + 1):
        w.apply(D[i], 29.0 + i, "R%d" % i)
    snap, rs = w.snap(), H.R.empty_resolutions()
    plan = V.prepare_migration_plan(snap, rs, w.sessions, list(w.ledger), D[5], "mig-fix", H.WHEN)
    return V.History.from_dict(plan.basis["candidate_history"])


class R01SupersededEntries(unittest.TestCase):
    def test_control_and_non_int_entries(self):
        h = restore_history()
        chk = V.validate_history(h)
        self.assertEqual(chk.superseded_seqs, (1,))
        for value in (True, 1.0):
            with self.subTest(type(value).__name__):
                ev = H.deep(h.events)
                ev[2]["superseded_seqs"] = [value]
                H.expect_rule(self, "superseded_mismatch", H.rebuild(ev, remap=True))

    def test_bool_and_float_where_the_list_is_longer(self):
        ev = H.example_r().events
        V.validate_history(H.history_of(ev))                     # control: the accepted example R
        for index, pos, value in ((7, 0, 3.0), (7, 2, 5.0), (14, 1, 11.0), (18, 4, 14.0)):
            with self.subTest((index, pos, type(value).__name__)):
                def edit(rec, pos=pos, value=value):
                    rec["superseded_seqs"][pos] = value
                H.expect_rule(self, "superseded_mismatch", H.rebuild_edit(ev, index, edit))

    def test_exact_ints_still_pass_and_other_wrong_lists_still_fail(self):
        ev = H.example_r().events
        H.rebuild_edit(ev, 7, lambda rec: None)                   # unchanged content, rebuilt: accepted
        V.validate_history(H.rebuild_edit(ev, 7, lambda rec: None))
        H.expect_rule(self, "superseded_mismatch", H.rebuild_edit(ev, 7, lambda rec: rec["superseded_seqs"].pop()))
        H.expect_rule(self, "superseded_mismatch", H.rebuild_edit(ev, 7, lambda rec: rec.update(superseded_seqs="3456")))


class R01MigrationSource(unittest.TestCase):
    def setUp(self):
        self.h = migrated_history()
        V.validate_history(self.h)                                # control: the unchanged history is accepted
        self.last = len(self.h.events) - 1

    def rule(self, field, value):
        ev = H.deep(self.h.events)
        ev[self.last]["source"][field] = value
        return H.rule_of(self, H.rebuild(ev))

    def test_schema_version_must_be_the_int_one(self):
        for value in (True, 1.0, "1", 2, 0):
            with self.subTest(repr(value)):
                self.assertEqual(self.rule("schema_version", value), "migration_source")

    def test_head_seq_must_be_the_exact_int(self):
        head = self.h.events[self.last]["source"]["head_seq"]
        self.assertIs(type(head), int)
        for value in (True, float(head), str(head), head + 1, -1):
            with self.subTest(repr(value)):
                self.assertEqual(self.rule("head_seq", value), "migration_source")

    def test_head_seq_zero_boundary(self):
        w = H.P.World()                                           # only GENESIS: the source head is 0
        snap, rs = w.snap(), H.R.empty_resolutions()
        plan = V.prepare_migration_plan(snap, rs, w.sessions, list(w.ledger), D[5], "mig-zero", H.WHEN)
        h = V.History.from_dict(plan.basis["candidate_history"])
        V.validate_history(h)                                     # control: 0 is accepted
        ev = H.deep(h.events)
        self.assertEqual(ev[-1]["source"]["head_seq"], 0)
        for value in (False, 0.0):
            with self.subTest(repr(value)):
                ev[-1]["source"]["head_seq"] = value
                H.expect_rule(self, "migration_source", H.rebuild(ev))

    def test_origin_source_head_seq_must_be_an_exact_int(self):
        h, _ = H.example_m()
        V.validate_history(H.history_of(h.events))
        index = next(i for i, r in enumerate(h.events) if r.get("origin") is not None and r["origin"]["source_head_seq"] == 1)
        for value in (True, 1.0):
            with self.subTest(repr(value)):
                ev = H.deep(h.events)
                ev[index]["origin"]["source_head_seq"] = value
                H.expect_rule(self, "origin", H.rebuild(ev, remap=True))


class R02PublicAccessors(unittest.TestCase):
    NESTED = ({"nested": []}, [1, [2]])

    def history_with(self, field, value):
        data = H.example_u().history().to_dict()
        data[field] = H.deep(value)
        return V.History.from_dict(data)

    def test_a_normal_history_reads_as_before(self):
        h = H.example_u().history()
        self.assertEqual((h.head_seq, h.schema_version), (3, 2))
        self.assertIsInstance(h.head_hash, str)
        self.assertEqual(h.head_hash, h.events[-1]["event_hash"])
        self.assertEqual(h.schema_version, V.SCHEMA_VERSION_V2)

    def test_nested_values_returned_by_an_unchecked_history_are_independent(self):
        for field in ("head_seq", "head_hash", "schema_version"):
            for value in self.NESTED:
                with self.subTest((field, repr(value))):
                    h = self.history_with(field, value)
                    twin = self.history_with(field, value)
                    before = (h.to_dict(), V.encode_history(h), h.digest, hash(h))
                    got = getattr(h, field)
                    self.assertEqual(got, value)
                    self.assertIsNot(got, getattr(h, field))        # a fresh copy each time
                    got.append(7) if isinstance(got, list) else got.update(x=7)
                    if isinstance(got, list) and got and isinstance(got[0], list):
                        got[1].append(9)
                    self.assertEqual(getattr(h, field), value)       # the next read is the original
                    self.assertEqual((h.to_dict(), V.encode_history(h), h.digest, hash(h)), before)
                    self.assertEqual(h, twin)

    def test_the_other_accessors_stay_independent(self):
        h = H.example_u().history()
        h.events.append(1)
        h.current_state["x"] = 1
        h.to_dict()["events"].clear()
        self.assertEqual(len(h.events), 4)
        self.assertNotIn("x", h.current_state)

    def test_plan_hash(self):
        w = H.P.World()
        w.apply(D[1], 29.0, "R1")
        snap, rs = w.snap(), H.R.empty_resolutions()
        plan = V.prepare_migration_plan(snap, rs, w.sessions, list(w.ledger), D[5], "mig-ph", H.WHEN)
        self.assertEqual(len(plan.plan_hash), 64)                    # control: a normal plan reads as before
        self.assertEqual(plan.plan_hash, plan.to_dict()["plan_hash"])
        for value in self.NESTED:
            with self.subTest(repr(value)):
                forged = V.MigrationPlan.from_dict({"basis": {}, "plan_hash": H.deep(value)})
                twin = V.MigrationPlan.from_dict({"basis": {}, "plan_hash": H.deep(value)})
                before = (forged.to_dict(), hash(forged))
                got = forged.plan_hash
                self.assertEqual(got, value)
                self.assertIsNot(got, forged.plan_hash)
                got.append(7) if isinstance(got, list) else got.update(x=7)
                if isinstance(got, list) and isinstance(got[1], list):
                    got[1].append(9)
                self.assertEqual(forged.plan_hash, value)
                self.assertEqual((forged.to_dict(), hash(forged)), before)
                self.assertEqual(forged, twin)


class P02ExampleRSameFlag(unittest.TestCase):
    """The same_as_superseded flag of example R's #10 depends on the synthetic F&G value of D2; the checker states the
    fact for either input. D2 = 28 (the fixed example) gives True, D2 = 30 gives False."""

    @staticmethod
    def flags(d2):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], d2)
        b.restart(D[2], "q1")
        b.apply(D[3], 31.0)
        b.ack("ADDED", D[3], [H.fp(H.P.obs("B3", D[3], 41.0, hour=21))], "q2", applied=4)
        b.apply(D[4], 32.0)
        b.restore(2, {3: "DROP", 4: "REAPPLY", 5: "REPLAY", 6: "REAPPLY"}, "q4")
        V.validate_history(b.history())
        return [(e["from_seq"], e["same_as_superseded"]) for e in b.events[7]["replay"] if e["op"] == "REAPPLY"]

    def test_the_flag_follows_the_input(self):
        self.assertEqual(self.flags(28.0), [(4, False), (6, True)])
        self.assertEqual(self.flags(30.0), [(4, False), (6, False)])

    def test_a_wrong_flag_is_refused_for_either_input(self):
        for d2, wrong in ((28.0, False), (30.0, True)):
            with self.subTest(d2):
                b = H.HB()
                b.apply(D[1], 27.0)
                b.apply(D[2], d2)
                b.restart(D[2], "q1")
                b.apply(D[3], 31.0)
                b.ack("ADDED", D[3], [H.fp(H.P.obs("B3", D[3], 41.0, hour=21))], "q2", applied=4)
                b.apply(D[4], 32.0)
                b.restore(2, {3: "DROP", 4: "REAPPLY", 5: "REPLAY", 6: "REAPPLY"}, "q4")

                def flip(rec):
                    rec["replay"][3]["same_as_superseded"] = wrong
                H.expect_rule(self, "restore_replay_mismatch", H.rebuild_edit(b.events, 7, flip))


if __name__ == "__main__":
    unittest.main()
