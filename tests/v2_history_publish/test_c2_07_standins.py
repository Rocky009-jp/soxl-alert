"""C2-03 .. C2-09, the layers that the real confirming functions make unreachable: a builder checks that the candidate
extends the current history (the confirming functions always return such a candidate), that the candidate of a resolution
is the one of its batch, and that the identity of the adopted bytes is that of the bytes it was given. With the real
functions no input reaches these refusals, so the confirming function is replaced here, in the namespace of build.py, by a
stand-in that returns what the real one never returns (the same method as the stand-in of C-1's mutation 7)."""
import unittest
from types import SimpleNamespace
from unittest import mock

import c2_helpers as X

U, V = X.U, X.V
D, P, H = X.D, X.P, X.H

INTERNAL = ("history_invalid", "history", "publication_candidate")


def diverging(count):
    """A valid history with `count` records whose records after the genesis are not those of the usual base (another
    value on D1), so it is never an extension of it."""
    b = H.HB()
    for i in range(1, count):
        b.apply(D[i], 29.0 + i)
    return b.history()


class Layers(unittest.TestCase):
    def test_a_candidate_that_does_not_extend_the_history_is_not_published(self):
        c = X.restart_case()                                  # 3 records: GENESIS, D1, D2
        other = diverging(4)                                  # 4 records, a different D1 and D2
        self.assertEqual(len(other.events), len(c.history.events) + 1)
        self.assertNotEqual(other.events[1], c.history.events[1])
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", history=other)
        with mock.patch("v2_history_publish.build.confirm_restart_plan", return_value=stub):
            self.assertEqual(X.err(U.publish_restart, c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.w.ledger),
                             INTERNAL)

    def test_the_candidate_of_a_restore_is_checked_the_same_way(self):
        c = X.restore_case(consume=False)
        n = len(c.history.events)
        other = diverging(n + 1)
        self.assertNotEqual(other.events[1], c.history.events[1])
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", history=other)
        with mock.patch("v2_history_publish.build.confirm_restore_plan", return_value=stub):
            self.assertEqual(X.err(U.publish_restore, c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.w.ledger,
                                   c.w.series), INTERNAL)

    def test_a_candidate_that_is_the_history_itself_or_shorter_is_not_published(self):
        c = X.restart_case()
        for candidate in (c.history, V.make_history_genesis(X.P.World().start_after, X.P.World().sessions)):
            with self.subTest(records=len(candidate.events)):
                stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", history=candidate)
                with mock.patch("v2_history_publish.build.confirm_restart_plan", return_value=stub):
                    self.assertEqual(X.err(U.publish_restart, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                                           c.w.ledger), INTERNAL)

    def test_the_candidate_of_a_resolution_must_be_the_one_of_its_batch(self):
        c = X.resolution_case()
        other = diverging(len(c.candidate.events))            # the same number of records, not the batch's candidate
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", batch=c.conf.batch, history=other)
        with mock.patch("v2_history_publish.build.confirm_history_resolution_plan", return_value=stub):
            self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.ledger),
                             INTERNAL)
        same = SimpleNamespace(status="CONFIRMED_IN_MEMORY", batch=c.conf.batch, history=c.candidate)
        with mock.patch("v2_history_publish.build.confirm_history_resolution_plan", return_value=same):
            self.assertEqual(U.publish_resolution(c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.ledger),
                             c.pub)

    def test_the_adopted_bytes_must_be_the_bytes_the_plan_names(self):
        c = X.adoption_case()
        other = X.A5.damaged_at(c.builder, 4)[0]
        self.assertNotEqual(X.raw_of(other), X.raw_of(c.data))
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", history=c.candidate)
        with mock.patch("v2_history_publish.build.confirm_prefix_adoption", return_value=stub):
            self.assertEqual(X.err(U.publish_adoption, c.plan, c.plan.plan_hash, other), INTERNAL)
            # and for the bytes of the plan the publication states the identity of the bytes
            pub = U.publish_adoption(c.plan, c.plan.plan_hash, c.data)
        self.assertEqual(pub.body["expected"], X.raw_of(c.data))

    def test_the_expected_identity_comes_from_the_bytes_and_not_from_the_plan(self):
        # a plan whose identity is wrong, with a confirming step that says yes anyway: the bytes decide, and the
        # disagreement is refused (a publication that expected the plan's bytes would write over other bytes)
        c = X.adoption_case()
        forged = X.A5.refreshed(c.plan, lambda d: d["basis"].update(raw_sha256="1" * 64, raw_size=5))
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", history=c.candidate)
        with mock.patch("v2_history_publish.build.confirm_prefix_adoption", return_value=stub):
            self.assertEqual(X.err(U.publish_adoption, forged, forged.plan_hash, c.data), INTERNAL)

    def test_a_confirming_step_that_says_no_change_gives_no_publication(self):
        c = X.adoption_case()
        stub = SimpleNamespace(status="NO_CHANGE", history=c.candidate)
        with mock.patch("v2_history_publish.build.confirm_prefix_adoption", return_value=stub):
            self.assertEqual(X.err(U.publish_adoption, c.plan, c.plan.plan_hash, c.data),
                             ("publication_refused", "source", "no_change"))
        for name, make, call in (("confirm_restart_plan", X.restart_case, lambda c: U.publish_restart(
                c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.w.ledger)),):
            c2 = make()
            stub = SimpleNamespace(status="NO_CHANGE", history=c2.candidate)
            with mock.patch("v2_history_publish.build.%s" % name, return_value=stub):
                self.assertEqual(X.err(call, c2), ("publication_refused", "source", "no_change"))

    def test_a_day_that_is_not_prepared_gives_no_publication_even_with_a_batch(self):
        c = X.day_case()
        for status in ("ALREADY_APPLIED", "NO_COMMIT"):
            with self.subTest(status=status):
                stub = SimpleNamespace(status=status, batch=c.batch)
                with mock.patch("v2_history_publish.build.prepare_history_day", return_value=stub):
                    self.assertEqual(X.err(U.publish_day, c.history, D[2], c.w.series, c.w.sessions, c.w.ledger),
                                     ("publication_refused", "source", "not_prepared"))

    def test_a_confirmed_resolution_without_a_batch_gives_no_publication(self):
        c = X.resolution_case()
        stub = SimpleNamespace(status="CONFIRMED_IN_MEMORY", batch=None, history=c.candidate)
        with mock.patch("v2_history_publish.build.confirm_history_resolution_plan", return_value=stub):
            self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, c.history, c.w.sessions, c.ledger),
                             ("publication_refused", "source", "no_change"))


if __name__ == "__main__":
    unittest.main()
