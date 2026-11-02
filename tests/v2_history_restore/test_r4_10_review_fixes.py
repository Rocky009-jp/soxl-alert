"""The review fixes of S3-B-4 (R-01 the listed differences of a replayed acknowledgement, R-02 the order of the plan's own
form against the current inputs, R-03 the four single deletions that were once called equivalent and the no-effect rule).

Only synthetic data. The four R-03 cases and the two R-01 cases come from the review reproduction of the same names; the
current calendar of a case is changed on purpose (a synthetic input, not a claim about any real exchange)."""
import unittest

import r4_helpers as R

T, H, Z, D, P, V = R.T, R.H, R.Z, R.D, R.P, R.V

MAPPING = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None))


# ---- the cases -------------------------------------------------------------------------------------------------------

def ref_case(kind):
    """A replayed acknowledgement whose reference names a record that the restore point keeps."""
    b = H.HB()
    if kind == "applied_ref":
        b.apply(D[1], 27.0)
        b.restart(D[1], "review-source-r")
        extra = P.obs("review-extra", D[1], 41.0, hour=21)
        b.ack("ADDED", D[1], [H.fp(extra)], "review-source-q", applied=1)
    else:
        b.apply(D[3], 27.0)
        b.restart(D[3], "review-source-r")
        extra = P.obs("review-late", D[1], 21.0)
        b.ack("LATE", D[1], [H.fp(extra)], "review-source-q", missing=("APPLY", 1))
    b.w.ledger.append(extra)
    return b, R.prep(b, 1, {2: "DROP", 3: "REPLAY"}, D[5], "review-r1")


def calendar_added(with_restart, with_decision):
    """The current sessions have a day (D1) that the saved APPLY of D3 passed over without it."""
    b = H.HB()
    full = b.w.sessions
    b.w.sessions = R.sessions_with(dates=[d for d in D if d != D[1]])
    b.apply(D[3], 27.0)
    if with_restart:
        b.restart(D[3], "review-old-r")
    V.validate_history(b.history())
    b.w.sessions = full
    if with_decision:
        b.w.ledger.append(P.obs("review-new-session", D[1], 26.0))
    mapping = {1: "REAPPLY"}
    if with_restart:
        mapping[2] = "DROP"
    return b, mapping


def prepare_added(with_restart=True, with_decision=True):
    b, mapping = calendar_added(with_restart, with_decision)
    return b, R.prep(b, 0, mapping, D[5], "review-calendar")


def frontier_case():
    """Two declarations; the current sessions have no D1 any more, so the replayed declaration of D2 has a new frontier."""
    b = H.HB()
    b.declare(D[1], "review-declare-1")
    b.declare(D[2], "review-declare-2")
    V.validate_history(b.history())
    b.w.sessions = R.sessions_with(dates=[d for d in D if d != D[1]])
    return b, R.prep(b, 0, {1: "DROP", 2: "REPLAY"}, D[4], "review-frontier")


# ---- R-01 ------------------------------------------------------------------------------------------------------------

class R01ListedDifferences(unittest.TestCase):
    """A reference that still names the same record is not a change; one that follows a re-applied day is."""

    def final_difference(self, b, plan, names):
        change = next(c for c in plan.basis["changes"] if c["op"] == "REPLAY")
        result = R.confirm(plan, b.history(), b.w)
        old, new = b.events[change["from_seq"]], result.history.events[change["to_seq"]]
        return change, sorted(k for k in names if R.cj(old[k]) != R.cj(new[k])), old, new

    def test_kept_applied_ref_is_not_listed(self):
        b, plan = ref_case("applied_ref")
        change, actual, old, new = self.final_difference(b, plan, ("applied_ref", "missing_ref", "state_after"))
        self.assertEqual(old["applied_ref"], new["applied_ref"])
        self.assertEqual(change["changed_fields"], ["state_after"])
        self.assertEqual(change["changed_fields"], actual)

    def test_kept_missing_ref_is_not_listed(self):
        b, plan = ref_case("missing_ref")
        change, actual, old, new = self.final_difference(b, plan, ("applied_ref", "missing_ref", "state_after"))
        self.assertEqual(old["missing_ref"], new["missing_ref"])
        self.assertEqual(change["changed_fields"], ["state_after"])
        self.assertEqual(change["changed_fields"], actual)

    def test_ref_to_a_reapplied_day_is_listed(self):
        b = R.ex_ack_between()
        plan = R.prep(b, 1, MAPPING, D[5], "r4-1")
        change, actual, old, new = self.final_difference(b, plan, ("applied_ref", "missing_ref", "state_after"))
        self.assertNotEqual(old["applied_ref"]["seq"], new["applied_ref"]["seq"])
        self.assertNotEqual(old["applied_ref"]["event_hash"], new["applied_ref"]["event_hash"])
        self.assertEqual(change["changed_fields"], ["applied_ref", "state_after"])
        self.assertEqual(change["changed_fields"], actual)

    def test_every_replayed_acknowledgement_is_listed_as_it_really_differs(self):
        for kind in ("applied_ref", "missing_ref"):
            b, plan = ref_case(kind)
            for change in plan.basis["changes"]:
                if change["op"] != "REPLAY":
                    continue
                result = R.confirm(plan, b.history(), b.w)
                old, new = b.events[change["from_seq"]], result.history.events[change["to_seq"]]
                names = ("applied_ref", "missing_ref", "state_after") if old["kind"] == "ACK" else ()
                self.assertEqual(change["changed_fields"], sorted(k for k in names if R.cj(old[k]) != R.cj(new[k])))

    def test_the_candidate_is_the_independent_one_and_has_the_digests_of_before_the_fix(self):
        """Only the listed names change: the candidate events and digests are those the independent builder writes, and
        those the version before the fix wrote for the same inputs (fixed values)."""
        cases = {"applied_ref": ref_case("applied_ref"), "missing_ref": ref_case("missing_ref")}
        b = R.ex_ack_between()
        cases["mapped"] = (b, R.prep(b, 1, MAPPING, D[5], "r4-1"))
        for name, (b, plan) in sorted(cases.items()):
            if name == "mapped":
                mapping, rid, check = MAPPING, "r4-1", D[5]
            else:
                mapping, rid, check = {2: "DROP", 3: "REPLAY"}, "review-r1", D[5]
            cand = plan.basis["candidate_history"]
            self.assertEqual(R.cj(cand["events"][len(b.events):]), R.cj(R.oracle(b, 1, mapping, rid, check)[len(b.events):]))
            self.assertEqual(plan.basis["candidate_digest"], BEFORE_THE_FIX[name], name)


# digests of the candidate Histories that the version before the fix (5eede11) built for the three cases above
BEFORE_THE_FIX = {
    "applied_ref": "79fec80154f21c9470b7238d8b4e5f7637ee620ee89c7474eb773ed2d083cd6e",
    "missing_ref": "eda9b04e5475a4295c835e7e4ea2536b3a3f0a559459c08e63f59e87f65c5cba",
    "mapped": "cfa1d1e3ff39eec7837a1d84005aa5b379aef69d12c9249f1e6f156bf106f917"}


# ---- R-02 ------------------------------------------------------------------------------------------------------------

class R02PlanFormBeforeInputs(unittest.TestCase):
    """A plan whose own form is wrong is refused as history_plan_mismatch / plan, in confirmation A and in the
    re-confirmation B, whatever the current inputs are (here: sessions=None); a correct plan keeps the input errors."""

    @classmethod
    def setUpClass(cls):
        cls.b = R.ex_restart_between()
        cls.h, cls.w = cls.b.history(), cls.b.w
        cls.plan = R.prep(cls.b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "review-shape")
        cls.done = R.confirm(cls.plan, cls.h, cls.w)

    def both(self, bad, sessions="current"):
        """The answer of confirmation A (the original) and B (the plan's own candidate); sessions=None passes no sessions."""
        out = {}
        for branch, current in (("A", self.h), ("B", self.done.history)):
            out[branch] = err(Z.confirm_restore_plan, bad, bad.plan_hash, current,
                              self.w.sessions if sessions == "current" else sessions, self.w.ledger, self.w.series)
        return out

    def test_the_plan_itself_is_confirmed_in_both_branches(self):
        self.assertEqual(self.done.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(R.confirm(self.plan, self.done.history, self.w).status, "NO_CHANGE")

    def test_bad_changes_rows_with_missing_sessions(self):
        for replacement in ([{}], [{"op": []}], [{"op": "REAPPLY", "from_seq": True}]):
            bad = R.refreshed(self.plan, lambda bs, v=replacement: bs.__setitem__("changes", v))
            for sessions in ("current", None):                 # valid inputs and missing sessions: the same answer
                got = self.both(bad, sessions)
                self.assertEqual(got["A"], ("history_plan_mismatch", "plan", None), (replacement, sessions))
                self.assertEqual(got["B"], ("history_plan_mismatch", "plan", None), (replacement, sessions))

    def test_other_bad_changes_rows(self):
        base = self.plan.basis["changes"]
        edits = [
            lambda c: c[0].__setitem__("from_seq", -1),
            lambda c: c[0].__setitem__("to_seq", -2),
            lambda c: c[0].__setitem__("to_seq", True),
            lambda c: c[0].__setitem__("d", "2026-13-40"),
            lambda c: c[0].__setitem__("kind", "NOPE"),
            lambda c: c[0].__setitem__("same_as_superseded", "yes"),
            lambda c: c[0].__setitem__("changed_fields", ["not_a_field"]),
            lambda c: c[0].__setitem__("changed_fields", "state_after"),
            lambda c: c[0].pop("op"),
            lambda c: c.append(dict(c[0], extra=1)),
        ]
        for i, edit in enumerate(edits):
            bad = R.refreshed(self.plan, lambda bs, e=edit: e(bs["changes"]))
            got = self.both(bad, sessions=None)
            self.assertEqual(got["A"], ("history_plan_mismatch", "plan", None), i)
            self.assertEqual(got["B"], ("history_plan_mismatch", "plan", None), i)
        self.assertEqual(self.plan.basis["changes"], base)

    def test_negative_or_wrong_from_seq_of_an_op(self):
        edits = [
            lambda bs: bs["ops"][-1].__setitem__("from_seq", -1),
            lambda bs: bs["ops"][0].__setitem__("from_seq", -1),                # a DROP, not a REAPPLY
            lambda bs: bs["ops"][-1].__setitem__("from_seq", 10 ** 6),          # beyond the original head
            lambda bs: bs["ops"][-1].__setitem__("from_seq", 2),                # a record that is not an APPLY
            lambda bs: bs["ops"][-1].__setitem__("from_seq", True),
            lambda bs: bs["ops"][-1].__setitem__("from_seq", 3.0),
        ]
        for i, edit in enumerate(edits):
            bad = R.refreshed(self.plan, edit)
            got = self.both(bad, sessions=None)
            self.assertEqual(got["A"], ("history_plan_mismatch", "plan", None), i)
            self.assertEqual(got["B"], ("history_plan_mismatch", "plan", None), i)

    def test_a_negative_restore_point_is_the_plans_own_error(self):
        bad = R.refreshed(self.plan, lambda bs: bs["restore_point"].__setitem__("seq", -1))
        self.assertEqual(self.both(bad, sessions=None)["A"], ("history_plan_mismatch", "plan", None))

    def test_bad_series_inputs_with_missing_sessions(self):
        self.assertTrue(self.plan.basis["series_inputs"])
        edits = [
            lambda s: s.__setitem__(0, 1),
            lambda s: s.__setitem__(0, {}),
            lambda s: s[0].__setitem__("row", None),
            lambda s: s[0].__setitem__("row", dict(s[0]["row"], soxx=True)),
            lambda s: s[0].__setitem__("d", "x"),
            lambda s: s[0].__setitem__("from_seq", -1),
            lambda s: s[0].__setitem__("prev_row", {"date": "2026-03-02"}),
        ]
        for i, edit in enumerate(edits):
            bad = R.refreshed(self.plan, lambda bs, e=edit: e(bs["series_inputs"]))
            got = self.both(bad, sessions=None)
            self.assertEqual(got["A"], ("history_plan_mismatch", "plan", None), i)
            self.assertEqual(got["B"], ("history_plan_mismatch", "plan", None), i)

    def test_a_correct_plan_keeps_the_error_of_the_bad_input(self):
        for branch, current in (("A", self.h), ("B", self.done.history)):
            self.assertEqual(err(Z.confirm_restore_plan, self.plan, self.plan.plan_hash, current, None, self.w.ledger,
                                 self.w.series)[:2], ("sessions_invalid", "sessions"), branch)
            self.assertEqual(err(Z.confirm_restore_plan, self.plan, self.plan.plan_hash, current, self.w.sessions,
                                 [{"bad": 1}], self.w.series)[0], "record_id_invalid", branch)

    def test_no_plan_value_is_shown_for_a_bad_plan(self):
        bad = R.refreshed(self.plan, lambda bs: bs.__setitem__("changes", [{"op": "SECRET-VALUE"}]))
        e = R.refusal(Z.confirm_restore_plan, bad, bad.plan_hash, self.h, None, self.w.ledger, self.w.series)
        self.assertNotIn("SECRET-VALUE", repr(e) + str(getattr(e, "detail", "")))


# ---- R-03 ------------------------------------------------------------------------------------------------------------

class R03CounterExamples(unittest.TestCase):
    """The four single deletions that were once called equivalent each have a input that separates them."""

    def test_m09c_a_newly_skipped_day_with_a_decision_needs_a_consume(self):
        b, mapping = calendar_added(True, True)
        self.assertEqual(err(R.prep, b, 0, mapping, D[5], "review-calendar"), ("restore_requires_consume", "ops", None))

    def test_m09c_without_the_decision_the_same_plan_is_ready(self):
        b, mapping = calendar_added(True, False)
        plan = R.prep(b, 0, mapping, D[5], "review-calendar")
        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.basis["candidate_records"][-1]["skipped_sessions"], [D[1], D[2]])

    def test_m12b_a_replayed_declaration_gets_the_new_frontier(self):
        b, plan = frontier_case()
        self.assertEqual(plan.status, "READY")
        last = plan.basis["candidate_records"][-1]
        self.assertEqual((last["kind"], last["d"], last["frontier_before"]), ("DECLARE_MISSING", D[2], D[0]))
        self.assertNotEqual(last["frontier_before"], b.events[2]["frontier_before"])
        result = R.confirm(plan, b.history(), b.w)
        self.assertEqual(result.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(R.confirm(plan, result.history, b.w).status, "NO_CHANGE")

    def test_m16d_the_tail_of_the_plans_candidate_is_compared_before_any_input(self):
        b, plan = prepare_added(False, False)
        bad = R.refreshed(plan, lambda bs: bs.__setitem__("candidate_records", [{}]))
        self.assertEqual(err(Z.confirm_restore_plan, bad, bad.plan_hash, b.history(), None, b.w.ledger, b.w.series),
                         ("history_plan_mismatch", "plan", None))

    def test_m16d_the_same_on_the_main_example(self):
        b = R.ex_restart_between()
        plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "review-shape")
        bad = R.refreshed(plan, lambda bs: bs.__setitem__("candidate_records", [{}]))
        self.assertEqual(err(Z.confirm_restore_plan, bad, bad.plan_hash, b.history(), None, b.w.ledger, b.w.series),
                         ("history_plan_mismatch", "plan", None))

    def test_m17c_a_plan_without_a_drop_that_changes_something_is_ready(self):
        b, plan = prepare_added(False, False)
        changes = plan.basis["changes"]
        self.assertFalse(any(c["op"] == "DROP" for c in changes))
        self.assertIs(changes[0]["same_as_superseded"], False)
        self.assertEqual(changes[0]["changed_fields"], ["input_hash", "skipped_sessions"])
        self.assertEqual(plan.basis["candidate_records"][-1]["skipped_sessions"], [D[1], D[2]])
        result = R.confirm(plan, b.history(), b.w)
        self.assertEqual(result.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(R.confirm(plan, result.history, b.w).status, "NO_CHANGE")

    def test_m17c_a_plan_without_a_drop_that_changes_nothing_is_still_refused(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.assertEqual(err(R.prep, b, 0, {1: "REAPPLY"}, D[3], "r4-1"), ("restore_no_effect", "ops", None))

    def test_the_no_effect_rule_is_the_exact_condition(self):
        """No DROP and every re-applied day the same: refused. Anything else is not."""
        b, plan = prepare_added(False, False)
        self.assertEqual(plan.status, "READY")                 # no DROP, one REAPPLY that is not the same
        b2 = R.ex_restart_between()
        self.assertEqual(R.prep(b2, 1, {2: "DROP", 3: "REAPPLY"}, D[3], "r4-1").status, "READY")   # a DROP


if __name__ == "__main__":
    unittest.main()
