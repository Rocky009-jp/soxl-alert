"""C2-12: reconcile_publication, the read-only reconciliation after an uncertain outcome (design 5.3)."""
import json
import unittest

import c2_helpers as X

U, V = X.U, X.V

PUBLISHED, EXTENDED, NOT_PUBLISHED, CONFLICT = U.PUBLISHED, U.PUBLISHED_THEN_EXTENDED, U.NOT_PUBLISHED, U.CONFLICT
INVALID = lambda rule: ("publication_invalid", "publication", rule)       # noqa: E731
UNREADABLE = (b"", b"\xff\xfe", b"{", b"[]", b"null", b"\xef\xbb\xbf{}", b"\xef\xbb\xbf")


def outcome(case, current):
    return U.reconcile_publication(current, case.pub).outcome


class FourOutcomes(unittest.TestCase):
    def test_before_after_and_after_with_more_records(self):
        for c in X.every_case():
            with self.subTest(source=c.source):
                self.assertEqual(outcome(c, c.current), NOT_PUBLISHED)                          # still as expected
                self.assertEqual(outcome(c, X.file_bytes(c.candidate)), PUBLISHED)              # the candidate itself
                self.assertEqual(outcome(c, X.file_bytes(X.extended_history(c))), EXTENDED)     # records follow

    def test_an_append_that_is_published_is_published_in_any_valid_text_of_the_candidate(self):
        for make in X.APPEND_CASES:
            c = make()
            with self.subTest(source=c.source):
                self.assertEqual(outcome(c, X.indented(c.candidate)), PUBLISHED)
                self.assertEqual(outcome(c, X.indented(c.history)), NOT_PUBLISHED)
                self.assertEqual(outcome(c, X.indented(X.extended_history(c))), EXTENDED)

    def test_an_absent_file(self):
        for c in X.every_case():
            with self.subTest(source=c.source):
                expected = NOT_PUBLISHED if c.pub.mode == "CREATE" else CONFLICT
                self.assertEqual(outcome(c, None), expected)

    def test_a_file_that_cannot_be_read_is_a_conflict_not_an_error(self):
        for c in X.every_case():
            for data in UNREADABLE:
                with self.subTest(source=c.source, size=len(data)):
                    self.assertEqual(outcome(c, data), CONFLICT)

    def test_an_append_whose_current_file_is_damaged_in_one_place_is_a_conflict(self):
        for make in X.APPEND_CASES:
            c = make()
            with self.subTest(source=c.source):
                doc = c.history.to_dict()
                doc["events"][1]["state_after"]["streak"] = 123
                self.assertEqual(outcome(c, json.dumps(doc).encode("utf-8")), CONFLICT)
                self.assertEqual(outcome(c, c.current[:-1]), CONFLICT)
                self.assertEqual(outcome(c, c.current + b"x"), CONFLICT)

    def test_another_history_is_a_conflict(self):
        for c in X.every_case():
            others = [x for x in X.every_case() if x.pub.publication_hash != c.pub.publication_hash]
            for other in others:
                with self.subTest(source=c.source, other=other.source):
                    # a history that begins with the very record that a GENESIS publication makes is that publication
                    # followed by more records, whatever the records are; any other history is a conflict
                    same_start = c.source == "GENESIS" and other.candidate.events[0] == c.candidate.events[0]
                    self.assertEqual(outcome(c, X.file_bytes(other.candidate)), EXTENDED if same_start else CONFLICT)
        g = X.genesis_case()
        later = X.P.World(1)
        self.assertNotEqual(later.start_after, g.w.start_after)
        self.assertEqual(outcome(g, X.file_bytes(V.make_history_genesis(later.start_after, later.sessions))), CONFLICT)
        for make in (X.day_case, X.resolution_case, X.restart_case):
            c = make()
            with self.subTest(source=c.source, what="diverging extension"):
                self.assertEqual(outcome(c, X.file_bytes(X.other_extension(c))), CONFLICT)

    def test_a_create_that_finds_a_file_that_is_not_its_candidate_is_a_conflict(self):
        for make in (X.genesis_case, X.migration_case):
            c = make()
            with self.subTest(source=c.source):
                other = X.day_case().candidate
                expected = EXTENDED if c.source == "GENESIS" else CONFLICT      # it begins with the same genesis
                self.assertEqual(outcome(c, X.file_bytes(other)), expected)

    def test_a_replace_is_not_published_while_the_named_bytes_are_there_even_if_they_cannot_be_read(self):
        c = X.adoption_case()
        self.assertRaises(Exception, U.read_history_bytes, c.data)
        self.assertEqual(outcome(c, c.data), NOT_PUBLISHED)                        # the first look, before any reading
        self.assertEqual(outcome(c, c.data + b" "), CONFLICT)
        self.assertEqual(outcome(c, c.data[:-1]), CONFLICT)
        self.assertEqual(outcome(c, None), CONFLICT)

    def test_a_replace_over_other_valid_bytes_is_a_conflict(self):
        c = X.adoption_case()
        self.assertEqual(outcome(c, X.file_bytes(c.builder.history())), CONFLICT)     # the whole file, not damaged

    def test_the_reconciliation_names_the_publication_and_nothing_else(self):
        for c in X.every_case():
            r = U.reconcile_publication(c.current, c.pub)
            self.assertEqual(r.publication_hash, c.pub.publication_hash)
            self.assertEqual(set(r.to_dict()), {"outcome", "publication_hash"})
            self.assertIn(r.outcome, (PUBLISHED, EXTENDED, NOT_PUBLISHED, CONFLICT))

    def test_the_reconciliation_reads_only(self):
        for c in X.every_case():
            before = (c.pub.to_dict(), c.current)
            U.reconcile_publication(c.current, c.pub)
            self.assertEqual((c.pub.to_dict(), c.current), before)


class PhysicalPrefix(unittest.TestCase):
    """The extended outcome is decided by the digest of the physical prefix, not by the hash of one record."""

    def test_a_publication_whose_head_hash_fits_but_whose_digest_does_not_is_a_conflict(self):
        # The hash of every record contains its seq and the hash before it, so an honest publication cannot tell the two
        # tests apart. Here the candidate_digest is changed and the publication hash written again: the record at
        # candidate_head_seq of the current history still has the candidate_head_hash, but the prefix is not the candidate.
        for make in X.APPEND_CASES:
            c = make()
            with self.subTest(source=c.source):
                current = X.file_bytes(X.extended_history(c))
                history = U.read_history_bytes(current)[0]
                self.assertEqual(history.events[c.candidate.head_seq]["event_hash"], c.pub.body["candidate_head_hash"])
                forged = X.rehash(c.pub, lambda b: b.update(candidate_digest="1" * 64))
                self.assertEqual(U.reconcile_publication(current, forged).outcome, CONFLICT)
                self.assertEqual(U.reconcile_publication(current, c.pub).outcome, EXTENDED)

    def test_the_same_holds_for_a_create_and_a_replace(self):
        for make in (X.genesis_case, X.migration_case, X.adoption_case):
            c = make()
            with self.subTest(source=c.source):
                current = X.file_bytes(X.extended_history(c))
                forged = X.rehash(c.pub, lambda b: b.update(candidate_digest="1" * 64))
                self.assertEqual(U.reconcile_publication(current, forged).outcome, CONFLICT)

    def test_the_head_of_a_published_candidate_is_compared_with_its_hash_and_digest_together(self):
        c = X.day_case()
        for field in ("candidate_head_hash", "candidate_digest"):
            with self.subTest(field=field):
                forged = X.rehash(c.pub, lambda b: b.update({field: "1" * 64}))
                self.assertEqual(U.reconcile_publication(X.file_bytes(c.candidate), forged).outcome, CONFLICT)


class Boundaries(unittest.TestCase):
    """Only a wrong publication or a wrong argument raises; what is in the bytes is returned as a value."""

    def test_the_arguments_and_the_publication_are_refused_in_the_same_way_as_by_check_publication(self):
        c = X.day_case()
        class Sub(bytes):
            pass
        for bad in ("text", bytearray(c.current), memoryview(c.current), 5, [1], {"a": 1}, Sub(c.current)):
            with self.subTest(current=type(bad).__name__):
                self.assertEqual(X.err(U.reconcile_publication, bad, c.pub), INVALID("current_type"))
        for bad in (None, {}, "x", c.pub.to_dict(), 3, c.reconcile()):
            with self.subTest(pub=type(bad).__name__):
                self.assertEqual(X.err(U.reconcile_publication, c.current, bad), INVALID("type"))
                self.assertEqual(X.err(U.reconcile_publication, "text", bad), INVALID("type"))
        forged = X.rehash(c.pub, lambda b: b.update(candidate_head_seq=-1))
        self.assertEqual(X.err(U.reconcile_publication, c.current, forged), INVALID("shape"))
        view = dict(c.pub.to_dict(), publication_hash="0" * 64)
        wrong = U.HistoryPublication._wrap(view, None)
        self.assertEqual(X.err(U.reconcile_publication, c.current, wrong), INVALID("publication_hash"))

    def test_a_publication_of_a_wrong_form_is_refused_by_both_the_same_way(self):
        c = X.day_case()
        for name, fn in {"mode": lambda b: b.update(mode="REPLACE"), "extra": lambda b: b.update(x=1),
                         "records": lambda b: b.update(records=[]), "head": lambda b: b.update(candidate_head_seq=7),
                         "digest": lambda b: b.update(candidate_digest="nope")}.items():
            with self.subTest(name=name):
                forged = X.rehash(c.pub, fn)
                self.assertEqual(X.err(U.reconcile_publication, c.current, forged),
                                 X.err(U.check_publication, c.current, forged))

    def test_a_publication_whose_content_is_wrong_is_not_an_error_for_the_reconciliation(self):
        # the reconciliation does not build the candidate: the content is for check_publication, before any write
        c = X.day_case()
        forged = X.rehash(c.pub, lambda b: b["records"][0]["state_after"].update(streak=77))
        self.assertEqual(outcome(X.Case("DAILY", forged, c.current, c.candidate), c.current), NOT_PUBLISHED)
        self.assertEqual(X.err(U.check_publication, c.current, forged)[:2], ("history_invalid", "history"))


if __name__ == "__main__":
    unittest.main()
