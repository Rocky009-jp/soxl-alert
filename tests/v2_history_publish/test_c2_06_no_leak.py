"""C2-14: no unexpected exception leaks out of check_publication and reconcile_publication. Whatever is changed in a
publication (types, then the ranges of its integer fields), in the current bytes or in the v1 bytes, the answer is a
value or a fixed refusal (a CoreError with its code); never an AttributeError, KeyError, TypeError, IndexError,
RecursionError, ValueError or the like. The changes are made here, with the hash written again, so that they get past
the hash check and reach the deeper steps."""
import copy
import json
import unittest

import c2_helpers as X

U = X.U

VALUES = (None, 0, 1, -1, True, False, "", "x", [], {}, [1], {"a": 1}, 1.5, 2 ** 64, "0" * 64, [None], [[]], [{}])
INTS = (-(2 ** 63) - 1, -2, -1, 0, 1, 2, 3, 7, 8, 9, 2 ** 31, 2 ** 63, 2 ** 64, 10 ** 30)


def paths_of(body, depth=3):
    """The paths (as tuples of keys) to change: the body keys, the keys of the dicts below, the first and the last
    element of each list of dicts, down to the depth."""
    found = []

    def walk(node, path, d):
        found.append(path)
        if d == 0:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + (k,), d - 1)
        elif isinstance(node, list) and node:
            idx = sorted({0, len(node) - 1})
            for i in idx:
                walk(node[i], path + (i,), d - 1)

    for k, v in body.items():
        walk(v, (k,), depth - 1)
    return found


def set_at(body, path, value):
    node = body
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def drop_at(body, path):
    node = body
    for key in path[:-1]:
        node = node[key]
    if isinstance(node, dict):
        del node[path[-1]]
    else:
        node.pop(path[-1])


class Leak(unittest.TestCase):
    def run_both(self, case, pub, currents, v1s=(None,)):
        """The kinds of the unexpected exceptions that came out, as strings."""
        bad = []
        for current in currents:
            for v1 in v1s:
                for name, fn, args in (("check", U.check_publication, (current, pub, v1)),
                                       ("reconcile", U.reconcile_publication, (current, pub))):
                    try:
                        fn(*args)
                    except X.CoreError:
                        pass
                    except BaseException as e:             # noqa: BLE001 - the point of the test
                        bad.append("%s %s: %s %s" % (case.source, name, type(e).__name__, e))
        return bad

    def currents(self, case):
        cands = [case.current, None, X.file_bytes(case.candidate), b"\xff\xfe", b"{", b""]
        if case.current:
            cands.append(case.current[:-1])
        return cands

    def v1s(self, case):
        return (case.source_v1,) if case.source == "MIGRATION" else (None,)

    def mutate_publication(self, case, values, with_drop=True):
        bad, count = [], 0
        body = case.pub.body
        for path in paths_of(body):
            for value in values:
                forged = copy.deepcopy(body)
                set_at(forged, path, value)
                try:
                    pub = U.HistoryPublication._make(forged)
                except X.CoreError:
                    continue
                count += 1
                bad.extend(self.run_both(case, pub, self.currents(case), self.v1s(case)))
            if with_drop and len(path) >= 1:
                forged = copy.deepcopy(body)
                try:
                    drop_at(forged, path)
                    pub = U.HistoryPublication._make(forged)
                except (X.CoreError, KeyError, IndexError):
                    continue
                count += 1
                bad.extend(self.run_both(case, pub, self.currents(case), self.v1s(case)))
        return bad, count

    def test_a_changed_type_anywhere_in_a_publication_is_a_refusal_or_a_value(self):
        total = 0
        for make in X.ALL_CASES:
            case = make()
            with self.subTest(source=case.source):
                bad, count = self.mutate_publication(case, VALUES)
                total += count
                self.assertEqual(bad[:5], [])
        self.assertGreater(total, 1500)

    def test_the_integer_fields_at_their_boundaries(self):
        total = 0
        for make in X.ALL_CASES:
            case = make()
            body = case.pub.body
            int_paths = [("candidate_head_seq",)]
            if body["expected"] is not None:
                int_paths += [("expected", k) for k in body["expected"] if k in ("head_seq", "raw_size")]
            if body["source_v1"] is not None:
                int_paths.append(("source_v1", "raw_size"))
            if body["records"] is not None:
                int_paths += [("records", i, "seq") for i in range(len(body["records"]))]
            if body["candidate_history"] is not None:
                n = len(body["candidate_history"]["events"])
                int_paths += [("candidate_history", "head_seq")] + [("candidate_history", "events", i, "seq")
                                                                    for i in sorted({0, n - 1})]
                int_paths += [("candidate_history", "events", i, "parent_seq") for i in sorted({0, n - 1})]
            n_cands = body["candidate_head_seq"]
            values = INTS + (n_cands - 1, n_cands, n_cands + 1)
            with self.subTest(source=case.source):
                bad = []
                for path in int_paths:
                    for value in values:
                        forged = copy.deepcopy(body)
                        try:
                            set_at(forged, path, value)
                            pub = U.HistoryPublication._make(forged)
                        except (X.CoreError, KeyError, IndexError, TypeError):
                            continue
                        total += 1
                        bad.extend(self.run_both(case, pub, self.currents(case), self.v1s(case)))
                self.assertEqual(bad[:5], [])
        self.assertGreater(total, 400)

    def test_a_negative_or_oversized_head_never_reaches_the_reading_of_the_current_bytes(self):
        c = X.day_case()
        for value in (-1, -2, -50, 10 ** 30):
            forged = X.rehash(c.pub, lambda b: b.update(candidate_head_seq=value))
            self.assertEqual(X.err(U.reconcile_publication, c.current, forged), ("publication_invalid", "publication",
                                                                                "shape"))
            self.assertEqual(X.err(U.check_publication, c.current, forged), ("publication_invalid", "publication",
                                                                            "shape"))

    def test_changed_bytes_of_the_current_file_and_of_the_v1_file(self):
        bad, count = [], 0
        for make in X.ALL_CASES:
            case = make()
            sources = []
            if case.current:
                sources.append(("current", case.current))
            if case.source_v1:
                sources.append(("v1", case.source_v1))
            for which, data in sources:
                step = max(1, len(data) // 45)
                positions = sorted(set(list(range(0, len(data), step)) + [len(data) - 1, len(data)]))
                for pos in positions:
                    variants = [data[:pos], data[:pos] + data[pos + 1:], data[:pos] + b'"' + data[pos + 1:],
                                data[:pos] + b"\x00" + data[pos:], data[:pos] + b"\xff" + data[pos + 1:],
                                data[:pos] + b"9" * 400 + data[pos + 1:]]
                    for blob in variants:
                        count += 1
                        if which == "current":
                            bad.extend(self.run_both(case, case.pub, [blob], self.v1s(case)))
                        else:
                            bad.extend(self.run_both(case, case.pub, [case.current], [blob]))
        self.assertEqual(bad[:5], [])
        self.assertGreater(count, 1500)

    def test_a_current_file_of_which_one_field_has_another_type_is_a_refusal_or_a_value(self):
        bad, count = [], 0
        for make in X.APPEND_CASES + (X.adoption_case,):
            case = make()
            base = case.history if case.source != "ADOPTION" else case.candidate
            doc = base.to_dict()
            for path in paths_of(doc, 3):
                for value in (None, 0, -1, True, "", "x", [], {}, 2 ** 64, [None]):
                    forged = copy.deepcopy(doc)
                    set_at(forged, path, value)
                    blob = json.dumps(forged).encode("utf-8")
                    count += 1
                    bad.extend(self.run_both(case, case.pub, [blob], self.v1s(case)))
        self.assertEqual(bad[:5], [])
        self.assertGreater(count, 600)

    def test_a_deeply_nested_or_huge_value_is_a_refusal(self):
        c = X.day_case()
        deep = b"[" * 100000 + b"]" * 100000
        for blob in (deep, b'{"a":' * 3000 + b"1" + b"}" * 3000, b"9" * 100000, b'{"head_seq":' + b"9" * 6000 + b"}"):
            for fn, args in ((U.check_publication, (blob, c.pub)), (U.reconcile_publication, (blob, c.pub))):
                try:
                    fn(*args)
                except X.CoreError:
                    pass
        self.assertEqual(U.reconcile_publication(deep, c.pub).outcome, U.CONFLICT)
        self.assertEqual(U.reconcile_publication(b"9" * 100000, c.pub).outcome, U.CONFLICT)


if __name__ == "__main__":
    unittest.main()
