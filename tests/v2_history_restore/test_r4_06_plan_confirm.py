"""B4-15 (the plan, its hash and the differences), B4-16 (confirmation A and B, stale and mismatch) and B4-17 (the series range)."""
import unittest
from unittest import mock

import r4_helpers as R

T, H, Z, D, P, V, O = R.T, R.H, R.Z, R.D, R.P, R.V, R.O
import v2_history_restore.build as build  # noqa: E402
from v2_history_restore.values import BASIS_KEYS  # noqa: E402


def err(fn, *args, **kwargs):
    e = R.refusal(fn, *args, **kwargs)
    return (e.code, e.field, getattr(e, "rule", None), e.detail)


MAPPING = {2: "DROP", 3: "REAPPLY", 4: "REPLAY", 5: "REAPPLY"}


def mutate(value):
    """Another value of the same kind for any basis item."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value[:-1] + ("0" if value[-1:] != "0" else "1")
    if isinstance(value, int):
        return value + 1
    if isinstance(value, list):
        return value[:-1] if value else [None]
    if isinstance(value, dict):
        return dict(value, extra_key=1)
    return "x"


class PlanContent(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_ack_between()
        self.plan = R.prep(self.b, 1, MAPPING, D[5], "r4-1")
        self.basis = self.plan.basis

    def test_the_basis_has_its_twenty_three_items_and_the_hash_covers_them(self):
        self.assertEqual(len(BASIS_KEYS), 23)
        self.assertEqual(set(self.basis), set(BASIS_KEYS))
        self.assertEqual(self.plan.plan_hash, H.sha(R.cj(self.basis)))
        self.assertEqual(self.plan.status, "READY")
        self.assertIs(self.plan.committed, False)

    def test_the_items_are_the_values_of_the_inputs(self):
        basis, check = self.basis, V.validate_history(self.b.history())
        self.assertEqual((basis["expected_head_seq"], basis["expected_head_hash"]), (check.head_seq, check.head_hash))
        self.assertEqual(basis["history_digest"], self.b.history().digest)
        self.assertEqual(basis["expected_state_digest"], check.state_digest)
        self.assertEqual(basis["restore_point"], R.point(self.b, 1))
        self.assertEqual(basis["ops"], R.ops_of(self.b, 1, MAPPING))
        self.assertEqual((basis["check_d"], basis["request_id"], basis["requested_at"]), (D[5], "r4-1", R.WHEN_TEXT))
        self.assertEqual(basis["ledger_digest"], R.ledger_digest(R.parse_ledger(self.b.w.ledger)))
        self.assertEqual(basis["candidate_records"], basis["candidate_history"]["events"][-4:])
        self.assertEqual(basis["candidate_records"][0]["kind"], "RECOVERY_RESTORE")
        self.assertEqual(basis["candidate_records"][0]["request_hash"], basis["request_hash"])

    def test_the_series_inputs_are_the_normalized_rows_of_the_reapplied_days_only(self):
        items = self.basis["series_inputs"]
        self.assertEqual([(i["from_seq"], i["d"]) for i in items], [(3, D[2]), (5, D[3])])
        first = items[0]
        self.assertEqual(sorted(first), sorted(["from_seq", "d", "prev_session_date", "series_previous_date", "row", "prev_row"]))
        self.assertEqual(first["row"], {"date": D[2], "soxx": 110.0, "sma": 100.0, "rsi": 50.0, "shd": -1.0, "prev_rsi": 49.0})
        self.assertEqual(first["prev_session_date"], D[1])
        self.assertEqual(self.basis["series_digest"], H.sha(R.cj(items)))

    def test_the_changes_name_every_operation_with_its_real_values(self):
        changes = self.basis["changes"]
        self.assertEqual([(c["op"], c["from_seq"], c["kind"], c["d"], c["to_seq"]) for c in changes],
                         [("DROP", 2, "RESTART_UNKNOWN", D[1], None), ("REAPPLY", 3, "APPLY", D[2], 7),
                          ("REPLAY", 4, "ACK", D[2], 8), ("REAPPLY", 5, "APPLY", D[3], 9)])
        self.assertEqual([c["same_as_superseded"] for c in changes], [None, False, None, True])
        self.assertEqual(changes[3]["changed_fields"], [])
        self.assertEqual(changes[1]["changed_fields"], ["state_after", "transition_result"])
        self.assertEqual(changes[2]["changed_fields"], ["applied_ref", "state_after"])
        # the flags come from the compared values: a same-input REAPPLY on an unchanged base is true
        b = R.ex_restart_between()
        plan = R.prep(b, 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, D[3], "r4-1")
        self.assertEqual([(c["op"], c["same_as_superseded"], c["changed_fields"]) for c in plan.basis["changes"]],
                         [("REAPPLY", True, []), ("DROP", None, []), ("REAPPLY", False, ["state_after", "transition_result"])])

    def test_every_item_is_bound_by_the_hash_and_by_the_rebuild(self):
        history = self.b.history()
        for key in sorted(BASIS_KEYS):
            with self.subTest(key):
                # not fixed up: the hash does not match
                broken = R.with_plan_dict(self.plan, lambda d, key=key: d["basis"].__setitem__(key, mutate(d["basis"][key])))
                self.assertEqual(err(R.confirm, broken, history, self.b.w)[:2], ("history_plan_mismatch", "plan"))
                # fixed up: only the rebuild from the real inputs can tell
                fixed = R.refreshed(self.plan, lambda basis, key=key: basis.__setitem__(key, mutate(basis[key])))
                e = R.refusal(R.confirm, fixed, history, self.b.w)
                self.assertIn(e.code, ("history_plan_mismatch", "history_plan_stale"))

    def test_a_confirmation_hash_that_is_not_the_plans_is_refused(self):
        history = self.b.history()
        for wrong in (H.sha("x"), "0" * 64, "", 5, [self.plan.plan_hash]):
            with self.subTest(wrong=wrong):
                self.assertEqual(err(R.confirm, self.plan, history, self.b.w, plan_hash=wrong)[:2], ("history_plan_mismatch", "plan"))

    def test_another_time_changes_the_plan_and_only_the_plan(self):
        later = R.WHEN.replace(hour=R.WHEN.hour + 1)
        other = R.prep(self.b, 1, MAPPING, D[5], "r4-1", when=later)
        a, c = self.basis, other.basis
        differing = sorted(k for k in a if R.cj(a[k]) != R.cj(c[k]))
        self.assertEqual(a["request_hash"], c["request_hash"])
        self.assertNotEqual(self.plan.plan_hash, other.plan_hash)
        self.assertIn("requested_at", differing)
        self.assertNotIn("request_hash", differing)


class Confirmation(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_ack_between()
        self.plan = R.prep(self.b, 1, MAPPING, D[5], "r4-1")

    def test_a_confirmation_against_the_original_gives_the_candidate_in_memory_only(self):
        history = self.b.history()
        before = R.cj(history.to_dict())
        res = R.confirm(self.plan, history, self.b.w)
        self.assertEqual((res.status, res.committed, res.committable), ("CONFIRMED_IN_MEMORY", False, False))
        self.assertEqual(res.plan_hash, self.plan.plan_hash)
        self.assertEqual(res.history.digest, self.plan.basis["candidate_digest"])
        self.assertEqual(R.cj(res.history.events), R.cj(R.oracle(self.b, 1, MAPPING, "r4-1", D[5])))
        self.assertEqual(R.cj(history.to_dict()), before)                       # the original is not touched
        self.assertEqual(len(history.events), len(self.b.events))

    def test_a_confirmation_against_its_own_candidate_changes_nothing_and_adds_nothing(self):
        res = R.confirm(self.plan, self.b.history(), self.b.w)
        again = R.confirm(self.plan, res.history, self.b.w)
        self.assertEqual(again.status, "NO_CHANGE")
        self.assertEqual(again.history.digest, res.history.digest)
        self.assertEqual(len(again.history.events), len(res.history.events))        # no second RECOVERY_RESTORE
        self.assertEqual([e["kind"] for e in again.history.events].count("RECOVERY_RESTORE"), 1)
        self.assertEqual((again.committed, again.committable), (False, False))

    def test_every_confirmation_rebuilds_the_whole_basis_and_checks_the_original_prefix(self):
        with mock.patch("v2_history_restore.confirm.build_restore", wraps=build.build_restore) as spy:
            R.confirm(self.plan, self.b.history(), self.b.w)
        self.assertEqual(spy.call_count, 1)
        res = R.confirm(self.plan, self.b.history(), self.b.w)
        with mock.patch("v2_history_restore.confirm.build_restore", wraps=build.build_restore) as spy:
            R.confirm(self.plan, res.history, self.b.w)
        self.assertEqual(spy.call_count, 1)                                          # branch B rebuilds from the plan's own prefix
        self.assertEqual(len(spy.call_args[0][0].events), len(self.b.events))

        def change_the_prefix(events, n):
            events[1]["state_after"] = R.deep(events[2]["state_after"])             # inside the original part of the candidate

        forged = R.forge(self.plan, change_the_prefix)
        self.assertEqual(err(R.confirm, forged, self.b.history(), self.b.w)[:2], ("history_plan_mismatch", "plan"))

    def test_a_history_that_moved_on_or_another_candidate_is_stale(self):
        b = R.ex_restart_between()
        mapping = {2: "DROP", 3: "REAPPLY"}
        w = b.w
        # the row of D3 is already in the ledger the plan is made with, so only the history differs afterwards
        ledger = w.ledger + [P.obs("R-" + D[3], D[3], 30.0)]
        plan = R.prep(b, 1, mapping, D[4], "r4-1", ledger=ledger)
        moved = R.ex_restart_between()
        moved.apply(D[3], 30.0, "R-" + D[3])
        self.assertEqual(R.cj(moved.w.ledger), R.cj(ledger))
        self.assertEqual(err(R.confirm, plan, moved.history(), b.w, ledger=ledger)[:2], ("history_plan_stale", "plan"))
        other_plan = R.prep(b, 0, {1: "REAPPLY", 2: "DROP", 3: "REAPPLY"}, D[4], "r4-9", ledger=ledger)
        other = R.confirm(other_plan, b.history(), b.w, ledger=ledger).history          # another restore of the same history
        self.assertEqual(err(R.confirm, plan, other, b.w, ledger=ledger)[:2], ("history_plan_stale", "plan"))

    def test_a_normal_change_of_the_inputs_is_stale(self):
        history = self.b.history()
        ledger = self.b.w.ledger + [P.obs("X6", D[6], 45.0)]
        self.assertEqual(err(R.confirm, self.plan, history, self.b.w, ledger=ledger)[:2], ("history_plan_stale", "plan"))
        sessions = R.sessions_with({D[6]: R.earlier_close})
        self.assertEqual(err(R.confirm, self.plan, history, self.b.w, sessions=sessions)[:2], ("history_plan_stale", "plan"))

    def test_a_difference_found_only_by_the_rebuild_after_the_digests_match_is_a_mismatch(self):
        def change_the_new_state(events, n):
            events[n + 1]["state_after"] = R.deep(self.b.events[3]["state_after"])      # the first new APPLY keeps the old state

        forged = R.forge(self.plan, change_the_new_state)
        self.assertEqual(err(R.confirm, forged, self.b.history(), self.b.w)[:2], ("history_plan_mismatch", "plan"))
        # the inputs of a plan are what it was built from; the history it was built from is not enough for another plan
        wrong_ops = R.refreshed(self.plan, lambda basis: basis["ops"][0].update(op="REPLAY"))
        self.assertEqual(err(R.confirm, wrong_ops, self.b.history(), self.b.w)[:2], ("history_plan_mismatch", "plan"))

    def test_a_confirmation_does_not_store_or_change_anything(self):
        history = self.b.history()
        plan_before = R.cj(self.plan.to_dict())
        ledger_before, sessions_before = R.deep(self.b.w.ledger), R.sessions_with()
        R.confirm(self.plan, history, self.b.w)
        self.assertEqual(R.cj(self.plan.to_dict()), plan_before)
        self.assertEqual(R.cj(self.b.w.ledger), R.cj(ledger_before))


class StrictSeries(object):
    """A series that records what it is asked for and refuses any row after the date it was cut at."""

    def __init__(self, base, log, cut=None, soxl=None, description=None):
        self.base, self.log, self.cut = base, log, cut
        self.soxl, self.desc = soxl, description

    def through(self, d):
        self.log.append(("through", d))
        return StrictSeries(self.base.through(d), self.log, d, self.soxl, self.desc)

    def previous_date(self, d):
        self.log.append(("previous_date", d))
        return self.base.previous_date(d)

    def row(self, d):
        self.log.append(("row", d))
        if self.cut is not None and d > self.cut:
            raise AssertionError("a row after the cut was asked for: %s > %s" % (d, self.cut))
        return self.base.row(d)

    def soxl_close(self, d):
        return self.soxl

    def description(self):
        return self.desc if self.desc is not None else self.base.description()


class SeriesRange(unittest.TestCase):
    def setUp(self):
        self.b = R.ex_ack_between()

    def test_nothing_after_the_cut_day_is_read(self):
        log = []
        series = StrictSeries(self.b.w.series, log)
        plan = R.prep(self.b, 1, MAPPING, D[5], "r4-1", series=series)
        self.assertEqual(plan.status, "READY")
        rows = [d for kind, d in log if kind == "row"]
        self.assertTrue(rows)
        self.assertEqual(sorted(set(d for kind, d in log if kind == "through")), [D[2], D[3]])
        self.assertEqual(max(rows), D[3])                                            # the re-applied days only

    def test_other_values_after_the_day_a_display_value_and_a_description_do_not_change_the_digest(self):
        base = R.prep(self.b, 1, MAPPING, D[5], "r4-1")
        future = R.with_row(self.b.w, D[5], soxx=999.0, rsi=10.0)                      # after every re-applied day
        for name, series in (
                ("later row", future),
                ("display value", StrictSeries(self.b.w.series, [], soxl=12.345)),
                ("description", StrictSeries(self.b.w.series, [], description={"rows": 1})),
                ("another shape of the meta", StrictSeries(self.b.w.series, [], description={"price_definition": "x"}))):
            with self.subTest(name):
                plan = R.prep(self.b, 1, MAPPING, D[5], "r4-1", series=series)
                self.assertEqual(plan.basis["series_digest"], base.basis["series_digest"])
                self.assertEqual(plan.plan_hash, base.plan_hash)

    def test_a_revised_history_that_changes_the_row_of_a_reapplied_day_stops(self):
        for d in (D[2], D[3]):
            series = R.with_row(self.b.w, d, rsi=61.0)
            self.assertEqual(err(R.prep, self.b, 1, MAPPING, D[5], "r4-1", series=series)[:2],
                             ("restore_market_input_changed", "series"))
        # a revision of the day before the previous one that changes prev_row of the first day does too
        series = R.with_row(self.b.w, D[1], rsi=61.0)
        self.assertEqual(err(R.prep, self.b, 1, MAPPING, D[5], "r4-1", series=series)[:2],
                         ("restore_market_input_changed", "series"))

    def test_no_reapplied_day_means_the_series_is_never_asked_for(self):
        b = R.ex_restart_tail()

        class Refuses(object):
            def __getattr__(self, name):
                raise AssertionError("the series was used: %s" % name)

        plan = R.prep(b, 1, {2: "DROP"}, D[5], "r4-1", series=Refuses())
        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.basis["series_inputs"], [])
        self.assertEqual(plan.basis["series_digest"], H.sha(R.cj([])))
        res = R.confirm(plan, b.history(), b.w, series=Refuses())
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")

    def test_a_series_that_does_not_answer_in_the_expected_form_is_a_fixed_error(self):
        class Broken(object):
            def through(self, d):
                return self

            def row(self, d):
                return object()

            def previous_date(self, d):
                return D[0]

        e = R.refusal(R.prep, self.b, 1, MAPPING, D[5], "r4-1", series=Broken())
        self.assertEqual((e.code, e.field, e.rule), ("restore_invalid", "series", "market_input"))


if __name__ == "__main__":
    unittest.main()
