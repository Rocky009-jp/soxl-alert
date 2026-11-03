"""C2-11: check_publication, the compare and swap on the current bytes (design 5.2)."""
import json
import unittest

import c2_helpers as X

U, V = X.U, X.V
D, P = X.D, X.P

INVALID = lambda rule: ("publication_invalid", "publication", rule)       # noqa: E731
STALE = lambda rule: ("publication_stale", "current", rule)               # noqa: E731
GARBAGE = (b"", b"\xff\xfe", b"{", b"[]", b"null", b"\xef\xbb\xbf{}")


class Success(unittest.TestCase):
    def test_every_way_of_writing_succeeds_on_the_bytes_it_expects(self):
        for c in X.every_case():
            with self.subTest(source=c.source):
                self.assertEqual(c.check(), c.candidate)
                self.assertEqual(c.check().digest, V.validate_history(c.candidate).history_digest)

    def test_a_check_changes_nothing_and_can_be_repeated(self):
        for c in X.every_case():
            with self.subTest(source=c.source):
                before = (c.pub.to_dict(), c.current, c.source_v1)
                first = c.check()
                self.assertEqual(c.check(), first)
                self.assertEqual((c.pub.to_dict(), c.current, c.source_v1), before)

    def test_an_append_accepts_a_valid_text_that_is_not_canonical(self):
        for make in X.APPEND_CASES:
            c = make()
            with self.subTest(source=c.source):
                pretty = X.indented(c.history)
                self.assertNotEqual(pretty, c.current)
                self.assertEqual(c.check(pretty), c.candidate)
                self.assertEqual(c.check(c.current + b"\n"), c.candidate)

    def test_a_replace_accepts_the_damaged_bytes_it_names_and_nothing_else(self):
        c = X.adoption_case()
        self.assertRaises(Exception, U.read_history_bytes, c.current)          # the bytes cannot be read as a history
        self.assertEqual(c.check(), c.candidate)

    def test_an_append_that_follows_an_append_is_checked_on_the_bytes_of_the_first(self):
        c = X.day_case()
        w = c.w
        w.ledger.append(P.obs("R3", D[3], 33.0))
        second = U.publish_day(c.candidate, D[3], w.series, w.sessions, w.ledger)
        self.assertEqual(U.check_publication(U.history_bytes(c.candidate), second).head_seq, 3)
        self.assertEqual(X.err(U.check_publication, c.current, second), STALE("head"))


class StaleCurrent(unittest.TestCase):
    def test_an_append_needs_a_current_history_and_it_must_be_the_one_expected(self):
        for make in X.APPEND_CASES:
            c = make()
            with self.subTest(source=c.source):
                self.assertEqual(X.err(c.check, None), STALE("absent"))
                self.assertEqual(X.err(c.check, U.history_bytes(c.candidate)), STALE("head"))   # already written
                other = X.restart_case() if c.source in ("DAILY", "RESOLUTION") else X.day_case()
                self.assertNotEqual(other.current, c.current)
                self.assertEqual(X.err(c.check, other.current), STALE("head"))                   # another history
                self.assertEqual(X.err(c.check, U.history_bytes(V.make_history_genesis(
                    X.P.World().start_after, X.P.World().sessions))), STALE("head"))

    def test_an_append_that_differs_by_one_part_of_the_expected_head_is_stale(self):
        c = X.day_case()
        for field, value in (("head_seq", 5), ("head_hash", "1" * 64), ("history_digest", "1" * 64)):
            with self.subTest(field=field):
                p = X.rehash(c.pub, lambda b: b["expected"].update({field: value}))
                if field == "head_seq":
                    p = X.rehash(c.pub, lambda b: (b["expected"].update(head_seq=5),
                                                   b.update(candidate_head_seq=5 + len(b["records"]))))
                self.assertEqual(X.err(U.check_publication, c.current, p), STALE("head"))

    def test_a_create_needs_that_nothing_is_there(self):
        for make in (X.genesis_case, X.migration_case):
            c = make()
            with self.subTest(source=c.source):
                for current in (U.history_bytes(c.candidate), b"", b"x", b"\xff", c.candidate.to_dict().__repr__().encode()):
                    self.assertEqual(X.err(c.check, current), STALE("present"))

    def test_a_migration_needs_the_v1_bytes_it_names(self):
        c = X.migration_case()
        other = X.encode_snapshot(X.H.example_m_empty_world()[1]).encode("utf-8")
        for v1 in (None, b"", other, c.data + b" ", c.data[:-1]):
            with self.subTest(v1=None if v1 is None else len(v1)):
                self.assertEqual(X.err(c.check, None, v1), STALE("source_v1"))
        self.assertEqual(c.check(None, c.data), c.candidate)

    def test_a_replace_needs_the_raw_identity_of_the_bytes_it_names(self):
        c = X.adoption_case()
        for current in (None, b"", c.data + b"\n", c.data[:-1], U.history_bytes(c.candidate), b"x"):
            with self.subTest(current=None if current is None else len(current)):
                self.assertEqual(X.err(c.check, current), STALE("raw"))

    def test_the_identity_of_a_replace_is_that_of_the_bytes_not_of_the_text(self):
        # a text that reads the same but is another sequence of bytes is not the bytes that were named
        a = X.adoption_case()
        doc = json.loads(a.data.decode("utf-8"))
        again = json.dumps(doc).encode("utf-8")
        self.assertNotEqual(again, a.data)
        self.assertEqual(X.err(a.check, again), STALE("raw"))


class UnreadableCurrent(unittest.TestCase):
    def test_an_append_on_bytes_that_are_not_a_valid_history_is_a_history_error(self):
        c = X.day_case()
        for name, data, rule in (("bom", b"\xef\xbb\xbf" + c.current, "json"), ("not utf-8", b"\xff\xfe", "utf8"),
                                 ("broken", c.current[:-4], "json"), ("empty", b"", "json"), ("list", b"[]", "shape")):
            with self.subTest(name=name):
                self.assertEqual(X.err(c.check, data), ("history_invalid", "history", rule))
        doc = c.history.to_dict()
        doc["events"][1]["state_after"]["streak"] = 123
        self.assertEqual(X.err(c.check, json.dumps(doc).encode("utf-8"))[:2], ("history_invalid", "history"))
        doc = c.history.to_dict()
        doc["head_hash"] = X.ZERO
        self.assertEqual(X.err(c.check, json.dumps(doc).encode("utf-8"))[:2], ("history_invalid", "history"))


class ArgumentMisuse(unittest.TestCase):
    """The arguments are looked at before the current bytes are compared (and after the publication itself)."""

    def test_the_current_must_be_bytes_or_none(self):
        class Sub(bytes):
            pass
        for c in X.every_case():
            for bad in ("text", bytearray(b"x"), memoryview(b"x"), 7, [b"x"], {"a": 1}, Sub(b"x"), True):
                with self.subTest(source=c.source, bad=type(bad).__name__):
                    self.assertEqual(X.err(c.check, bad), INVALID("current_type"))

    def test_the_v1_bytes_belong_to_a_migration_only(self):
        for make in (X.day_case, X.resolution_case, X.restart_case, X.restore_case, X.genesis_case, X.adoption_case):
            c = make()
            with self.subTest(source=c.source):
                self.assertEqual(X.err(c.check, X.UNSET, b"{}"), INVALID("source_v1"))
                self.assertEqual(X.err(c.check, X.UNSET, b""), INVALID("source_v1"))
                self.assertEqual(c.check(X.UNSET, None), c.candidate)

    def test_the_v1_bytes_of_a_migration_must_be_bytes_or_none(self):
        c = X.migration_case()
        for bad in ("text", bytearray(c.data), memoryview(c.data), 7, [c.data]):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(c.check, None, bad), INVALID("source_v1"))

    def test_a_misuse_is_seen_before_a_current_that_is_stale_absent_or_unreadable(self):
        c = X.day_case()
        for current in (None, b"", b"\xff", U.history_bytes(c.candidate), X.restart_case().current):
            with self.subTest(current=None if current is None else len(current)):
                self.assertEqual(X.err(c.check, current, b"v1"), INVALID("source_v1"))
        m = X.migration_case()
        self.assertEqual(X.err(m.check, b"x", "text"), INVALID("source_v1"))            # present, and misuse
        a = X.adoption_case()
        self.assertEqual(X.err(a.check, None, b"x"), INVALID("source_v1"))

    def test_the_type_of_the_current_is_seen_before_the_v1_bytes(self):
        c = X.day_case()
        self.assertEqual(X.err(c.check, "text", b"v1"), INVALID("current_type"))

    def test_a_wrong_publication_is_seen_before_any_misuse(self):
        c = X.day_case()
        for bad in (None, {}, "x", c.pub.to_dict(), c.pub.body, 5, object()):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.check_publication, "text", bad, b"v1"), INVALID("type"))
                self.assertEqual(X.err(U.check_publication, c.current, bad), INVALID("type"))
        broken = X.rehash(c.pub, lambda b: b.update(mode="CREATE"))
        self.assertEqual(X.err(U.check_publication, "text", broken, b"v1"), INVALID("mode"))

    def test_the_current_is_compared_before_the_candidate_is_checked(self):
        c = X.day_case()
        bad = X.rehash(c.pub, lambda b: b["records"][0]["state_after"].update(streak=77))
        self.assertEqual(X.err(U.check_publication, c.current, bad)[:2], ("history_invalid", "history"))   # candidate
        self.assertEqual(X.err(U.check_publication, None, bad), STALE("absent"))                           # current first
        self.assertEqual(X.err(U.check_publication, U.history_bytes(c.candidate), bad), STALE("head"))
        self.assertEqual(X.err(U.check_publication, b"\xff", bad), ("history_invalid", "history", "utf8"))


class WrongPublication(unittest.TestCase):
    def test_a_value_that_is_not_a_publication_is_refused(self):
        c = X.day_case()
        for bad in (None, {}, [], "x", 3, c.pub.to_dict(), c.pub.body, X.day_case().reconcile(), object, b""):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.check_publication, c.current, bad), INVALID("type"))

    def test_a_value_whose_hash_does_not_fit_is_refused(self):
        c = X.day_case()
        view = c.pub.to_dict()
        for wrong in ("0" * 64, "x", None, 5, c.pub.publication_hash.upper(), c.pub.publication_hash[:-1]):
            with self.subTest(wrong=wrong):
                view2 = dict(view, publication_hash=wrong)
                forged = U.HistoryPublication._wrap(view2, lambda rule: AssertionError(rule))
                self.assertEqual(X.err(U.check_publication, c.current, forged), INVALID("publication_hash"))
        body = c.pub.body
        body["d"] = D[3]                                              # the body changed, the hash was not
        forged = U.HistoryPublication._wrap({"body": body, "publication_hash": c.pub.publication_hash}, None)
        self.assertEqual(X.err(U.check_publication, c.current, forged), INVALID("publication_hash"))

    def test_a_body_of_the_wrong_form_is_refused_even_with_its_hash_written_again(self):
        c = X.day_case()

        def drop(key):
            return lambda b: b.pop(key)
        cases = {"operation": lambda b: b.update(operation="x"), "extra key": lambda b: b.update(extra=1),
                 "missing key": drop("records"), "mode for the source": lambda b: b.update(mode="CREATE"),
                 "unknown source": lambda b: b.update(source="X"), "source type": lambda b: b.update(source=["DAILY"]),
                 "hash form": lambda b: b.update(candidate_digest="zz"), "state digest": lambda b: b.update(
                     candidate_state_digest=None), "head hash": lambda b: b.update(candidate_head_hash=5),
                 "day": lambda b: b.update(d="2026-3-5"), "no day": lambda b: b.update(d=None),
                 "request id on a day": lambda b: b.update(request_id="q1"),
                 "plan hash on a day": lambda b: b.update(plan_hash=X.ZERO),
                 "expected missing": lambda b: b.update(expected=None), "expected key": lambda b: b["expected"].update(x=1),
                 "records empty": lambda b: b.update(records=[]), "records none": lambda b: b.update(records=None),
                 "records type": lambda b: b.update(records="x"),
                 "candidate given": lambda b: b.update(candidate_history={}),
                 "v1 given": lambda b: b.update(source_v1={"raw_sha256": X.ZERO, "raw_size": 1})}
        expected_rule = {"mode for the source": "mode", "unknown source": "mode", "source type": "mode"}
        for name, fn in cases.items():
            with self.subTest(name=name):
                p = _forged(c.pub, fn)
                self.assertEqual(X.err(U.check_publication, c.current, p),
                                 INVALID(expected_rule.get(name, "shape")))

    def test_the_fields_of_a_plan_source_are_checked(self):
        c = X.restart_case()
        for name, fn in {"no request id": lambda b: b.update(request_id=None), "bad request id": lambda b: b.update(
                request_id="a b"), "no plan hash": lambda b: b.update(plan_hash=None),
                         "plan hash form": lambda b: b.update(plan_hash="x"),
                         "a day on a plan": lambda b: b.update(d=D[2])}.items():
            with self.subTest(name=name):
                self.assertEqual(X.err(U.check_publication, c.current, _forged(c.pub, fn)), INVALID("shape"))

    def test_the_fields_of_a_create_and_a_replace_are_checked(self):
        g, m, a = X.genesis_case(), X.migration_case(), X.adoption_case()
        for case, name, fn in (
                (g, "expected on a create", lambda b: b.update(expected={"raw_sha256": X.ZERO, "raw_size": 0})),
                (g, "records on a create", lambda b: b.update(records=[{}])),
                (g, "no candidate", lambda b: b.update(candidate_history=None)),
                (g, "v1 on a genesis", lambda b: b.update(source_v1={"raw_sha256": X.ZERO, "raw_size": 0})),
                (g, "request id on a genesis", lambda b: b.update(request_id="q1")),
                (m, "no v1", lambda b: b.update(source_v1=None)),
                (m, "v1 key", lambda b: b["source_v1"].update(x=1)),
                (m, "v1 size", lambda b: b["source_v1"].update(raw_size=-1)),
                (m, "v1 sha", lambda b: b["source_v1"].update(raw_sha256="x")),
                (a, "no expected", lambda b: b.update(expected=None)),
                (a, "expected key", lambda b: b["expected"].pop("raw_size")),
                (a, "expected size", lambda b: b["expected"].update(raw_size=True)),
                (a, "v1 on an adoption", lambda b: b.update(source_v1={"raw_sha256": X.ZERO, "raw_size": 0})),
                (a, "records on an adoption", lambda b: b.update(records=[]))):
            with self.subTest(name=name):
                self.assertEqual(X.err(U.check_publication, case.current, _forged(case.pub, fn), case.source_v1),
                                 INVALID("shape"))

    def test_the_candidate_must_be_what_the_fields_say(self):
        c = X.day_case()
        for name, fn in {"digest": lambda b: b.update(candidate_digest="1" * 64),
                         "head hash": lambda b: b.update(candidate_head_hash="1" * 64),
                         "state digest": lambda b: b.update(candidate_state_digest="1" * 64)}.items():
            with self.subTest(name=name):
                self.assertEqual(X.err(U.check_publication, c.current, _forged(c.pub, fn)), INVALID("candidate_digest"))
        g = X.genesis_case()
        for name, fn in {"digest": lambda b: b.update(candidate_digest="1" * 64),
                         "state digest": lambda b: b.update(candidate_state_digest="1" * 64)}.items():
            with self.subTest(name="create " + name):
                self.assertEqual(X.err(U.check_publication, None, _forged(g.pub, fn)), INVALID("candidate_digest"))

    def test_changed_records_are_refused_even_with_the_hash_written_again(self):
        for make in X.APPEND_CASES:
            c = make()
            for name, fn in {"state": lambda b: b["records"][-1]["state_after"].update(streak=77),
                             "a field": lambda b: b["records"][0].update(kind="APPLY" if b["records"][0]["kind"] != "APPLY"
                                                                         else "ACK")}.items():
                with self.subTest(source=c.source, name=name):
                    e = X.err(U.check_publication, c.current, _forged(c.pub, fn))
                    self.assertIn(e[:2], (("history_invalid", "history"), ("publication_invalid", "publication")))
            with self.subTest(source=c.source, name="seq"):
                p = _forged(c.pub, lambda b: b["records"][0].update(seq=b["records"][0]["seq"] + 1))
                self.assertEqual(X.err(U.check_publication, c.current, p), INVALID("records"))
            with self.subTest(source=c.source, name="not a record"):
                p = _forged(c.pub, lambda b: b["records"].__setitem__(0, "x"))
                self.assertEqual(X.err(U.check_publication, c.current, p), INVALID("records"))
            with self.subTest(source=c.source, name="no event hash"):
                p = _forged(c.pub, lambda b: b["records"][0].pop("event_hash"))
                e = X.err(U.check_publication, c.current, p)
                self.assertIn(e, (INVALID("records"), ("history_invalid", "history", "record_keys")))

    def test_a_changed_candidate_of_a_whole_publication_is_refused(self):
        for make in (X.genesis_case, X.migration_case, X.adoption_case):
            c = make()
            with self.subTest(source=c.source):
                p = _forged(c.pub, lambda b: b["candidate_history"]["events"][-1]["state_after"].update(streak=77))
                e = X.err(U.check_publication, c.current, p, c.source_v1)
                self.assertEqual(e[:2], ("history_invalid", "history"))
                p = _forged(c.pub, lambda b: b["candidate_history"].pop("current_state"))
                e = X.err(U.check_publication, c.current, p, c.source_v1)
                self.assertEqual(e[:2], ("history_invalid", "history"))

    def test_the_integer_fields_have_ranges_in_the_form(self):
        c = X.day_case()
        for name, fn in {"negative head": lambda b: b.update(candidate_head_seq=-1),
                         "zero head": lambda b: b.update(candidate_head_seq=0),
                         "one too many": lambda b: b.update(candidate_head_seq=b["candidate_head_seq"] + 1),
                         "huge": lambda b: b.update(candidate_head_seq=10 ** 30), "bool": lambda b: b.update(
                             candidate_head_seq=True), "float": lambda b: b.update(candidate_head_seq=2.0),
                         "str": lambda b: b.update(candidate_head_seq="2"),
                         "negative expected": lambda b: b["expected"].update(head_seq=-1),
                         "huge expected": lambda b: b["expected"].update(head_seq=10 ** 30),
                         "bool expected": lambda b: b["expected"].update(head_seq=True)}.items():
            with self.subTest(name=name):
                self.assertEqual(X.err(U.check_publication, c.current, _forged(c.pub, fn)), INVALID("shape"))
        a = X.adoption_case()
        for name, fn in {"negative size": lambda b: b["expected"].update(raw_size=-1),
                         "huge size": lambda b: b["expected"].update(raw_size="1"),
                         "head not the count": lambda b: b.update(candidate_head_seq=b["candidate_head_seq"] + 1)}.items():
            with self.subTest(name="replace " + name):
                self.assertEqual(X.err(U.check_publication, a.current, _forged(a.pub, fn)), INVALID("shape"))


def _forged(pub, fn):
    return X.rehash(pub, fn)


if __name__ == "__main__":
    unittest.main()
