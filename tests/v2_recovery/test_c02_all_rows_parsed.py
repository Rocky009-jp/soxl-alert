"""C-02: every row is parsed on its own before anything is excluded; bad input is never turned into 'unobserved'."""
import unittest

import r_helpers as H
from r_helpers import D, R


def bad_row(**changes):
    row = H.P.obs("BAD", D[2], 30.0)
    row.update(changes)
    return row


class EveryRowIsParsed(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.rs = R.empty_resolutions()
        self.good = list(self.w.ledger)

    def test_unparsable_values_stop_with_the_core_input_error(self):
        cases = {
            "bool": (bad_row(current_fg_value=True), "fg_value_invalid"),
            "huge_int": (bad_row(current_fg_value=10 ** 400), "fg_value_invalid"),
            "nan": (bad_row(current_fg_value=float("nan")), "fg_value_invalid"),
            "inf": (bad_row(current_fg_value=float("inf")), "fg_value_invalid"),
            "text": (bad_row(current_fg_value="abc"), "fg_value_invalid"),
            "role": (bad_row(observation_role="decision "), "role_unknown"),
            "status": (bad_row(observation_status="seen"), "status_unknown"),
            "date": (bad_row(target_us_session_date="2026-02-30"), "invalid_date"),
            "time": (bad_row(observed_at_iso8601="2026-03-03T20:00"), "datetime_missing_timezone"),
            "id": (bad_row(record_id="has space"), "record_id_invalid"),
        }
        for name, (row, code) in cases.items():
            with self.subTest(name):
                ledger = self.good + [row]
                H.expect_code(self, code, H.resolve, self.w, self.rs, ledger, D[1])
                H.expect_code(self, code, R.prepare_resolved_day, self.w.snap(), self.rs, D[2], self.w.series,
                              self.w.sessions, ledger)
                cmds = [H.declare(D[2])]
                H.expect_code(self, code, H.plan_for, self.w, self.rs, cmds, ledger, D[2])

    def test_a_bad_row_cannot_be_named_away(self):
        # the fingerprint of a row that does not parse cannot even be computed; naming a good row does not help
        ledger = self.good + [bad_row(current_fg_value="abc")]
        cmd = H.ack(self.w.snap(), "ADDED", D[1], [H.fp(self.good[0])])
        H.rule_of(self, H.plan_for, self.w, self.rs, [cmd], self.good, D[1])      # the good ledger alone is refused
        H.expect_code(self, "fg_value_invalid", H.plan_for, self.w, self.rs, [cmd], ledger, D[1])

    def test_not_an_observation_and_not_a_list(self):
        H.expect_code(self, "observation_invalid", H.resolve, self.w, self.rs, self.good + ["x"], D[1])
        H.expect_code(self, "observation_invalid", H.resolve, self.w, self.rs, "rows", D[1])
        H.expect_code(self, "observation_invalid", H.resolve, self.w, self.rs, None, D[1])

    def test_a_bad_value_is_never_downgraded_to_no_signal(self):
        ledger = self.good + [bad_row(current_fg_value="abc")]
        with self.assertRaises(H.InputError):
            R.prepare_resolved_day(self.w.snap(), self.rs, D[2], self.w.series, self.w.sessions, ledger)

    def test_no_value_text_in_the_error(self):
        ledger = self.good + [bad_row(current_fg_value=H.URL)]
        with self.assertRaises(H.InputError) as cm:
            H.resolve(self.w, self.rs, ledger, D[1])
        self.assertNotIn("secret-token", str(cm.exception) + repr(cm.exception.__dict__))


class EmptySetKeepsS1Behaviour(unittest.TestCase):
    def test_conflict_between_versions_is_not_hidden_by_an_empty_set(self):
        w = H.world(1)
        row_a = H.P.obs("X1", D[2], 27.0)
        row_b = H.P.obs("X1", D[2], 40.0)                  # same id, other content
        ledger = list(w.ledger) + [row_a, row_b]
        H.expect_code(self, "record_id_conflict", H.resolve, w, R.empty_resolutions(), ledger, D[1])

    def test_a_conflict_outside_every_command_is_not_widened(self):
        w = H.world(1)
        rs = R.empty_resolutions()
        # a conflict on an unrelated day; an ADDED command for D1 must not make it disappear
        extra = H.P.obs("B1", D[1], 40.0, hour=21)
        c1, c2 = H.P.obs("U1", D[5], 27.0), H.P.obs("U1", D[5], 41.0)
        ledger = list(w.ledger) + [extra, c1, c2]
        cmd = H.ack(w.snap(), "ADDED", D[1], [H.fp(extra)])
        H.expect_code(self, "record_id_conflict", H.plan_for, w, rs, [cmd], ledger, D[1])

    def test_a_conflict_at_or_before_genesis_is_not_widened(self):
        w = P_world_with_start(2)
        ledger = [H.P.obs("G1", D[0], 27.0), H.P.obs("G1", D[0], 41.0)]
        H.expect_code(self, "record_id_conflict", H.resolve, w, R.empty_resolutions(), ledger, D[3])


def P_world_with_start(idx):
    w = H.P.World(start_idx=idx)
    return w


if __name__ == "__main__":
    unittest.main()
