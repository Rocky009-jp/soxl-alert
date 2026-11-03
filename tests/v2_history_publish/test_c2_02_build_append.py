"""C2-03 (DAILY), C2-04 (RESOLUTION), C2-05 (RESTART), C2-06 (RESTORE): the builders that append records.

Each expected value is the result of the existing confirming step for the same inputs (the candidate it returns, the
records it adds); the builder under test only has to make a publication of exactly that. A refusal of the confirming
step comes back with the same code, field and rule, not wrapped."""
import unittest

import c2_helpers as X

U, O, V, RS, RT = X.U, X.O, X.V, X.RS, X.RT
D, P, T = X.D, X.P, X.T


def tail(case):
    """The records that the candidate adds to the history the case started from."""
    return case.candidate.events[len(case.history.events):]


class AppendCommon(unittest.TestCase):
    def assert_append_publication(self, case, source):
        body = case.pub.body
        self.assertEqual((body["mode"], body["source"]), ("APPEND", source))
        check = V.validate_history(case.history)
        self.assertEqual(body["expected"], {"head_seq": check.head_seq, "head_hash": check.head_hash,
                                            "history_digest": check.history_digest})
        self.assertEqual(body["records"], tail(case))
        self.assertEqual(X.cj(body["records"]), X.cj(tail(case)))
        self.assertIsNone(body["candidate_history"])
        self.assertIsNone(body["source_v1"])
        # applied to the current bytes, the publication gives the candidate of the confirming step
        self.assertEqual(case.check(), case.candidate)
        # and the bytes of that candidate are the bytes of the current history plus the records, as a history
        self.assertEqual(U.read_history_bytes(U.history_bytes(case.candidate))[0], case.candidate)


class Daily(AppendCommon):
    """C2-03."""

    def test_the_candidate_is_what_check_append_batch_accepts_for_the_prepared_day(self):
        c = X.day_case()
        self.assert_append_publication(c, "DAILY")
        self.assertEqual(c.pub.body["d"], D[2])
        self.assertEqual((c.pub.body["request_id"], c.pub.body["plan_hash"]), (None, None))
        self.assertEqual(c.candidate, O.check_append_batch(c.history, c.batch))
        # the records are the records of the batch, character for character
        self.assertEqual(X.cj(c.pub.body["records"]), X.cj(c.batch.body["records"]))
        self.assertEqual(len(c.pub.body["records"]), 1)
        self.assertEqual(c.pub.body["records"][0]["kind"], "APPLY")
        self.assertEqual(c.pub.body["records"][0]["d"], D[2])

    def test_a_day_that_is_not_prepared_is_refused_as_not_prepared(self):
        c = X.day_case()
        h, w = c.history, c.w
        again = T.day(h, D[1], w)                           # a day that is applied already
        self.assertEqual(again.status, "ALREADY_APPLIED")
        self.assertEqual(X.err(U.publish_day, h, D[1], w.series, w.sessions, w.ledger),
                         ("publication_refused", "source", "not_prepared"))
        bare = [r for r in w.ledger if r["record_id"] != "R2"]        # D2 has no decision row
        res = T.day(h, D[2], w, bare)
        self.assertEqual(res.status, "NO_COMMIT")
        self.assertEqual(X.err(U.publish_day, h, D[2], w.series, w.sessions, bare),
                         ("publication_refused", "source", "not_prepared"))

    def test_a_refusal_of_the_day_preparation_is_returned_as_it_is(self):
        c = X.day_case()
        h, w = c.history, c.w
        for d in ("2026-3-5", "2030-01-01", D[3], None, 5, ["x"]):
            with self.subTest(d=d):
                expected = X.err(O.prepare_history_day, h, d, w.series, w.sessions, w.ledger)
                self.assertEqual(X.err(U.publish_day, h, d, w.series, w.sessions, w.ledger), expected)
        expected = X.err(O.prepare_history_day, h, D[2], w.series, w.sessions, [{"x": 1}])
        self.assertEqual(X.err(U.publish_day, h, D[2], w.series, w.sessions, [{"x": 1}]), expected)
        expected = X.err(O.prepare_history_day, {"events": []}, D[2], w.series, w.sessions, w.ledger)
        self.assertEqual(X.err(U.publish_day, {"events": []}, D[2], w.series, w.sessions, w.ledger), expected)

    def test_the_inputs_are_not_changed(self):
        c = X.day_case()
        h, w = c.history, c.w
        ledger, sessions = X.deep(w.ledger), X.sessions_digest(w.sessions)
        U.publish_day(h, D[2], w.series, w.sessions, w.ledger)
        self.assertEqual((w.ledger, h), (ledger, c.history))
        self.assertEqual(X.sessions_digest(w.sessions), sessions)

    def test_a_later_day_extends_a_candidate_of_an_earlier_one(self):
        c = X.day_case()
        w = c.w
        w.ledger.append(P.obs("R3", D[3], 33.0))
        pub = U.publish_day(c.candidate, D[3], w.series, w.sessions, w.ledger)
        self.assertEqual(pub.body["expected"]["head_seq"], 2)
        self.assertEqual(pub.body["candidate_head_seq"], 3)
        self.assertEqual(U.check_publication(U.history_bytes(c.candidate), pub).head_seq, 3)


class Resolution(AppendCommon):
    """C2-04."""

    def test_the_candidate_is_the_one_of_the_confirmation(self):
        c = X.resolution_case()
        self.assert_append_publication(c, "RESOLUTION")
        self.assertEqual(c.conf.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(c.pub.body["request_id"], "q1")
        self.assertEqual(c.pub.body["plan_hash"], c.plan.plan_hash)
        self.assertIsNone(c.pub.body["d"])
        # the same records as the batch of the confirmation
        self.assertEqual(X.cj(c.pub.body["records"]), X.cj(c.conf.batch.body["records"]))
        self.assertEqual(c.candidate, O.check_append_batch(c.history, c.conf.batch))

    def test_a_plan_that_changes_nothing_is_refused_as_no_change(self):
        c = X.resolution_case()
        again = O.confirm_history_resolution_plan(c.plan, c.plan.plan_hash, c.candidate, c.w.sessions, c.ledger)
        self.assertEqual(again.status, "NO_CHANGE")
        self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, c.candidate, c.w.sessions, c.ledger),
                         ("publication_refused", "source", "no_change"))

    def test_a_refusal_of_the_confirmation_is_returned_as_it_is(self):
        c = X.resolution_case()
        args = (c.history, c.w.sessions, c.ledger)
        self.assertEqual(X.err(U.publish_resolution, c.plan, X.ZERO, *args),
                         ("history_plan_mismatch", "plan", None))
        self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                               list(c.w.ledger)), X.err(O.confirm_history_resolution_plan, c.plan, c.plan.plan_hash,
                                                        c.history, c.w.sessions, list(c.w.ledger)))
        data = c.plan.to_dict()
        data["basis"]["request_id"] = "other"
        forged = O.HistoryResolutionPlan.from_dict(data)
        self.assertEqual(X.err(U.publish_resolution, forged, forged.plan_hash, *args),
                         X.err(O.confirm_history_resolution_plan, forged, forged.plan_hash, *args))
        self.assertEqual(X.err(U.publish_resolution, c.plan.to_dict(), c.plan.plan_hash, *args)[:2],
                         ("history_plan_mismatch", "plan"))
        self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                               c.ledger + [P.obs("y", D[1], 21.0)]),
                         X.err(O.confirm_history_resolution_plan, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                               c.ledger + [P.obs("y", D[1], 21.0)]))

    def test_a_longer_history_than_the_plan_was_made_for_is_stale(self):
        c = X.resolution_case()
        longer = O.check_append_batch(c.history, T.day(c.history, D[2], c.w, c.w.ledger + [P.obs("R2", D[2], 31.0)]).batch)
        expected = X.err(O.confirm_history_resolution_plan, c.plan, c.plan.plan_hash, longer, c.w.sessions, c.ledger)
        self.assertEqual(expected[0], "history_plan_stale")
        self.assertEqual(X.err(U.publish_resolution, c.plan, c.plan.plan_hash, longer, c.w.sessions, c.ledger),
                         expected)


class Restart(AppendCommon):
    """C2-05."""

    def test_the_candidate_is_the_one_of_the_confirmation(self):
        c = X.restart_case()
        self.assert_append_publication(c, "RESTART")
        self.assertEqual(c.conf.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual((c.pub.body["request_id"], c.pub.body["plan_hash"]), ("q1", c.plan.plan_hash))
        self.assertEqual(len(c.pub.body["records"]), 1)
        self.assertEqual(c.pub.body["records"][0]["kind"], "RESTART_UNKNOWN")

    def test_a_plan_that_is_confirmed_against_its_own_candidate_is_refused_as_no_change(self):
        c = X.restart_case()
        self.assertEqual(RT.confirm_restart_plan(c.plan, c.plan.plan_hash, c.candidate, c.w.sessions, c.w.ledger).status,
                         "NO_CHANGE")
        self.assertEqual(X.err(U.publish_restart, c.plan, c.plan.plan_hash, c.candidate, c.w.sessions, c.w.ledger),
                         ("publication_refused", "source", "no_change"))

    def test_a_refusal_of_the_confirmation_is_returned_as_it_is(self):
        c = X.restart_case()
        args = (c.history, c.w.sessions, c.w.ledger)
        self.assertEqual(X.err(U.publish_restart, c.plan, X.ZERO, *args)[:2], ("history_plan_mismatch", "plan"))
        self.assertEqual(X.err(U.publish_restart, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                               c.w.ledger + [P.obs("y", D[1], 21.0)]),
                         X.err(RT.confirm_restart_plan, c.plan, c.plan.plan_hash, c.history, c.w.sessions,
                               c.w.ledger + [P.obs("y", D[1], 21.0)]))
        forged = X.R3.refreshed(c.plan, lambda b: b.update(request_id="zzz"))
        self.assertEqual(X.err(U.publish_restart, forged, forged.plan_hash, *args),
                         X.err(RT.confirm_restart_plan, forged, forged.plan_hash, *args))


class Restore(AppendCommon):
    """C2-06."""

    def test_a_restore_that_consumes_a_day_publishes_the_restore_record_and_the_made_records(self):
        c = X.restore_case(consume=True)
        self.assert_append_publication(c, "RESTORE")
        self.assertEqual(c.conf.status, "CONFIRMED_IN_MEMORY")
        kinds = [(r["kind"], r.get("d")) for r in c.pub.body["records"]]
        self.assertEqual(kinds, [("RECOVERY_RESTORE", None), ("APPLY", D[3]), ("APPLY", D[4])])
        restore = c.pub.body["records"][0]
        self.assertEqual([e["op"] for e in restore["replay"]], ["DROP", "CONSUME", "REAPPLY"])
        self.assertEqual((c.pub.body["request_id"], c.pub.body["plan_hash"]), ("c1-1", c.plan.plan_hash))
        # the consumed APPLY is a record that the plan made from the decision of D3 (it is not a copy of an old one)
        self.assertEqual(c.pub.body["records"][1]["seq"], len(c.history.events) + 1)

    def test_a_restore_without_a_consume_is_published_as_well(self):
        c = X.restore_case(consume=False)
        self.assert_append_publication(c, "RESTORE")
        self.assertEqual([r["kind"] for r in c.pub.body["records"]], ["RECOVERY_RESTORE", "APPLY"])
        self.assertEqual([e["op"] for e in c.pub.body["records"][0]["replay"]], ["DROP", "REAPPLY"])

    def test_a_plan_that_is_confirmed_against_its_own_candidate_is_refused_as_no_change(self):
        c = X.restore_case()
        w = c.w
        self.assertEqual(RS.confirm_restore_plan(c.plan, c.plan.plan_hash, c.candidate, w.sessions, w.ledger,
                                                 w.series).status, "NO_CHANGE")
        self.assertEqual(X.err(U.publish_restore, c.plan, c.plan.plan_hash, c.candidate, w.sessions, w.ledger,
                               w.series), ("publication_refused", "source", "no_change"))

    def test_a_refusal_of_the_confirmation_is_returned_as_it_is(self):
        c = X.restore_case()
        w = c.w
        args = (c.history, w.sessions, w.ledger, w.series)
        self.assertEqual(X.err(U.publish_restore, c.plan, X.ZERO, *args)[:2], ("history_plan_mismatch", "plan"))
        gone = X.P.make_series(dates=[d for d in D if d != D[3]])
        self.assertEqual(X.err(U.publish_restore, c.plan, c.plan.plan_hash, c.history, w.sessions, w.ledger, gone),
                         ("target_row_missing", "market", None))
        self.assertEqual(X.err(U.publish_restore, c.plan, c.plan.plan_hash, c.history, w.sessions, w.ledger, gone),
                         X.err(RS.confirm_restore_plan, c.plan, c.plan.plan_hash, c.history, w.sessions, w.ledger,
                               gone))

    def test_a_ledger_without_the_decision_of_the_consumed_day_is_not_published(self):
        c = X.restore_case()
        w = c.w
        other = [r for r in w.ledger if r["target_us_session_date"] != D[3]]
        self.assertLess(len(other), len(w.ledger))
        e = X.err(U.publish_restore, c.plan, c.plan.plan_hash, c.history, w.sessions, other, w.series)
        self.assertEqual(e, X.err(RS.confirm_restore_plan, c.plan, c.plan.plan_hash, c.history, w.sessions, other,
                                  w.series))
        self.assertNotEqual(e[0], "publication_refused")


if __name__ == "__main__":
    unittest.main()
