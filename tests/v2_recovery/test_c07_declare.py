"""C-07 DECLARE_MISSING: only the one session right after the frontier, only when D has no valid decision (N-04)."""
import unittest

import r_helpers as H
from r_helpers import D, R


def row(record_id, d, value, day=None, hour=20, **extra):
    r = H.P.obs(record_id, day or d, value, hour=hour)
    r["target_us_session_date"] = d
    r.update(extra)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.r1 = self.w.ledger[0]

    def plan(self, cmds, extra, check_d, rs=None, rid="decl-1"):
        return H.plan_for(self.w, rs or self.rs, cmds, [self.r1] + list(extra), check_d, rid=rid)

    def run_(self, cmds, extra, check_d, rs=None, rid="decl-1"):
        return H.run(self.w, rs or self.rs, cmds, [self.r1] + list(extra), check_d, rid=rid)


class Eligible(Base):
    def test_no_decision_at_all_is_declared_with_an_empty_list(self):
        res = self.run_([H.declare(D[2])], [], D[2])
        rec = res.resolutions.records[0]
        self.assertEqual((rec["kind"], rec["d"], rec["frontier_before"]), ("DECLARE_MISSING", D[2], D[1]))
        self.assertEqual([e["date"] for e in rec["session_context"]], [D[1], D[2], D[3]])
        self.assertEqual(rec["record_fingerprints"], [])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])
        self.assertEqual(rec["state_after"], self.snap.current_state)            # the market state is not touched

    def test_two_conflicting_decisions_are_declared(self):
        c1, c2 = row("C1", D[2], 27.0), row("C2", D[2], 35.0)
        H.expect_code(self, "decision_conflict", H.resolve, self.w, self.rs, [self.r1, c1, c2], D[2])
        res = self.run_([H.declare(D[2], sorted([H.fp(c1), H.fp(c2)]))], [c1, c2], D[2])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])
        self.assertEqual(sorted(res.effective_ledger.excluded_fingerprints), sorted([H.fp(c1), H.fp(c2)]))

    def test_a_row_in_the_window_for_another_target_is_declared(self):
        m = row("M1", D[3], 30.0, day=D[2])                                       # observed on D2 evening, for D3
        H.expect_code(self, "target_mismatch", H.resolve, self.w, self.rs, [self.r1, m], D[2])
        res = self.run_([H.declare(D[2], [H.fp(m)])], [m], D[2])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])

    def test_a_decision_outside_its_window_is_declared(self):
        o = row("O1", D[2], 30.0, hour=10)                                         # before the close of D2
        H.expect_code(self, "decision_outside_window", H.resolve, self.w, self.rs, [self.r1, o], D[2])
        res = self.run_([H.declare(D[2], [H.fp(o)])], [o], D[2])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])

    def test_same_id_other_version_counts_as_a_related_disturbance(self):
        v1, v2 = row("V1", D[2], 27.0), row("V1", D[2], 28.0)
        res = self.run_([H.declare(D[2], sorted([H.fp(v1), H.fp(v2)]))], [v1, v2], D[2])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])

    def test_not_checked_and_supplemental_rows_do_not_count(self):
        s = row("S1", D[2], 27.0, observation_role="supplemental")
        nc = row("N1", D[2], "", observation_status="not_checked", current_fg_value="", observed_at_iso8601="")
        res = self.run_([H.declare(D[2])], [s, nc], D[2])
        self.assertEqual(len(res.effective_ledger.rows), 3)


class ValidDecisionIsRefused(Base):
    def test_one_valid_decision_is_never_turned_into_a_gap(self):
        valid = row("V1", D[2], 27.0)
        for names in ([], [H.fp(valid)]):
            with self.subTest(names=names):
                H.expect_rule(self, "declare_valid_decision", self.plan, [H.declare(D[2], names)], [valid], D[2])

    def test_identical_resubmission_is_still_one_decision(self):
        valid = row("V1", D[2], 27.0)
        y, m, d = (int(x) for x in D[2].split("-"))
        tz9 = H.P.timezone(H.P.timedelta(hours=9))
        again = dict(valid, observed_at_iso8601=H.P.datetime(y, m, d + 1, 10, 0, tzinfo=tz9).isoformat())
        self.assertEqual(H.fp(valid), H.fp(again))
        H.expect_rule(self, "declare_valid_decision", self.plan, [H.declare(D[2], [H.fp(valid)])], [valid, again], D[2])

    def test_an_unrelated_conflict_on_another_day_is_no_reason(self):
        valid = row("V1", D[2], 27.0)
        u1, u2 = row("U1", D[6], 27.0), row("U1", D[6], 41.0)
        for names in ([], [H.fp(valid)]):
            with self.subTest(names=names):
                H.expect_rule(self, "declare_valid_decision", self.plan, [H.declare(D[2], names)],
                              [valid, u1, u2], D[2])


class Naming(Base):
    def test_missing_and_extra_fingerprints(self):
        c1, c2 = row("C1", D[2], 27.0), row("C2", D[2], 35.0)
        other = row("E1", D[5], 27.0)
        fps = sorted([H.fp(c1), H.fp(c2)])
        for name, names in {"missing_one": fps[:1], "empty": [], "extra": sorted(fps + [H.fp(other)]),
                            "unknown": sorted(fps + ["9" * 64])}.items():
            with self.subTest(name):
                H.expect_rule(self, "declare_incomplete", self.plan, [H.declare(D[2], names)], [c1, c2, other], D[2])


class Frontier(Base):
    def test_unconfirmed_day(self):
        w = H.P.World(unconfirmed=(D[2],))
        w.apply(D[1], 27.0, "R1")
        plan = lambda cmds, cd: H.plan_for(w, R.empty_resolutions(), cmds, list(w.ledger), cd)
        H.expect_rule(self, "declare_unconfirmed", plan, [H.declare(D[2])], D[3])
        # check_d itself unconfirmed: the existing core error comes first
        H.expect_code(self, "target_unconfirmed", plan, [H.declare(D[2])], D[2])

    def test_two_days_in_one_batch_and_the_reverse_order(self):
        res = self.run_([H.declare(D[2]), H.declare(D[3])], [], D[3])
        recs = res.resolutions.records
        self.assertEqual([r["frontier_before"] for r in recs], [D[1], D[2]])
        self.assertEqual([r["d"] for r in recs], [D[2], D[3]])
        H.expect_rule(self, "declare_frontier", self.plan, [H.declare(D[3]), H.declare(D[2])], [], D[3])

    def test_skipping_ahead_redeclaring_and_after_check_d(self):
        H.expect_rule(self, "declare_frontier", self.plan, [H.declare(D[3])], [], D[3])
        done = self.run_([H.declare(D[2])], [], D[2])
        H.expect_rule(self, "declare_frontier", self.plan, [H.declare(D[2])], [], D[3], rs=done.resolutions, rid="d2")
        H.expect_rule(self, "declare_frontier", self.plan, [H.declare(D[2])], [], D[1])

    def test_a_declaration_before_any_apply_starts_at_the_genesis_boundary(self):
        w = H.world(0)
        res = H.run(w, R.empty_resolutions(), [H.declare(D[1])], [], D[1], rid="d1")
        rec = res.resolutions.records[0]
        self.assertEqual((rec["frontier_before"], rec["source_head_seq"]), (D[0], 0))
        self.assertEqual(R.validate_resolutions(w.snap(), res.resolutions).declared_days, (D[1],))
        day = R.prepare_resolved_day(w.snap(), res.resolutions, D[2], w.series, w.sessions, [row("R2", D[2], 33.0)])
        self.assertEqual(day.status, "PREPARED")
        H.expect_rule(self, "declare_frontier", H.plan_for, w, R.empty_resolutions(), [H.declare(D[2])], [], D[2])

    def test_an_applied_day_is_not_declared_again(self):
        H.expect_rule(self, "declare_applied", self.plan, [H.declare(D[1])], [], D[1])

    def test_a_declaration_after_a_later_apply_starts_from_the_new_latest_apply(self):
        done = self.run_([H.declare(D[2])], [], D[2])
        snap = H.extend_with_s1(self.w, D[3], [self.r1] + [row("R3", D[3], 27.0)])
        self.assertEqual(snap.head_seq, 2)
        ledger = [self.r1, row("R3", D[3], 27.0)]
        res = H.run(self.w, done.resolutions, [H.declare(D[4])], ledger, D[4], rid="d4", snapshot=snap)
        self.assertEqual(res.resolutions.records[-1]["frontier_before"], D[3])
        self.assertEqual(R.validate_resolutions(snap, res.resolutions).declared_days, (D[2], D[4]))


class SharedIdAcrossDays(Base):
    def test_one_version_alone_is_a_version_choice_and_both_days_together_are_not(self):
        x2, x3 = row("X1", D[2], 27.0), row("X1", D[3], 28.0)
        H.expect_rule(self, "version_selection", self.plan, [H.declare(D[2], [H.fp(x2)])], [x2, x3], D[3])
        both = [H.declare(D[2], [H.fp(x2)]), H.declare(D[3], [H.fp(x3)])]
        res = self.run_(both, [x2, x3], D[3])
        self.assertEqual(res.effective_ledger.rows, [H.cols(self.r1)])

    def test_a_new_fingerprint_after_the_declaration_stops_again(self):
        done = self.run_([H.declare(D[2])], [], D[2])
        late = row("L2", D[2], 27.0)
        H.expect_code(self, "late_observation", H.resolve, self.w, done.resolutions, [self.r1, late], D[2])


if __name__ == "__main__":
    unittest.main()
