"""D5-07 header-only differences, D5-08 later damage, D5-09 batches and non-monotonic prefixes,
D5-10 NO_VALID_PREFIX and the migration examples."""
import unittest

import d5_helpers as X

HEAD_RULE = "head"


def no_discard(case, d, n):
    case.assertEqual(d["discarded"], {"from_index": n, "count": 0, "items": []})


class HeaderOnly(unittest.TestCase):
    def check(self, edit_name, data, rule, n):
        with X.Spy() as spy:
            d = X.diagnose(data)
        self.assertEqual(d["status"], "PREFIX_ONLY", edit_name)
        self.assertEqual(d["verified"]["count"], n)
        self.assertEqual(d["verified"]["head_seq"], n - 1)
        no_discard(self, d, n)
        self.assertEqual(d["failure"], {"stage": "validate", "code": "history_invalid", "field": "history", "rule": rule})
        self.assertEqual(spy.ks(2), [n, n], "the whole file, then k = n with the rebuilt header")
        self.assertEqual(spy.calls[0][2:], ("history_invalid", rule))
        self.assertEqual(spy.calls[1][2:], ("PASS", None))
        return d

    def test_each_header_difference(self):
        b = X.ex_new()
        n = len(b.events)
        state = X.deep(b.events[-1]["state_after"])
        state["streak"] = state["streak"] + 1
        cases = [("head_hash", X.file_of(b.events, head_hash=X.ZERO), "head"),
                 ("head_seq", X.file_of(b.events, head_seq=n + 5), "head"),
                 ("current_state", X.file_of(b.events, current_state=state), "current_state"),
                 ("extra header key", X.file_of(b.events, extra_key=1), "header_keys")]
        for name, data, rule in cases:
            self.assertEqual(X.full_error(data)[2], rule, "independent full-file result for " + name)
            d = self.check(name, data, rule, n)
            self.assertEqual(d["verified"]["head_hash"], b.events[-1]["event_hash"])

    def test_a_missing_header_key(self):
        b = X.ex_new()
        doc = X.H.header(X.deep(b.events))
        del doc["current_state"]
        d = self.check("missing", X.doc_bytes(doc), "header_keys", len(b.events))
        self.assertEqual(d["claimed"]["event_count"], len(b.events))

    def test_the_header_of_the_prefix_comes_from_its_own_last_record_not_the_file(self):
        b = X.ex_new()
        d = X.diagnose(X.file_of(X.with_hash(b.events, 4), head_hash=b.events[-1]["event_hash"], head_seq=6))
        self.assertEqual(d["verified"]["count"], 4)
        self.assertEqual(d["verified"]["head_seq"], 3)
        self.assertEqual(d["verified"]["head_hash"], b.events[3]["event_hash"])
        self.assertEqual(d["claimed"]["head_seq"], 6)

    def test_a_header_only_difference_in_a_history_with_batches(self):
        b = X.ex_r()
        self.check("batches", X.file_of(b.events, head_hash=X.ZERO), "head", len(b.events))


class LaterDamage(unittest.TestCase):
    def test_a_damaged_last_event_hash(self):
        b = X.ex_new()
        n = len(b.events)
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(X.with_hash(b.events, n - 1)))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], n - 1)
        self.assertEqual(d["verified"]["head_seq"], n - 2)
        self.assertEqual(d["discarded"]["from_index"], n - 1)
        self.assertEqual(d["discarded"]["count"], 1)
        self.assertEqual(d["discarded"]["items"], [{"index": n - 1, "kind": "APPLY", "seq": n - 1,
                                                    "d": b.events[-1]["d"], "request_id": None}])
        self.assertEqual(d["failure"]["rule"], "event_hash")
        self.assertEqual(spy.ks(2), [n, n, n - 1])

    def test_a_changed_value_in_the_middle_with_its_hash_left_alone(self):
        b = X.ex_new()
        n = len(b.events)
        pos = 3
        events = X.deep(b.events)
        events[pos]["d"] = "2030-01-01"
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(events))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], pos)
        self.assertEqual(d["discarded"]["from_index"], pos)
        self.assertEqual(d["discarded"]["count"], n - pos)
        items = d["discarded"]["items"]
        self.assertEqual([i["index"] for i in items], list(range(pos, n)))
        self.assertEqual([i["seq"] for i in items], list(range(pos, n)))
        self.assertEqual([i["kind"] for i in items], ["APPLY"] * (n - pos))
        self.assertEqual([i["d"] for i in items], ["2030-01-01"] + [e["d"] for e in b.events[pos + 1:]],
                         "the later, intact records are also on the discarded side")
        self.assertEqual(spy.ks(2), [n, n, n - 1, n - 2, n - 3, pos],
                         "searching down from n stops at the first k that passes; nothing below is tried")

    def test_the_search_does_not_continue_below_the_first_passing_k(self):
        b = X.ex_new()
        with X.Spy() as spy:
            X.diagnose(X.file_of(X.with_hash(b.events, len(b.events) - 1)))
        self.assertEqual(min(spy.ks()), len(b.events) - 1)
        self.assertEqual(spy.calls[-1][2], "PASS")

    def test_damage_after_a_restart(self):
        b = X.ex_u()
        d = X.diagnose(X.file_of(X.with_hash(b.events, 3)))
        self.assertEqual(d["verified"]["count"], 3)
        self.assertEqual(d["discarded"]["items"][0]["kind"], "RESTART_UNKNOWN")
        self.assertIsNone(d["discarded"]["items"][0]["d"], "resume_after is not shown")
        self.assertEqual(d["discarded"]["items"][0]["request_id"], "q1")


class Batches(unittest.TestCase):
    def test_a_restore_batch_cut_in_the_middle(self):
        b = X.H.example_r1()
        self.assertEqual(b.events[7]["kind"], "RECOVERY_RESTORE")
        events = X.deep(b.events)[:10]                 # restore at 7 and two of its three created records
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(events))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], 7, "the batch starts at index 7")
        self.assertEqual(d["discarded"]["from_index"], 7)
        self.assertEqual([i["kind"] for i in d["discarded"]["items"]], ["RECOVERY_RESTORE", "APPLY", "ACK"])
        for k in (10, 9, 8):
            self.assertIn(("history_invalid", "restore_incomplete"), spy.outcome(k), "k=%d must be refused" % k)
        self.assertEqual(spy.outcome(7), [("PASS", None)])
        self.assertEqual(d["failure"]["rule"], "restore_incomplete")

    def test_a_request_batch_cut_in_the_middle(self):
        b = X.R4.ex_two_command_request()
        self.assertEqual((b.events[3]["command_index"], b.events[3]["command_count"]), (0, 2))
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(b.events[:4]))      # the first of two commands of one request
        self.assertEqual(d["verified"]["count"], 3, "the request batch starts at index 3")
        self.assertEqual(d["discarded"], {"from_index": 3, "count": 1, "items": [
            {"index": 3, "kind": "ACK", "seq": 3, "d": b.events[3]["d"], "request_id": "q1"}]})
        self.assertEqual(spy.outcome(4)[-1], ("history_invalid", "batch"))
        self.assertEqual(spy.outcome(3), [("PASS", None)])

    def test_the_complete_batches_are_valid(self):
        self.assertEqual(X.diagnose(X.file_of(X.H.example_r1().events))["status"], "VALID")
        self.assertEqual(X.diagnose(X.file_of(X.R4.ex_two_command_request().events))["status"], "VALID")

    def test_prefix_validity_is_not_monotonic_and_the_longest_is_chosen(self):
        b = X.H.example_r1()
        b.apply(X.D[5], 33.0)                           # index 11, then its hash is damaged
        events = X.with_hash(b.events, 11)
        n = len(events)
        # independent facts about the input: 11 and 7 pass, the ones between do not
        passes = {}
        for k in range(1, n + 1):
            try:
                X.V.validate_history(X.V.History.from_dict(X.H.header(X.deep(b.events[:k]))))
                passes[k] = True
            except X.PersistenceError:
                passes[k] = False
        self.assertEqual([passes[k] for k in (11, 10, 9, 8, 7)], [True, False, False, False, True])
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(events))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], 11, "not 7 (a search from below that stops at the first failure)")
        self.assertEqual(d["discarded"]["count"], 1)
        self.assertEqual(spy.ks(2), [12, 12, 11])

    def test_a_batch_in_the_middle_of_a_longer_damaged_file(self):
        b = X.H.example_r1()
        for i in range(3):
            b.apply(X.D[5 + i], 33.0 + i)               # 11, 12, 13
        events = X.deep(b.events)
        events[12]["event_hash"] = X.ZERO               # damage after the batch
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["verified"]["count"], 12)

    def test_damage_inside_a_restore_batch_goes_back_to_before_the_batch(self):
        b = X.H.example_r1()
        events = X.with_hash(b.events, 9)
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["verified"]["count"], 7)
        self.assertEqual(d["discarded"]["count"], 4)

    def test_damage_inside_the_second_restore_of_example_r(self):
        b = X.ex_r()
        pos = [i for i, e in enumerate(b.events) if e["kind"] == "RECOVERY_RESTORE"]
        self.assertEqual(pos, [7, 14, 18])
        d = X.diagnose(X.file_of(X.with_hash(b.events, 16)))
        self.assertEqual(d["verified"]["count"], 14, "the batch of the restore at 14 is cut")
        self.assertEqual(d["verified"]["head_seq"], 13)


class NoValidPrefix(unittest.TestCase):
    def test_a_damaged_genesis(self):
        b = X.ex_new()
        n = len(b.events)
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(X.with_hash(b.events, 0)))
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertIsNone(d["verified"])
        self.assertEqual(d["discarded"]["from_index"], 0)
        self.assertEqual(d["discarded"]["count"], n)
        self.assertEqual([i["index"] for i in d["discarded"]["items"]], list(range(n)))
        self.assertEqual(d["discarded"]["items"][0], {"index": 0, "kind": "GENESIS", "seq": 0, "d": None,
                                                     "request_id": None})
        self.assertEqual(d["failure"]["stage"], "validate")
        self.assertEqual(d["schema_version"], 2)
        self.assertEqual(spy.ks(2), [n] + list(range(n, 0, -1)), "every k from n down to 1 is tried")

    def test_an_empty_list_of_events(self):
        with X.Spy() as spy:
            d = X.diagnose(X.doc_bytes(
                {"schema_version": 2, "core_sha": X.CORE_SHA, "head_seq": 0, "head_hash": X.ZERO,
                 "current_state": {}, "events": []}))
        self.assertEqual(len(spy.calls), 1)
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertIsNone(d["verified"])
        self.assertEqual(d["discarded"], {"from_index": 0, "count": 0, "items": []})
        self.assertEqual(d["claimed"]["event_count"], 0)
        self.assertEqual(d["failure"]["rule"], "events")

    def test_events_that_are_not_a_list(self):
        for value in ("text", {"a": 1}, None, 5, True):
            doc = {"schema_version": 2, "core_sha": X.CORE_SHA, "head_seq": 0, "head_hash": X.ZERO,
                   "current_state": {}, "events": value}
            with X.Spy() as spy:
                d = X.diagnose(X.doc_bytes(doc))
            self.assertEqual(d["status"], "NO_VALID_PREFIX", repr(value))
            self.assertIsNone(d["discarded"], repr(value))
            self.assertIsNone(d["verified"])
            self.assertEqual(len(spy.calls), 1, "only the whole-file check ran; there is no prefix to try")

    def test_a_missing_events_key(self):
        b = X.ex_new()
        doc = X.H.header(X.deep(b.events))
        del doc["events"]
        d = X.diagnose(X.doc_bytes(doc))
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertIsNone(d["discarded"])
        self.assertIsNone(d["claimed"]["event_count"])

    def test_every_record_damaged(self):
        b = X.ex_new()
        events = X.deep(b.events)
        for e in events:
            e["event_hash"] = X.ZERO
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertEqual(d["discarded"]["count"], len(events))

    def test_a_non_dict_first_element(self):
        b = X.ex_new()
        events = X.deep(b.events)
        events[0] = 5
        doc = {"schema_version": 2, "core_sha": X.CORE_SHA, "head_seq": 6, "head_hash": b.events[-1]["event_hash"],
               "current_state": {}, "events": events}
        d = X.diagnose(X.doc_bytes(doc))
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertEqual(d["discarded"]["items"][0], {"index": 0, "kind": "?", "seq": None, "d": None,
                                                     "request_id": None})


class MigrationExamples(unittest.TestCase):
    def test_a_damaged_migration_after_earlier_acknowledgements(self):
        b = X.ex_m()
        self.assertEqual([e["kind"] for e in b.events][7], "SCHEMA_MIGRATION")
        self.assertEqual(len(b.events), 8)
        self.assertTrue(any(e["kind"] == "ACK" and e.get("origin") for e in b.events[:7]))
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(X.with_hash(b.events, 7)))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], 2)
        self.assertEqual(d["verified"]["head_seq"], 1)
        self.assertIs(d["verified"]["migrated"], False)
        self.assertEqual(d["discarded"]["from_index"], 2)
        self.assertEqual(d["discarded"]["count"], 6)
        self.assertEqual([i["seq"] for i in d["discarded"]["items"]], [2, 3, 4, 5, 6, 7])
        self.assertEqual(d["discarded"]["items"][-1]["kind"], "SCHEMA_MIGRATION")
        self.assertEqual(spy.outcome(8)[-1], ("history_invalid", "event_hash"))
        for k in (7, 6, 5, 4, 3):
            self.assertEqual(spy.outcome(k), [("history_invalid", "origin")], "k=%d" % k)
        self.assertEqual(spy.outcome(2), [("PASS", None)])
        self.assertEqual(spy.ks(2)[-1], 2, "k=1 is never tried")

    def test_a_damaged_migration_without_earlier_acknowledgements(self):
        b = X.ex_m_empty()
        self.assertEqual([e["kind"] for e in b.events], ["GENESIS", "APPLY", "APPLY", "SCHEMA_MIGRATION"])
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(X.with_hash(b.events, 3)))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], 3)
        self.assertEqual(d["verified"]["head_seq"], 2)
        self.assertIs(d["verified"]["migrated"], False)
        self.assertEqual(d["discarded"]["count"], 1)
        self.assertEqual(d["discarded"]["items"][0]["kind"], "SCHEMA_MIGRATION")
        self.assertEqual(spy.outcome(4)[-1], ("history_invalid", "event_hash"))
        self.assertEqual(spy.outcome(3), [("PASS", None)])

    def test_the_migration_example_expectations_do_not_depend_on_changing_b1(self):
        b = X.ex_m()
        X.V.validate_history(b.history())             # the unchanged checker accepts the intact migrated history


if __name__ == "__main__":
    unittest.main()
