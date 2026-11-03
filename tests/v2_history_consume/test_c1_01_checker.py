"""C1-02 (the form of the records) and C1-03 (the rules of the checker v2_history.restore for CONSUME).

Histories are written with the independent builder (c1_helpers.oracle, which does not check anything) and then changed;
the checker is v2_history.validate_history. The place of each rule is the table of design 3.3."""
import unittest

import c1_helpers as C

H, V, D = C.H, C.V, C.D
CONSUME = C.CONSUME


def scenario_a():
    """0 GENESIS, 1 APPLY D1, 2 RESTART(D1), 3 APPLY D2, 4 DECLARE D3, 5 APPLY D4 and the restore at 3: DROP 4, CONSUME D3,
    REAPPLY 5."""
    b = C.s_declare()
    events = C.oracle(b, 3, [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)], "c1-1", D[5])
    return b, events, len(b.events)


class Form(unittest.TestCase):
    """C1-02: the records that a CONSUME makes have the form of design 3.2, and the keys are not increased."""

    def test_the_restore_record_and_the_created_apply_have_the_fixed_form(self):
        b, events, n = scenario_a()
        V.validate_history(H.history_of(events))
        rec = events[n]
        self.assertEqual(rec["replay"][1], {"op": "CONSUME", "from_seq": None, "d": D[3], "seq": n + 1,
                                            "same_as_superseded": None})
        self.assertEqual(rec["request_basis"]["ops"],
                         [{"op": "DROP", "from_seq": 4}, {"op": "CONSUME", "d": D[3]}, {"op": "REAPPLY", "from_seq": 5}])
        self.assertEqual(len(rec), 15)                                               # RECOVERY_RESTORE keeps its 15 keys
        for entry in rec["replay"]:
            self.assertEqual(sorted(entry), ["d", "from_seq", "op", "same_as_superseded", "seq"])
        made = events[n + 1]
        self.assertEqual((made["kind"], made["d"]), ("APPLY", D[3]))
        self.assertEqual(sorted(made), sorted(events[1]))                            # an APPLY has the same keys as any
        self.assertEqual(made["parent_seq"], n)

    def test_the_created_apply_follows_the_chain_in_the_order_of_the_ops(self):
        b, events, n = scenario_a()
        self.assertEqual([e["d"] for e in events[n + 1:]], [D[3], D[4]])
        self.assertEqual([e["parent_seq"] for e in events[n + 1:]], [n, n + 1])
        check = V.validate_history(H.history_of(events))
        self.assertEqual(list(check.effective_seqs), [0, 1, 2, 3, n, n + 1, n + 2])

    def test_a_valid_history_with_consume_is_accepted_after_a_round_trip(self):
        b, events, n = scenario_a()
        again = V.History.from_dict(H.history_of(events).to_dict())
        self.assertEqual(V.validate_history(again).head_seq, n + 2)


class EntryForm(unittest.TestCase):
    """The replay entry of a CONSUME and its ops entry."""

    def setUp(self):
        self.b, self.events, self.n = scenario_a()

    def rule(self, fn, mirror=True):
        return C.rule_of(self, C.edit(self.events, self.n, fn, mirror))

    def test_the_replay_entry_has_exactly_five_keys(self):
        def drop_key(r):
            del r["replay"][1]["same_as_superseded"]
        def add_key(r):
            r["replay"][1]["extra"] = 1
        self.assertEqual(self.rule(drop_key), "restore_replay_mismatch")
        self.assertEqual(self.rule(add_key), "restore_replay_mismatch")

    def test_from_seq_and_the_same_flag_are_null_and_the_day_is_a_day(self):
        for key, value in (("from_seq", 5), ("from_seq", 0), ("same_as_superseded", False), ("same_as_superseded", True)):
            with self.subTest(key=key, value=value):
                self.assertEqual(self.rule(lambda r, k=key, v=value: r["replay"][1].update({k: v})),
                                 "restore_replay_mismatch")
        for bad in (None, "", "2026-13-45", "2026-3-3", 20260303, ["2026-03-05"]):
            with self.subTest(day=bad):
                self.assertEqual(self.rule(lambda r, v=bad: r["replay"][1].update(d=v)), "restore_replay_mismatch")

    def test_the_ops_entry_is_the_op_and_the_day_of_the_replay_entry(self):
        def other_day(r):
            r["request_basis"]["ops"][1] = {"op": CONSUME, "d": D[4]}
        def with_from_seq(r):
            r["request_basis"]["ops"][1] = {"op": CONSUME, "d": D[3], "from_seq": None}
        def without_day(r):
            r["request_basis"]["ops"][1] = {"op": CONSUME}
        def as_drop(r):
            r["request_basis"]["ops"][1] = {"op": "DROP", "from_seq": 4}
        def not_a_dict(r):
            r["request_basis"]["ops"][1] = "CONSUME"
        for fn in (other_day, with_from_seq, without_day, as_drop, not_a_dict):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(self.rule(fn, mirror=False), "request_basis")

    def test_a_named_operation_written_as_a_consume_in_ops_only_is_refused(self):
        def fn(r):
            r["request_basis"]["ops"][0] = {"op": CONSUME, "d": D[3]}
        self.assertEqual(self.rule(fn, mirror=False), "request_basis")

    def test_ops_and_replay_have_the_same_length(self):
        def short_ops(r):
            r["request_basis"]["ops"].pop()
        def long_ops(r):
            r["request_basis"]["ops"].append({"op": CONSUME, "d": D[6]})
        for fn in (short_ops, long_ops):
            self.assertEqual(self.rule(fn, mirror=False), "restore_replay_mismatch")

    def test_the_lowercase_name_and_the_unknown_names_stay_what_they_were(self):
        # in the place of an operation that names a superseded record: refused as before (the kind does not allow it)
        for name in ("consume", "MERGE", ""):
            with self.subTest(name=name):
                self.assertEqual(self.rule(lambda r, v=name: r["replay"][0].update(op=v)), "restore_op_kind")
        # in the place of a CONSUME the entry is one more operation that names a record: the list no longer fits
        for name in ("consume", "MERGE"):
            with self.subTest(name=name, place="consume"):
                self.assertEqual(self.rule(lambda r, v=name: r["replay"][1].update(op=v)), "restore_replay_mismatch")


class Operations(unittest.TestCase):
    """The operations that name a superseded record are checked as before, with the CONSUME entries left out."""

    def setUp(self):
        self.b, self.events, self.n = scenario_a()

    def rule(self, fn, mirror=True):
        return C.rule_of(self, C.edit(self.events, self.n, fn, mirror))

    def test_the_named_list_must_be_the_superseded_list(self):
        def missing(r):
            del r["replay"][0]
        def swapped(r):
            r["replay"][0], r["replay"][2] = r["replay"][2], r["replay"][0]
        self.assertEqual(self.rule(missing), "restore_replay_mismatch")
        self.assertEqual(self.rule(swapped), "restore_op_kind")          # REAPPLY first: not allowed for a declaration

    def test_an_operation_that_the_kind_does_not_allow_is_refused(self):
        self.assertEqual(self.rule(lambda r: r["replay"][2].update(op="DROP")), "restore_op_kind")
        self.assertEqual(self.rule(lambda r: r["replay"][0].update(op="REAPPLY")), "restore_op_kind")

    def test_from_seq_is_the_superseded_record(self):
        self.assertEqual(self.rule(lambda r: r["replay"][0].update(from_seq=5)), "restore_replay_mismatch")


class Rules(unittest.TestCase):
    """Design 3.3: the three rules of place and day, and the created record."""

    def setUp(self):
        self.b, self.events, self.n = scenario_a()

    def rule(self, fn, mirror=True):
        return C.rule_of(self, C.edit(self.events, self.n, fn, mirror))

    def test_the_day_of_a_superseded_apply_is_refused(self):
        self.assertEqual(self.rule(lambda r: r["replay"][1].update(d=D[4])), "restore_consume_applied_day")

    def test_a_day_that_is_not_the_day_of_the_created_apply_is_refused(self):
        self.assertEqual(self.rule(lambda r: r["replay"][1].update(d=D[2])), "restore_replay_mismatch")

    def test_the_same_day_twice_is_refused(self):
        def fn(r):
            r["replay"].insert(2, {"op": CONSUME, "from_seq": None, "d": D[3], "seq": r["replay"][1]["seq"] + 1,
                                   "same_as_superseded": None})
        self.assertEqual(self.rule(fn), "restore_consume_duplicate")

    def test_the_seq_of_the_created_record_is_the_next_one(self):
        self.assertEqual(self.rule(lambda r: r["replay"][1].update(seq=r["replay"][1]["seq"] + 1)),
                         "restore_replay_mismatch")
        self.assertEqual(self.rule(lambda r: r["replay"][1].update(seq=None)), "restore_replay_mismatch")

    def test_the_created_record_is_an_apply(self):
        # a well-formed record of another kind (the restart of seq 2, written again in place of the created APPLY)
        def fn(events):
            events[self.n + 1] = C.deep(events[2])
            events[self.n + 1].update(seq=self.n + 1, parent_seq=self.n)
        history = H.mutated(self.events, fn)
        self.assertEqual(C.rule_of(self, history), "restore_incomplete")

    def test_a_history_that_ends_inside_the_batch_is_incomplete(self):
        history = H.history_of(self.events[:self.n + 1])
        self.assertEqual(C.rule_of(self, history), "restore_incomplete")
        history = H.history_of(self.events[:self.n + 2])
        self.assertEqual(C.rule_of(self, history), "restore_incomplete")

    def test_the_created_apply_is_checked_by_the_ordinary_rules(self):
        tamper = {
            "state": (lambda e: e.update(state_after=dict(e["state_after"], streak=99)), "s1:"),
            "transition": (lambda e: e["transition_result"].update(gap=0.5), "s1:"),
            "input_hash": (lambda e: e.update(input_hash="0" * 64), "s1:input_hash"),
            "skipped": (lambda e: e.update(skipped_sessions=[D[2]]), "s1:skipped_sessions"),
        }
        for name, (fn, expected) in tamper.items():
            with self.subTest(name):
                def edit(events, f=fn):
                    f(events[self.n + 1])
                rule = C.rule_of(self, H.mutated(self.events, edit))
                self.assertTrue(rule.startswith(expected), rule)

    def test_a_day_that_a_kept_declaration_names_cannot_be_applied(self):
        # REPLAY the declaration of D3 and consume D3 as well: the chain view refuses an APPLY on a declared day
        b = C.s_declare()
        events = C.oracle(b, 3, [("REPLAY", 4), (CONSUME, D[3]), ("REAPPLY", 5)], "c1-1", D[5])
        self.assertEqual(C.rule_of(self, H.history_of(events)), "declare_applied")


class Batches(unittest.TestCase):
    """A CONSUME does not stand between two operations on the records of one request (REPLAY or DROP alike)."""

    def history(self, entries):
        b = R_two_command()
        return b, H.history_of(C.oracle(b, 2, entries, "c1-1", D[5]))

    def test_between_two_records_of_one_request_it_is_refused(self):
        for op in ("DROP", "REPLAY"):
            with self.subTest(op=op):
                b, history = self.history([(op, 3), (CONSUME, D[3]), (op, 4), (op, 5)])
                self.assertEqual(C.rule_of(self, history), "restore_consume_in_batch")

    def test_mixed_operations_in_a_batch_are_still_a_partial_batch(self):
        b, history = self.history([("DROP", 3), (CONSUME, D[3]), ("REPLAY", 4), ("DROP", 5)])
        self.assertEqual(C.rule_of(self, history), "restore_partial_batch")      # the older rule is the first

    def test_before_the_batch_and_after_the_batch_it_is_accepted_by_the_form_rules(self):
        for entries in ([(CONSUME, D[3]), ("DROP", 3), ("DROP", 4), ("DROP", 5)],
                        [("DROP", 3), ("DROP", 4), (CONSUME, D[3]), ("DROP", 5)],
                        [("DROP", 3), ("DROP", 4), ("DROP", 5), (CONSUME, D[3])]):
            with self.subTest(entries=entries):
                b, history = self.history(entries)
                V.validate_history(history)

    def test_a_consume_between_two_requests_is_accepted(self):
        b = R_two_command()
        history = H.history_of(C.oracle(b, 2, [("DROP", 3), ("DROP", 4), (CONSUME, D[3]), ("DROP", 5)], "c1-1", D[5]))
        V.validate_history(history)


def R_two_command():
    """ex_two_command_request (0 GENESIS, 1 APPLY D1, 2 APPLY D2, 3-4 one request of two ACKs, 5 RESTART(D2)) with a
    decision of D3."""
    b = C.R.ex_two_command_request()
    b.w.ledger.append(C.P.obs("X3", D[3], 45.0))
    return b


if __name__ == "__main__":
    unittest.main()
