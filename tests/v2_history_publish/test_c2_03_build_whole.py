"""C2-07 (GENESIS), C2-08 (MIGRATION), C2-09 (ADOPTION), C2-10 (P-01, the dynamic part) and the dynamic part of C2-15
(P-02): the builders that carry the whole candidate, and the ways that no builder makes a publication from a history that
only passed the checker."""
import json
import unittest

import c2_helpers as X

U, V, AD, RS = X.U, X.V, X.AD, X.RS
D, P, H, C1 = X.D, X.P, X.H, X.C1


class Genesis(unittest.TestCase):
    """C2-07."""

    def test_a_create_publication_of_a_history_that_is_only_the_genesis(self):
        c = X.genesis_case()
        body = c.pub.body
        self.assertEqual((body["mode"], body["source"]), ("CREATE", "GENESIS"))
        self.assertIsNone(body["expected"])
        self.assertIsNone(body["records"])
        self.assertEqual(body["candidate_history"], c.candidate.to_dict())
        self.assertEqual([e["kind"] for e in body["candidate_history"]["events"]], ["GENESIS"])
        self.assertEqual(body["candidate_head_seq"], 0)
        self.assertEqual(c.check(), c.candidate)
        self.assertEqual(c.candidate, V.make_history_genesis(c.w.start_after, c.w.sessions))

    def test_the_refusals_of_the_genesis_are_returned_as_they_are(self):
        w = X.P.World()
        for start in ("2026-3-3", "2000-01-01", None, 5):
            with self.subTest(start=start):
                expected = X.err(V.make_history_genesis, start, w.sessions)
                self.assertEqual(X.err(U.publish_genesis, start, w.sessions), expected)
        self.assertEqual(X.err(U.publish_genesis, w.start_after, {}), X.err(V.make_history_genesis, w.start_after, {}))


class Migration(unittest.TestCase):
    """C2-08."""

    @classmethod
    def setUpClass(cls):
        cls.c = X.migration_case()

    def args(self, **over):
        c = self.c
        a = dict(plan=c.plan, plan_hash=c.plan.plan_hash, data=c.data, rs=c.rs, sessions=c.w.sessions,
                 ledger=c.ledger)
        a.update(over)
        return (a["plan"], a["plan_hash"], a["data"], a["rs"], a["sessions"], a["ledger"])

    def test_a_create_publication_from_the_bytes_of_the_v1_snapshot(self):
        c = self.c
        body = c.pub.body
        self.assertEqual((body["mode"], body["source"]), ("CREATE", "MIGRATION"))
        self.assertEqual(body["source_v1"], X.raw_of(c.data))
        self.assertEqual((body["request_id"], body["plan_hash"]), ("mig-1", c.plan.plan_hash))
        self.assertEqual(body["candidate_history"], c.candidate.to_dict())
        self.assertIsNone(body["expected"])
        self.assertEqual(c.check(), c.candidate)

    def test_the_identity_is_that_of_the_received_bytes_even_when_they_are_not_canonical(self):
        c = self.c
        spaced = json.dumps(json.loads(c.data.decode("utf-8")), indent=1).encode("utf-8")
        self.assertNotEqual(spaced, c.data)
        pub = U.publish_migration(*self.args(data=spaced))
        self.assertEqual(pub.body["source_v1"], X.raw_of(spaced))
        self.assertNotEqual(pub.body["source_v1"], X.raw_of(c.data))
        self.assertEqual(U.check_publication(None, pub, spaced), c.candidate)
        self.assertEqual(X.err(U.check_publication, None, pub, c.data), ("publication_stale", "current", "source_v1"))

    def test_the_bytes_are_read_as_the_local_store_reads_them(self):
        data = self.c.data
        cases = {"bom": (b"\xef\xbb\xbf" + data, "json"), "not utf-8": (b"\xff\xfe\x00", "utf8"),
                 "cut": (data[:-5], "json"), "empty": (b"", "json"), "a list": (b"[]", None),
                 "duplicate key": (b'{"a":1,"a":2}', "json")}
        for name, (blob, rule) in cases.items():
            with self.subTest(name=name):
                code = X.err(U.publish_migration, *self.args(data=blob))
                self.assertEqual(code[:2], ("snapshot_invalid", "snapshot"))
                if rule:
                    self.assertEqual(code[2], rule)
        for bad in ("text", bytearray(data), memoryview(data), None, 7):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.publish_migration, *self.args(data=bad)),
                                 ("snapshot_invalid", "snapshot", "type"))

    def test_a_snapshot_that_is_valid_text_but_not_a_valid_snapshot_is_refused(self):
        doc = json.loads(self.c.data.decode("utf-8"))
        doc["head_hash"] = "0" * 64
        code = X.err(U.publish_migration, *self.args(data=json.dumps(doc).encode("utf-8")))
        self.assertEqual(code[:2], ("snapshot_invalid", "snapshot"))

    def test_the_refusals_of_the_confirmation_are_returned_as_they_are(self):
        c = self.c
        self.assertEqual(X.err(U.publish_migration, *self.args(plan_hash=X.ZERO)),
                         ("migration_plan_mismatch", "plan", None))
        other_w, other_snap, other_rs, other_ledger, _ = H.example_m_world()
        other_w.apply(D[5], 30.0, "R5")
        other = X.encode_snapshot(other_w.snap()).encode("utf-8")
        expected = X.err(V.confirm_migration_plan, c.plan, c.plan.plan_hash, other_w.snap(), c.rs, c.w.sessions,
                         c.ledger)
        self.assertEqual(expected[0], "migration_plan_stale")
        self.assertEqual(X.err(U.publish_migration, *self.args(data=other)), expected)
        self.assertEqual(X.err(U.publish_migration, *self.args(ledger=c.ledger[:-1])),
                         X.err(V.confirm_migration_plan, c.plan, c.plan.plan_hash, c.snap, c.rs, c.w.sessions,
                               c.ledger[:-1]))

    def test_the_v1_bytes_are_checked_before_the_confirmation_reads_the_other_inputs(self):
        # a v1 text that is wrong is a snapshot refusal even when the plan hash is wrong as well
        code = X.err(U.publish_migration, *self.args(data=b"\xff", plan_hash=X.ZERO))
        self.assertEqual(code, ("snapshot_invalid", "snapshot", "utf8"))


class Adoption(unittest.TestCase):
    """C2-09 and the dynamic part of C2-15."""

    @classmethod
    def setUpClass(cls):
        cls.c = X.adoption_case()

    def test_a_replace_publication_whose_expected_identity_is_computed_from_the_bytes(self):
        c = self.c
        body = c.pub.body
        self.assertEqual((body["mode"], body["source"]), ("REPLACE", "ADOPTION"))
        self.assertEqual(body["expected"], X.raw_of(c.data))                    # hashlib, in the test
        self.assertEqual((body["request_id"], body["plan_hash"]), ("ad1", c.plan.plan_hash))
        self.assertEqual(body["candidate_history"], c.candidate.to_dict())
        self.assertIsNone(body["records"])
        self.assertIsNone(body["source_v1"])
        self.assertEqual(c.conf.status, "CONFIRMED_IN_MEMORY")
        self.assertEqual(c.check(), c.candidate)

    def test_the_expected_identity_is_not_copied_from_the_plan(self):
        # the identity in the plan and the identity of the bytes agree here; the publication states the bytes'
        c = self.c
        basis = c.plan.basis
        self.assertEqual((basis["raw_sha256"], basis["raw_size"]), (X.raw_of(c.data)["raw_sha256"], len(c.data)))
        self.assertEqual(set(c.pub.body["expected"]), {"raw_sha256", "raw_size"})

    def test_a_plan_that_is_confirmed_against_its_own_candidate_is_refused_as_no_change(self):
        c = self.c
        cand_bytes = U.history_bytes(c.candidate)
        self.assertEqual(AD.confirm_prefix_adoption(c.plan, c.plan.plan_hash, cand_bytes).status, "NO_CHANGE")
        self.assertEqual(X.err(U.publish_adoption, c.plan, c.plan.plan_hash, cand_bytes),
                         ("publication_refused", "source", "no_change"))

    def test_the_refusals_of_the_confirmation_are_returned_as_they_are(self):
        c = self.c
        self.assertEqual(X.err(U.publish_adoption, c.plan, X.ZERO, c.data)[:2], ("history_plan_mismatch", "plan"))
        other = X.A5.damaged_at(c.builder, 4)[0]
        expected = X.err(AD.confirm_prefix_adoption, c.plan, c.plan.plan_hash, other)
        self.assertEqual(X.err(U.publish_adoption, c.plan, c.plan.plan_hash, other), expected)
        for bad in ("text", bytearray(c.data), None):
            with self.subTest(bad=type(bad).__name__):
                self.assertEqual(X.err(U.publish_adoption, c.plan, c.plan.plan_hash, bad),
                                 X.err(AD.confirm_prefix_adoption, c.plan, c.plan.plan_hash, bad))

    def test_the_body_holds_nothing_of_the_discarded_part_or_the_diagnosis(self):
        c = self.c
        body = c.pub.body
        for key in list(body) + list(body["expected"]):
            self.assertNotIn("discard", key.lower())
            self.assertNotIn("diagnos", key.lower())
        text = X.cj(body)
        basis = c.plan.basis
        self.assertNotIn(basis["diagnosis_digest"], text)
        self.assertNotIn(X.cj(basis["discarded"]), text)
        self.assertNotIn('"items"', text)
        # the summary and the repr name neither
        shown = json.dumps(c.pub.summary()) + repr(c.pub)
        self.assertNotIn("discard", shown.lower())
        self.assertNotIn("diagnos", shown.lower())

    def test_a_plan_that_names_other_bytes_is_not_published_whatever_its_status_says(self):
        c = self.c
        # a forged plan: another raw identity, with its hash written again, is refused by the confirmation
        forged = X.A5.refreshed(c.plan, lambda d: d["basis"].update(raw_sha256="1" * 64))
        self.assertEqual(X.err(U.publish_adoption, forged, forged.plan_hash, c.data)[:1],
                         X.err(AD.confirm_prefix_adoption, forged, forged.plan_hash, c.data)[:1])
        self.assertNotEqual(X.err(U.publish_adoption, forged, forged.plan_hash, c.data)[0], "publication_refused")


class Verified(unittest.TestCase):
    """C2-10 (P-01): a history that the checker accepts and the plan refuses is not made a publication."""

    @classmethod
    def setUpClass(cls):
        cls.b = C1.s_gap()
        cls.b.w.ledger.append(P.obs("X5", D[5], 50.0))
        cls.w = cls.b.w
        cls.bad_entries = [("REPLAY", 2), ("REAPPLY", 3), (C1.CONSUME, D[5])]
        cls.bad = H.history_of(C1.oracle(cls.b, 1, cls.bad_entries, "c1-x", D[7]))
        cls.good_entries = [("DROP", 2), (C1.CONSUME, D[2]), (C1.CONSUME, D[3]), ("REAPPLY", 3)]
        cls.good = C1.plan(cls.b, 1, cls.good_entries, D[7])

    def publish(self, plan, plan_hash=None, history=None):
        w = self.w
        return U.publish_restore(plan, plan.plan_hash if plan_hash is None else plan_hash,
                                 self.b.history() if history is None else history, w.sessions, w.ledger, w.series)

    def test_the_division_of_the_work_holds_the_checker_accepts_the_plan_refuses(self):
        self.assertEqual(V.validate_history(self.bad).head_seq, 7)
        self.assertEqual(X.err(C1.plan, self.b, 1, self.bad_entries, D[7]),
                         ("restore_invalid", "ops", "restore_consume_not_released"))

    def test_a_correct_plan_on_the_same_base_is_published(self):
        pub = self.publish(self.good)
        self.assertEqual(pub.body["source"], "RESTORE")
        self.assertEqual(pub.body["records"][0]["kind"], "RECOVERY_RESTORE")

    def test_a_plan_whose_basis_is_rewritten_to_that_history_with_its_hash_written_again_is_refused(self):
        base = self.b.history()
        chk = V.validate_history(self.bad)
        data = self.good.to_dict()
        basis = data["basis"]
        n = len(base.events)
        rewritten = {"candidate_history": self.bad.to_dict(), "candidate_digest": self.bad.digest,
                     "candidate_state_digest": chk.state_digest, "candidate_records": self.bad.events[n:]}
        touched = [k for k in rewritten if k in basis]
        self.assertTrue({"candidate_history", "candidate_digest"} <= set(touched))
        for key in touched:
            basis[key] = rewritten[key]
        forged = RS.RestorePlan.from_dict({"basis": basis, "plan_hash": X.sha(X.cj(basis).encode("utf-8"))})
        e = X.err(self.publish, forged)
        self.assertEqual(e[:2], ("history_plan_mismatch", None) if e[1] is None else e[:2])
        self.assertEqual(e[0], "history_plan_mismatch")

    def test_a_confirm_result_object_in_place_of_a_plan_is_refused(self):
        res = RS.RestoreConfirmResult("CONFIRMED_IN_MEMORY", self.bad, X.ZERO)
        self.assertEqual(X.err(self.publish, res, X.ZERO)[0], "history_plan_mismatch")

    def test_there_are_seven_builders_and_none_takes_a_history_a_result_or_a_dict(self):
        import inspect
        names = sorted(n for n in dir(U) if n.startswith("publish_"))
        self.assertEqual(names, ["publish_adoption", "publish_day", "publish_genesis", "publish_migration",
                                 "publish_resolution", "publish_restart", "publish_restore"])
        for name in names:
            params = list(inspect.signature(getattr(U, name)).parameters)
            for p in params:
                self.assertNotIn(p, ("candidate", "result", "confirm_result", "publication", "body", "data_dict",
                                     "history_dict"), name)
        self.assertEqual(list(inspect.signature(U.publish_restore).parameters),
                         ["plan", "confirmed_plan_hash", "history", "sessions", "raw_observations", "series"])
        self.assertEqual(list(inspect.signature(U.publish_day).parameters),
                         ["history", "d", "series", "sessions", "raw_observations"])
        self.assertEqual(list(inspect.signature(U.publish_adoption).parameters),
                         ["plan", "confirmed_plan_hash", "data"])
        self.assertFalse(hasattr(U, "publish_history"))
        self.assertFalse(hasattr(U, "from_dict"))

    def test_the_history_the_checker_accepts_is_accepted_by_check_publication_only_if_a_value_is_made_by_hand(self):
        """C2-10 (c), a characterisation: check_publication is a check of the form of a value and of the current bytes,
        not a confirmation. A value made with the private constructor outside the builders (which the range test forbids
        in the runtime) is accepted if its form, its hash and the current bytes agree, even when its candidate is a
        history that only passed the checker. This is why the private constructor is called in build.py only, and why
        C-3 takes only a value that a builder returned."""
        base = self.b.history()
        bchk = V.validate_history(base)
        chk = V.validate_history(self.bad)
        n = len(base.events)
        body = {"operation": "soxl-v2-history-publication/1", "mode": "APPEND", "source": "RESTORE", "d": None,
                "request_id": "c1-x", "plan_hash": X.ZERO,
                "expected": {"head_seq": bchk.head_seq, "head_hash": bchk.head_hash,
                             "history_digest": bchk.history_digest},
                "source_v1": None, "records": self.bad.events[n:], "candidate_history": None,
                "candidate_head_seq": chk.head_seq, "candidate_head_hash": chk.head_hash,
                "candidate_digest": self.bad.digest, "candidate_state_digest": chk.state_digest}
        by_hand = U.HistoryPublication._make(body)
        self.assertEqual(U.check_publication(X.file_bytes(base), by_hand), self.bad)
        # whereas no builder gives this value for these inputs
        self.assertNotEqual(self.publish(self.good), by_hand)


class NoAlias(unittest.TestCase):
    def test_the_builders_make_different_values_for_different_sources(self):
        hashes = {c.pub.publication_hash for c in X.every_case()}
        self.assertEqual(len(hashes), 7)


if __name__ == "__main__":
    unittest.main()
