"""A5-13 confirm, A5-14 an inconsistency inside the package, A5-15 the delegation (spies on the names the package really
calls)."""
import unittest

import a5_helpers as Z
from a5_helpers import A, D, G, H, V, X, GONE
import v2_history_adopt.build as B
import v2_history_adopt.confirm as C
import v2_history_adopt.prepare as PR
from v2_persistence.errors import PersistenceError

MISMATCH = ("history_plan_mismatch", "plan", None)
STALE = ("history_plan_stale", "plan", None)


def world():
    b, data, k = Z.new_world()
    return data, k, Z.prep(data, k)


def tamper(key, value):
    """Another value of the same kind for one key of the basis."""
    if key == "discarded":
        return dict(value, count=value["count"] + 1)
    if key == "candidate_history":
        return dict(value, head_seq=value["head_seq"] + 1)
    if key == "candidate_record":
        return dict(value, event_hash=Z.ZERO if value["event_hash"] != Z.ZERO else "1" * 64)
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value[:-1] + ("0" if value[-1] != "0" else "1")
    raise AssertionError(key)


class Outcomes(unittest.TestCase):
    def setUp(self):
        self.data, self.k, self.plan = world()

    def test_the_same_bytes_confirm_in_memory_with_the_candidate_of_the_plan(self):
        res = Z.confirm(self.plan, self.data)
        self.assertEqual(res.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(res.plan_hash, self.plan.plan_hash)
        self.assertIs(res.committed, False)
        self.assertEqual(res.history, V.History.from_dict(self.plan.basis["candidate_history"]))
        self.assertEqual(V.encode_history(res.history).encode("utf-8"), Z.candidate_bytes(self.data, self.k))
        self.assertEqual(V.validate_history(res.history).head_seq, self.k)

    def test_the_candidate_bytes_are_no_change_and_no_second_record_is_made(self):
        cand = Z.candidate_bytes(self.data, self.k)
        res = Z.confirm(self.plan, cand)
        self.assertEqual(res.status, "NO_CHANGE")
        self.assertEqual(res.history, V.History.from_dict(self.plan.basis["candidate_history"]))
        self.assertEqual(len(res.history.events), self.k + 1)
        self.assertEqual([e["kind"] for e in res.history.events].count("RECOVERY_PREFIX_ADOPTION"), 1)
        self.assertEqual(res.plan_hash, self.plan.plan_hash)

    def test_other_bytes_are_stale(self):
        cand = Z.candidate_bytes(self.data, self.k)
        b = X.ex_new()
        other_damage, _ = Z.damaged_at(b, 4)
        another_adoption, _ = Z.damaged_at(b, 6), None
        flipped = bytearray(self.data)
        flipped[-3] = ord("0") if flipped[-3] != ord("0") else ord("1")
        cases = {
            "one byte added": self.data + b" ", "one byte changed": bytes(flipped), "one byte removed": self.data[:-1],
            "indented candidate": X.indented(cand), "candidate with a space": cand + b"\n", "other damage": other_damage,
            "valid original": X.history_file(b), "garbage": b"xyz", "empty": b"", "utf8 error": b"\xff",
            "the prefix alone": Z.cj(H.header(Z.prefix_events(self.data, self.k))).encode("utf-8"),
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.assertEqual(Z.err(Z.confirm, self.plan, data), STALE)
        del another_adoption

    def test_a_plan_of_one_file_is_stale_for_another_file(self):
        b = X.ex_new()
        other, k2 = Z.damaged_at(b, 3)
        plan2 = Z.prep(other, k2, "ad2")
        self.assertEqual(Z.err(Z.confirm, self.plan, other), STALE)
        self.assertEqual(Z.err(Z.confirm, plan2, self.data), STALE)
        self.assertEqual(Z.confirm(plan2, other).status, "CONFIRMED_IN_MEMORY")

    def test_the_data_must_be_exactly_bytes_after_the_plan_is_accepted(self):
        class Sub(bytes):
            pass
        for bad in (self.data.decode("utf-8"), bytearray(self.data), memoryview(self.data), None, Sub(self.data)):
            with self.subTest(type(bad).__name__):
                self.assertEqual(Z.err(Z.confirm, self.plan, bad), ("adoption_invalid", "data", "type"))
        # a refused plan is reported before the type of the data
        self.assertEqual(Z.err(Z.confirm, self.plan, None, plan_hash=Z.ZERO), MISMATCH)

    def test_confirming_twice_gives_equal_results_and_changes_nothing(self):
        before = (self.plan.to_dict(), bytes(self.data))
        a, b = Z.confirm(self.plan, self.data), Z.confirm(self.plan, self.data)
        self.assertEqual(a, b)
        self.assertEqual(before, (self.plan.to_dict(), self.data))


class Mismatch(unittest.TestCase):
    def setUp(self):
        self.data, self.k, self.plan = world()
        self.cand = Z.candidate_bytes(self.data, self.k)

    def test_the_hash_asked_for_is_the_hash_of_the_plan(self):
        for bad in (Z.ZERO, "x", None, 5, self.plan.plan_hash.upper(), self.plan.plan_hash[:-1], "", [self.plan.plan_hash]):
            with self.subTest(repr(bad)[:20]):
                self.assertEqual(Z.err(A.confirm_prefix_adoption, self.plan, bad, self.data), MISMATCH)

    def test_the_hash_inside_the_plan_is_the_hash_of_its_basis(self):
        for name, fn in (("hash changed", lambda d: d.update(plan_hash=Z.ZERO)),
                         ("basis changed", lambda d: d["basis"].update(raw_size=d["basis"]["raw_size"] + 1)),
                         ("hash is a dict", lambda d: d.update(plan_hash={})), ("hash is a list", lambda d: d.update(plan_hash=[]))):
            with self.subTest(name):
                plan = Z.plan_with(self.plan, fn)
                self.assertEqual(Z.err(Z.confirm, plan, self.data, plan_hash=self.plan.plan_hash), MISMATCH)
                self.assertEqual(Z.err(Z.confirm, plan, self.data, plan_hash=plan.plan_hash), MISMATCH)

    def test_what_is_not_a_plan(self):
        for bad in (None, {}, self.plan.to_dict(), "plan", 5, [self.plan], object()):
            with self.subTest(type(bad).__name__):
                self.assertEqual(Z.err(A.confirm_prefix_adoption, bad, self.plan.plan_hash, self.data), MISMATCH)

    def test_the_basis_must_have_exactly_the_21_keys(self):
        for key in sorted(self.plan.basis):
            with self.subTest("missing " + key):
                plan = Z.refreshed(self.plan, lambda d, key=key: d["basis"].pop(key))
                self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)
        for extra in ("x", "prev_hash"):
            with self.subTest("extra " + extra):
                plan = Z.refreshed(self.plan, lambda d, extra=extra: d["basis"].update({extra: 1}))
                self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)
        plan = Z.refreshed(self.plan, lambda d: d.update(basis=[]))
        self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)

    def test_every_key_of_the_basis_tampered_alone_is_a_mismatch_for_the_original_bytes(self):
        for key, value in sorted(self.plan.basis.items()):
            with self.subTest(key):
                plan = Z.refreshed(self.plan, lambda d, key=key, value=value: d["basis"].update({key: tamper(key, value)}))
                self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)

    def test_the_keys_that_the_candidate_itself_proves_are_a_mismatch_for_the_candidate_bytes_too(self):
        keys = ["raw_sha256", "raw_size", "adopt_count", "prefix_head_seq", "prefix_head_hash", "prefix_state_digest",
                "prefix_document_digest", "request_id", "request_hash", "reason_code", "requested_at",
                "candidate_history", "candidate_digest", "candidate_head_seq", "candidate_head_hash",
                "candidate_state_digest", "candidate_record", "operation", "status"]
        for key in keys:
            with self.subTest(key):
                plan = Z.refreshed(self.plan, lambda d, key=key: d["basis"].update({key: tamper(key, d["basis"][key])}))
                self.assertEqual(Z.err(Z.confirm, plan, self.cand), MISMATCH)

    def test_a_replaced_candidate_record_or_history_is_a_mismatch(self):
        other = Z.record_of(Z.prefix_events(self.data, self.k), Z.evidence_of(self.data, self.k), "other-id")
        events = Z.prefix_events(self.data, self.k) + [other]

        def swap_record(d):
            d["basis"]["candidate_record"] = Z.deep(other)

        def swap_history(d):
            d["basis"]["candidate_history"] = H.header(events)

        def swap_both(d):
            swap_record(d)
            swap_history(d)

        def swap_both_and_digests(d):
            swap_both(d)
            cand = V.History.from_dict(H.header(events))
            d["basis"].update(candidate_digest=cand.digest, candidate_head_hash=other["event_hash"])

        def history_of_the_prefix_only(d):
            d["basis"]["candidate_history"] = H.header(Z.prefix_events(self.data, self.k))

        for name, fn in (("record", swap_record), ("history", swap_history), ("both", swap_both),
                         ("both and digests", swap_both_and_digests), ("prefix only", history_of_the_prefix_only)):
            with self.subTest(name):
                plan = Z.refreshed(self.plan, fn)
                self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)
                self.assertEqual(Z.err(Z.confirm, plan, self.cand), MISMATCH)

    def test_a_candidate_that_does_not_pass_the_checker_is_a_mismatch(self):
        def break_it(d):
            d["basis"]["candidate_history"]["events"][-1]["event_hash"] = Z.ZERO
        plan = Z.refreshed(self.plan, break_it)
        self.assertEqual(Z.err(Z.confirm, plan, self.data), MISMATCH)
        self.assertEqual(Z.err(Z.confirm, plan, self.cand), MISMATCH)

    def test_a_forged_plan_for_other_bytes_does_not_pass_as_the_original(self):
        other, k2 = Z.damaged_at(X.ex_new(), 3)
        forged = Z.refreshed(self.plan, lambda d: d["basis"].update(raw_sha256=Z.sha_bytes(other), raw_size=len(other)))
        self.assertEqual(Z.err(Z.confirm, forged, other), MISMATCH)

    def test_a_plan_for_a_different_request_id_or_time_is_another_plan(self):
        plan2 = Z.prep(self.data, self.k, "ad2")
        self.assertNotEqual(plan2.plan_hash, self.plan.plan_hash)
        self.assertEqual(Z.confirm(plan2, self.data).status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(Z.err(Z.confirm, self.plan, self.data, plan_hash=plan2.plan_hash), MISMATCH)


class InsidePackage(unittest.TestCase):
    """A5-14: a failure of the checker on a value the package itself made is not the caller's mistake."""

    def setUp(self):
        self.data, self.k, self.plan = world()
        self.real = B.validate_history

    def tearDown(self):
        B.validate_history = self.real
        C.validate_history = self.real

    def failing_on(self, call_numbers):
        calls = []
        real = self.real

        def spy(history):
            calls.append(history)
            if len(calls) in call_numbers:
                raise PersistenceError("history_invalid", "history", rule="spy")
            return real(history)

        B.validate_history = spy
        return calls

    def test_the_prefix_check_failing_is_reported_as_the_package_inconsistency(self):
        calls = self.failing_on({1})
        self.assertEqual(Z.err(Z.prep, self.data, self.k), ("history_invalid", "history", "adoption_candidate"))
        self.assertEqual(len(calls), 1)

    def test_the_candidate_check_failing_is_reported_the_same_way(self):
        calls = self.failing_on({2})
        self.assertEqual(Z.err(Z.prep, self.data, self.k), ("history_invalid", "history", "adoption_candidate"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].head_seq, self.k)

    def test_a_check_that_answers_something_else_is_the_same_inconsistency(self):
        real = self.real

        class Odd(object):
            def __init__(self, check, **changes):
                self.__dict__.update({n: getattr(check, n) for n in dir(check) if not n.startswith("_")})
                self.__dict__.update(changes)

        for name, changes in (("head_seq", dict(head_seq=99)), ("head_hash", dict(head_hash=Z.ZERO)),
                              ("state_digest", dict(state_digest=Z.ZERO)), ("history_digest", dict(history_digest=Z.ZERO))):
            with self.subTest(name):
                B.validate_history = lambda history, changes=changes: Odd(real(history), **changes)
                self.assertEqual(Z.err(Z.prep, self.data, self.k), ("history_invalid", "history", "adoption_candidate"))

    def test_a_failure_of_the_caller_is_not_reported_that_way(self):
        self.failing_on(set())
        self.assertEqual(Z.err(Z.prep, self.data, self.k + 1), ("adoption_invalid", "adopt_count", "count_mismatch"))
        self.assertEqual(Z.err(Z.prep, self.data, self.k, ""), ("adoption_invalid", "request_id", "request_id"))

    def test_the_rebuild_of_confirm_failing_inside_is_a_mismatch_of_the_plan(self):
        self.failing_on({1})
        self.assertEqual(Z.err(Z.confirm, self.plan, self.data), MISMATCH)

    def test_the_check_of_the_plans_own_candidate_failing_is_a_mismatch(self):
        def refuse(history):
            raise PersistenceError("history_invalid", "history", rule="spy")
        C.validate_history = refuse
        self.assertEqual(Z.err(Z.confirm, self.plan, self.data), MISMATCH)
        self.assertEqual(Z.err(Z.confirm, self.plan, Z.candidate_bytes(self.data, self.k)), MISMATCH)


class Delegation(unittest.TestCase):
    """A5-15: the names the package really references."""

    def setUp(self):
        self.data, self.k, self.plan = world()
        self.saved = {(m, n): getattr(m, n) for m, n in
                      ((PR, "diagnose_history_bytes"), (C, "diagnose_history_bytes"), (B, "validate_history"),
                       (C, "validate_history"), (B, "basis_request_hash"), (B, "compute_event_hash"))}

    def tearDown(self):
        for (module, name), value in self.saved.items():
            setattr(module, name, value)

    def wrap(self, module, name, log):
        real = getattr(module, name)

        def spy(*args, **kwargs):
            seen = tuple(Z.deep(a) if isinstance(a, (dict, list)) else a for a in args)                                        # as the call saw it (the caller may change it later)
            out = real(*args, **kwargs)
            log.append((seen, kwargs, out))
            return out

        setattr(module, name, spy)

    def test_prepare_diagnoses_the_bytes_once_with_the_unchanged_function(self):
        log = []
        self.wrap(PR, "diagnose_history_bytes", log)
        plan = Z.prep(self.data, self.k)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0][0][0], self.data)
        self.assertEqual(log[0][2].status, "PREFIX_ONLY")
        self.assertEqual(plan.basis["diagnosis_digest"], log[0][2].digest)

    def test_the_names_are_the_ones_of_the_unchanged_modules(self):
        self.assertIs(self.saved[(PR, "diagnose_history_bytes")], G.diagnose_history_bytes)
        self.assertIs(self.saved[(C, "diagnose_history_bytes")], G.diagnose_history_bytes)
        self.assertIs(self.saved[(B, "validate_history")], V.validate_history)
        self.assertIs(self.saved[(C, "validate_history")], V.validate_history)
        import v2_history.common as common
        import v2_persistence.codec as codec
        self.assertIs(self.saved[(B, "basis_request_hash")], common.basis_request_hash)
        self.assertIs(self.saved[(B, "compute_event_hash")], codec.compute_event_hash)

    def test_prepare_checks_the_prefix_and_the_candidate_with_validate_history(self):
        log = []
        self.wrap(B, "validate_history", log)
        Z.prep(self.data, self.k)
        self.assertEqual([len(a[0][0].events) for a in log], [self.k, self.k + 1])

    def test_the_request_hash_and_the_event_hash_come_from_the_existing_functions(self):
        hashes, events = [], []
        self.wrap(B, "basis_request_hash", hashes)
        self.wrap(B, "compute_event_hash", events)
        plan = Z.prep(self.data, self.k)
        rec = plan.basis["candidate_record"]
        self.assertEqual(len(hashes), 1)
        self.assertEqual(hashes[0][0][0], rec["request_basis"])
        self.assertEqual(hashes[0][2], rec["request_hash"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][2], rec["event_hash"])
        self.assertNotIn("event_hash", events[0][0][0])               # the hash is taken of the record without its own hash
        self.assertEqual(Z.H.hash_of(rec), rec["event_hash"])

    def test_confirm_of_the_original_bytes_diagnoses_once_and_rebuilds_with_that_diagnosis(self):
        diag, vh_confirm, vh_build = [], [], []
        self.wrap(C, "diagnose_history_bytes", diag)
        self.wrap(C, "validate_history", vh_confirm)
        self.wrap(B, "validate_history", vh_build)
        self.wrap(PR, "diagnose_history_bytes", [])
        self.assertEqual(Z.confirm(self.plan, self.data).status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(len(diag), 1)
        self.assertEqual(len(vh_confirm), 1)                           # the plan's own candidate
        self.assertEqual(len(vh_build), 2)                             # the rebuilt prefix and candidate

    def test_confirm_of_the_candidate_bytes_does_not_rebuild(self):
        diag, vh_build = [], []
        self.wrap(C, "diagnose_history_bytes", diag)
        self.wrap(B, "validate_history", vh_build)
        self.assertEqual(Z.confirm(self.plan, Z.candidate_bytes(self.data, self.k)).status, "NO_CHANGE")
        self.assertEqual((len(diag), len(vh_build)), (1, 0))

    def test_a_refused_plan_reads_no_bytes_at_all(self):
        diag = []
        self.wrap(C, "diagnose_history_bytes", diag)
        self.assertEqual(Z.err(Z.confirm, self.plan, self.data, plan_hash=Z.ZERO), MISMATCH)
        self.assertEqual(Z.err(Z.confirm, self.plan, None), ("adoption_invalid", "data", "type"))
        self.assertEqual(diag, [])

    def test_prepare_does_not_diagnose_when_an_argument_is_wrong(self):
        diag = []
        self.wrap(PR, "diagnose_history_bytes", diag)
        for args in ((self.data, 0, "ad1", Z.WHEN), (None, 6, "ad1", Z.WHEN), (self.data, 6, "", Z.WHEN)):
            try:
                A.prepare_prefix_adoption(*args)
            except Exception:                                          # noqa: BLE001
                pass
        self.assertEqual(diag, [])


if __name__ == "__main__":
    unittest.main()
