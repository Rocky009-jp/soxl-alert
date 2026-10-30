"""H-07: each segment of a chain view is re-attached to a fresh S1 history and checked by the unchanged
validate_snapshot (spied), so no rule, threshold or state formula is written in v2_history."""
import unittest
from unittest import mock

import h_helpers as H
from h_helpers import D, V

import v2_history.view as view_module
from v2_persistence.events import input_hash_of
from v2_persistence.recompute import validate_snapshot as real_validate


def fp(rid, d):
    return H.fp(H.P.obs(rid, d, 41.0, hour=21))


class UsesTheExistingChecker(unittest.TestCase):
    def test_validate_snapshot_is_called_once_per_segment_of_every_view(self):
        seen = []

        def spy(snapshot):
            seen.append((snapshot.schema_version, len(snapshot.events), snapshot.events[0]["kind"]))
            return real_validate(snapshot)
        with mock.patch.object(view_module, "validate_snapshot", side_effect=spy) as m:
            H.example_r().check()
        # final view: 1 segment; RESTORE#1 view (0..6): 2; RESTORE#2 view (..13): 2; RESTORE#3 view (..17): 1
        self.assertEqual(m.call_count, 6)
        self.assertTrue(all(v == 1 and kind == "GENESIS" for v, _n, kind in seen))
        # events per projected history: RESTORE#1 view 3+3, RESTORE#2 view 6+2, RESTORE#3 view 7, final view 7
        self.assertEqual(sorted(n for _v, n, _k in seen), [2, 3, 3, 6, 7, 7])

    def test_the_rule_of_the_s1_checker_is_passed_on_with_its_prefix(self):
        def failing(_snapshot):
            raise H.PersistenceError("snapshot_invalid", "snapshot", rule="spy-rule")
        with mock.patch.object(view_module, "validate_snapshot", side_effect=failing):
            H.expect_rule(self, "s1:spy-rule", H.example_u().history())

    def test_the_s1_checker_judges_the_projection_with_a_fresh_genesis_and_attached_parents(self):
        captured = []

        def spy(snapshot):
            captured.append(snapshot.events)
            return real_validate(snapshot)
        b = H.HB()
        b.apply(D[1], 27.0)
        b.ack("ADDED", D[1], [fp("X1", D[1])], "qa", applied=1)
        b.apply(D[2], 28.0)
        with mock.patch.object(view_module, "validate_snapshot", side_effect=spy):
            b.check()
        events = captured[0]
        self.assertEqual([e["kind"] for e in events], ["GENESIS", "APPLY", "APPLY"])
        self.assertEqual([e["seq"] for e in events], [0, 1, 2])              # re-attached: the ACK is not counted
        self.assertEqual(events[2]["parent_hash"], events[1]["event_hash"])


class ApplyContentIsRecalculated(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)                                                  # 1
        b.apply(D[2], 28.0)                                                  # 2
        b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2)              # 3
        b.apply(D[3], 31.0)                                                  # 4
        self.ev = b.events

    def mut(self, fn, index=2):
        ev = H.deep(self.ev)
        fn(ev[index])
        return H.rebuild(ev)

    def test_unchanged_history_is_accepted(self):
        V.validate_history(H.history_of(self.ev))

    def test_every_apply_field_is_judged_with_an_s1_rule(self):
        cases = {
            "transition_result": (lambda r: r["transition_result"].update(gap=not r["transition_result"]["gap"]),
                                  "s1:transition_mismatch"),
            "transition_notes": (lambda r: r["transition_result"].update(notes=["x"]), "s1:transition_mismatch"),
            "state_after_streak": (lambda r: r["state_after"].update(streak=r["state_after"]["streak"] + 1),
                                   None),
            "input_hash": (lambda r: r.update(input_hash="0" * 64), "s1:input_hash"),
            "skipped_sessions": (lambda r: r.update(skipped_sessions=[D[1]]), "s1:skipped_sessions"),
            "row": (lambda r: r["confirmed_inputs"]["row"].update(rsi=r["confirmed_inputs"]["row"]["rsi"] + 1),
                    None),
            "context_boundary": (lambda r: r["confirmed_inputs"]["session_context"][0].update(open_at="2026-03-03T00:00:00Z"),
                                 None),
            "d": (lambda r: r.update(d=D[9]), None),
        }
        for name, (fn, rule) in cases.items():
            with self.subTest(name):
                got = H.rule_of(self, self.mut(fn))
                self.assertTrue(got.startswith("s1:"), got)
                if rule is not None:
                    self.assertEqual(got, rule)

    def test_malformed_confirmed_inputs_get_an_s1_rule_not_an_exception(self):
        for name, fn in {"not_a_dict": lambda r: r.update(confirmed_inputs=5),
                         "missing_key": lambda r: r["confirmed_inputs"].pop("row"),
                         "context_not_list": lambda r: r["confirmed_inputs"].update(session_context=7)}.items():
            with self.subTest(name):
                got = H.rule_of(self, self.mut(fn))
                self.assertTrue(got.startswith("s1:"), got)

    def test_ib04_holds_with_acks_and_declarations_between_applies(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.ack("ADDED", D[1], [fp("X1", D[1])], "qa", applied=1)
        b.ack("ADDED", D[1], [fp("X2", D[1])], "qb", applied=1)
        b.declare(D[2], "qd")
        b.apply(D[3], 29.0)                                                  # skips the declared D2
        chk = b.check()
        self.assertEqual(chk.latest_apply_d, D[3])
        self.assertEqual(b.events[-1]["skipped_sessions"], [D[2]])
        self.assertEqual(b.events[-1]["state_after"]["base"]["as_of_d"], D[1])

    def test_ib04_base_mismatch_after_a_control_record_is_an_s1_failure(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2)
        b.apply(D[3], 29.0)
        ev = H.deep(b.events)
        ev[4]["state_after"]["base"]["as_of_d"] = D[0]
        H.expect_rule(self, "s1:IB-04", H.rebuild(ev))

    def test_a_restart_boundary_is_the_s1_start_of_its_segment(self):
        b = H.example_u()
        b.apply(D[4], 27.0)
        ev = H.deep(b.events)
        ev[4]["confirmed_inputs"]["session_context"][0]["open_at"] = "2026-03-05T00:00:00Z"
        ev[4]["input_hash"] = input_hash_of(ev[4]["confirmed_inputs"])
        H.expect_rule(self, "s1:context_boundary", H.rebuild(ev))
        ev = H.deep(b.events)
        ev[3]["boundary_session"]["open_at"] = "2026-03-05T00:00:00Z"
        ev[3]["boundary_session"]["close_at"] = "2026-03-05T01:00:00Z"
        H.expect_rule(self, "s1:context_boundary", H.rebuild(ev))


class ControlRecordStateAfter(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)                                                  # 1
        b.apply(D[2], 28.0)                                                  # 2
        b.ack("ADDED", D[2], [fp("X1", D[2])], "qa", applied=2)              # 3
        b.declare(D[3], "qd")                                                # 4
        b.apply(D[4], 29.0)                                                  # 5
        b.restart(D[4], "qr")                                                # 6
        self.ev = b.events

    def test_i15_the_state_after_of_each_control_record(self):
        other = self.ev[1]["state_after"]
        for index in (3, 4, 6):
            with self.subTest(index):
                ev = H.deep(self.ev)
                ev[index]["state_after"] = H.deep(other)
                H.expect_rule(self, "state_after", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[3]["state_after"]["streak"] += 1
        H.expect_rule(self, "state_after", H.rebuild(ev))

    def test_restore_state_after_is_the_restore_points(self):
        ev = H.example_r1().events
        e = H.deep(ev)
        e[7]["state_after"]["streak"] += 1
        H.expect_rule(self, "restore_state", H.rebuild(e, remap=True))

    def test_migration_state_after_is_the_parents(self):
        b, _ = H.example_m()
        e = H.deep(b.events)
        e[7]["state_after"]["streak"] += 1
        H.expect_rule(self, "state_after", H.rebuild(e))

    def test_a_record_after_a_state_changing_ack_keeps_the_truth(self):         # I-10: the current state is the last
        d = H.history_of(self.ev).to_dict()
        d["current_state"]["streak"] += 1
        H.expect_rule(self, "current_state", V.History.from_dict(d))


if __name__ == "__main__":
    unittest.main()
