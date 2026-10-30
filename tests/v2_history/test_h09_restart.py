"""H-09: RESTART_UNKNOWN (design 7). Example U, the three floor values, boundary, no-op, state reset, and the
guarantee that later ACK / DECLARE_MISSING records do not move the processing boundary."""
import unittest

import h_helpers as H
from h_helpers import D, V

from v2_core.tri import Tri


def fp(rid, d):
    return H.fp(H.P.obs(rid, d, 41.0, hour=21))


class ExampleU(unittest.TestCase):
    def test_accepted_with_the_designs_values(self):
        b = H.example_u()
        chk = b.check()
        self.assertEqual(b.events[3]["floor"], {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[0]})
        self.assertEqual(b.events[3]["state_after"], H.initial_state())
        self.assertEqual(b.events[3]["boundary_session"], H.sess(D[3]))
        self.assertEqual(chk.current_boundary, V.Boundary("RESTART_UNKNOWN", 3, D[3]))
        self.assertEqual((chk.latest_apply_d, chk.processing_after), (D[2], D[3]))
        self.assertEqual(chk.effective_seqs, (0, 1, 2, 3))
        self.assertEqual(V.validate_history(H.history_of(b.events)).record_count, 4)
        self.assertEqual(b.events[3]["request_basis"]["reason_code"], "RESTART_UNKNOWN")

    def test_the_first_apply_after_the_restart_follows_the_core(self):
        cases = {"fg_30_or_more": (31.0, "UNKNOWN", 1), "fg_below_25": (20.0, "FALSE", 0),
                 "fg_25_to_30": (27.0, "UNKNOWN", 0)}
        for name, (value, armed, streak) in cases.items():
            with self.subTest(name):
                b = H.example_u()
                rec = b.apply(D[4], value)
                self.assertEqual(rec["state_after"]["armed"], Tri(armed).value)
                self.assertEqual(rec["state_after"]["streak"], streak)
                self.assertFalse(rec["transition_result"]["gap"])
                self.assertEqual(rec["skipped_sessions"], [])
                self.assertIsNone(rec["state_after"]["base"]["as_of_d"])
                self.assertEqual(rec["confirmed_inputs"]["session_context"][0], b.events[3]["boundary_session"])
                b.check()

    def test_a_missing_day_after_the_restart_is_skipped_without_a_gap(self):
        b = H.example_u()
        rec = b.apply(D[5], 31.0)                                            # D4 has no decision
        self.assertEqual(rec["skipped_sessions"], [D[4]])
        self.assertFalse(rec["transition_result"]["gap"])
        b.check()

    def test_a_day_at_or_before_the_boundary_cannot_be_applied_in_the_new_segment(self):
        b = H.example_u()
        for src in (1, 2):                                                   # the APPLYs of D1 / D2 again
            with self.subTest(src):
                ev = H.deep(b.events)
                dup = H.deep(ev[src])
                dup["seq"], dup["parent_seq"] = 4, 3
                ev.append(dup)
                H.expect_rule(self, "s1:d_order", H.rebuild(ev))

    def test_ack_and_declare_after_the_restart_do_not_move_the_boundary(self):
        b = H.example_u()
        before = b.check()
        b.declare(D[4], "qd")
        after = b.check()
        self.assertEqual(after.current_boundary, before.current_boundary)
        self.assertEqual(after.processing_after, before.processing_after)
        self.assertEqual(after.processing_after, D[3])
        self.assertEqual(after.declared_days_in_segment, (D[4],))
        self.assertEqual(b.events[4]["frontier_before"], D[3])
        self.assertEqual(after.state_digest, before.state_digest)
        c = H.example_u()
        c.apply(D[4], 31.0)
        c.ack("ADDED", D[4], [fp("X1", D[4])], "qa", applied=4)
        chk = c.check()
        self.assertEqual(chk.current_boundary, V.Boundary("RESTART_UNKNOWN", 3, D[3]))
        self.assertEqual(chk.processing_after, D[4])                         # the state's as_of_d, not the ACK

    def test_a_second_restart_below_the_previous_boundary_is_refused(self):
        b = H.example_u()
        b.restart(D[2], "q2")                                                # RT-09 / design 7.3's last row
        H.expect_rule(self, "restart_floor", b.history())


class Floor(unittest.TestCase):
    def test_each_floor_value_is_enforced(self):
        # last APPLY day
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.restart(D[1], "q1")
        H.expect_rule(self, "restart_floor", b.history())
        # last declared day (resume_after equal to the last APPLY day, earlier than the declaration)
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "qd")
        c.restart(D[1], "q1")
        H.expect_rule(self, "restart_floor", c.history())
        # previous boundary
        d = H.HB()
        d.apply(D[1], 27.0)
        d.restart(D[2], "q1")
        d.restart(D[1], "q2")
        H.expect_rule(self, "restart_floor", d.history())

    def test_exactly_the_floor_is_accepted(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.restart(D[2], "q1")
        b.check()
        c = H.HB()
        c.apply(D[1], 27.0)
        c.declare(D[2], "qd")
        c.restart(D[2], "q1")
        self.assertEqual(c.events[3]["floor"], {"last_apply_d": D[1], "last_declared_d": D[2], "prev_boundary": D[0]})
        c.check()

    def test_a_false_floor_is_refused(self):
        base = H.example_u().events
        for name, floor in {
                "apply_day": {"last_apply_d": D[1], "last_declared_d": None, "prev_boundary": D[0]},
                "declared_day": {"last_apply_d": D[2], "last_declared_d": D[1], "prev_boundary": D[0]},
                "boundary": {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[1]},
                "nulls": {"last_apply_d": None, "last_declared_d": None, "prev_boundary": D[0]},
                "missing_key": {"last_apply_d": D[2], "prev_boundary": D[0]},
                "extra_key": {"last_apply_d": D[2], "last_declared_d": None, "prev_boundary": D[0], "x": 1},
                "not_a_dict": [D[2]]}.items():
            with self.subTest(name):
                ev = H.deep(base)
                ev[3]["floor"] = floor
                H.expect_rule(self, "restart_floor", H.rebuild(ev))


class BoundaryAndRequest(unittest.TestCase):
    def test_noop_restarts(self):
        b = H.HB()
        b.restart(D[0], "q1")
        H.expect_rule(self, "restart_noop", b.history())
        c = H.example_u()
        c.restart(D[3], "q2")
        H.expect_rule(self, "restart_noop", c.history())

    def test_a_restart_that_moves_the_boundary_or_resets_a_used_state_is_not_a_noop(self):
        b = H.HB()
        b.restart(D[2], "q1")                                                # initial state, but the boundary moves
        b.check()
        c = H.HB()
        c.apply(D[1], 27.0)
        c.restart(D[1], "q1")                                                # the state is used and gets reset
        chk = c.check()
        self.assertEqual(chk.current_boundary, V.Boundary("RESTART_UNKNOWN", 2, D[1]))

    def test_resume_after_must_not_pass_check_d(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.restart(D[3], "q1", check_d=D[2])
        H.expect_rule(self, "check_d", b.history())
        c = H.HB()
        c.apply(D[1], 27.0)
        c.restart(D[3], "q1", check_d=D[3])
        c.check()

    def test_the_new_state_must_be_the_initial_state(self):
        ev = H.deep(H.example_u().events)
        ev[3]["state_after"] = H.deep(ev[2]["state_after"])
        H.expect_rule(self, "state_after", H.rebuild(ev))

    def test_the_boundary_session(self):
        base = H.example_u().events
        cases = {
            "other_date": lambda s: s.update(date=D[4]),
            "unconfirmed": lambda s: s.update(confirmed=False),
            "not_canonical": lambda s: s.update(open_at="2026-03-05T14:30:00-05:00"),
            "missing_key": lambda s: s.pop("open_at"),
            "close_before_open": lambda s: s.update(close_at=s["open_at"]),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                ev = H.deep(base)
                fn(ev[3]["boundary_session"])
                H.expect_rule(self, "restart_boundary", H.rebuild(ev))
        ev = H.deep(base)
        ev[3]["resume_after"] = "soon"
        ev[3]["request_basis"]["resume_after"] = "soon"
        H.expect_rule(self, "restart_boundary", H.rebuild(ev))

    def test_request_fields(self):
        base = H.example_u().events
        def hashed(ev):
            ev[3]["request_hash"] = H.request_hash(ev[3]["request_basis"])
            return H.rebuild(ev)
        ev = H.deep(base)
        ev[3]["request_basis"]["resume_after"] = D[4]
        H.expect_rule(self, "request_basis", hashed(ev))
        ev = H.deep(base)
        ev[3]["request_basis"]["extra"] = 1
        H.expect_rule(self, "request_basis", hashed(ev))
        ev = H.deep(base)
        ev[3]["request_basis"]["reason_code"] = "OTHER"
        H.expect_rule(self, "reason_code", hashed(ev))
        ev = H.deep(base)
        ev[3]["requested_at"] = "2030-01-01T00:00:00Z"
        H.expect_rule(self, "requested_at", H.rebuild(ev))
        ev = H.deep(base)
        ev[3]["request_hash"] = "0" * 64
        H.expect_rule(self, "request_hash", H.rebuild(ev))
        ev = H.deep(base)
        ev[3]["request_basis"]["check_d"] = "later"
        H.expect_rule(self, "check_d", hashed(ev))
        ev = H.deep(base)
        ev[3]["request_id"] = ev[3]["request_basis"]["request_id"] = "a b"
        H.expect_rule(self, "request_id", hashed(ev))


class SegmentsAcrossRestarts(unittest.TestCase):
    def test_days_are_unique_and_increasing_across_segments(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.restart(D[2], "q1")
        b.apply(D[3], 31.0)
        b.restart(D[3], "q2")
        b.apply(D[4], 32.0)
        chk = b.check()
        self.assertEqual(chk.latest_apply_d, D[4])
        self.assertEqual(chk.current_boundary, V.Boundary("RESTART_UNKNOWN", 5, D[3]))
        self.assertEqual(b.events[5]["floor"], {"last_apply_d": D[3], "last_declared_d": None, "prev_boundary": D[2]})
        # an APPLY of an earlier segment's day added after the second restart is refused by the S1 projection
        ev = H.deep(b.events)
        dup = H.deep(ev[2])
        dup["seq"], dup["parent_seq"] = 7, 6
        ev.append(dup)
        H.expect_rule(self, "s1:d_order", H.rebuild(ev))

    def test_declared_days_before_a_restart_are_part_of_its_floor(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "qd")
        b.apply(D[3], 29.0)
        b.restart(D[3], "q1")
        self.assertEqual(b.events[4]["floor"], {"last_apply_d": D[3], "last_declared_d": D[2], "prev_boundary": D[0]})
        chk = b.check()
        self.assertEqual(chk.declared_days_in_segment, ())                   # the declaration belongs to the old segment


if __name__ == "__main__":
    unittest.main()
