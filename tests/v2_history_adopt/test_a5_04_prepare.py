"""A5-08 the arguments, A5-09 what the diagnosis allows, A5-10 the trace of a migration, A5-11 the request ids, A5-12 the
values of the record and of the plan (all calculated here from the file, never by the code under test)."""
import datetime
import unittest

import a5_helpers as Z
from a5_helpers import D, G, H, V, X

NOT_ADOPTABLE = ("adoption_invalid", "data", "not_adoptable")


class Arguments(unittest.TestCase):
    def setUp(self):
        self.b, self.data, self.k = Z.new_world()

    def test_data_must_be_exactly_bytes(self):
        class Sub(bytes):
            pass
        for bad in (self.data.decode("utf-8"), bytearray(self.data), memoryview(self.data), None, Sub(self.data), 5):
            with self.subTest(type(bad).__name__):
                self.assertEqual(Z.err(Z.prep, bad, self.k), ("adoption_invalid", "data", "type"))

    def test_adopt_count_is_a_strict_positive_integer(self):
        for bad in (True, False, 0, -1, 1.0, 6.5, "6", None, [6]):
            with self.subTest(repr(bad)):
                self.assertEqual(Z.err(Z.prep, self.data, bad), ("adoption_invalid", "adopt_count", "type"))
        self.assertEqual(Z.prep(self.data, 6).status, "READY")

    def test_requested_at_is_an_aware_datetime(self):
        naive = datetime.datetime(2026, 11, 3, 1, 2, 3)
        out = Z.refusal(Z.prep, self.data, self.k, "ad1", naive)
        self.assertEqual((out[0], out[1], out[2]), ("InputError", "datetime_missing_timezone", "requested_at"))
        for bad in ("2026-11-03T01:02:03Z", None, 5, datetime.date(2026, 11, 3)):
            with self.subTest(repr(bad)):
                out = Z.refusal(Z.prep, self.data, self.k, "ad1", bad)
                self.assertEqual((out[0], out[1], out[2]), ("InputError", "datetime_invalid", "requested_at"))

    def test_request_id_must_have_the_form_of_a_record_id(self):
        for bad in ("", " x", "has space", 5, None, "x" * 500, b"ad1"):
            with self.subTest(repr(bad)[:20]):
                self.assertEqual(Z.err(Z.prep, self.data, self.k, bad), ("adoption_invalid", "request_id", "request_id"))

    def test_the_order_when_several_are_wrong(self):
        naive = datetime.datetime(2026, 11, 3)
        valid_file = X.history_file(X.ex_new())                          # VALID: refused later, at the diagnosis
        order = [
            (dict(data=None, k=0, rid="", when=naive), ("adoption_invalid", "data", "type")),
            (dict(data=self.data, k=0, rid="", when=naive), ("adoption_invalid", "adopt_count", "type")),
            (dict(data=valid_file, k=True, rid="", when=naive), ("adoption_invalid", "adopt_count", "type")),
        ]
        for kw, want in order:
            with self.subTest(want):
                self.assertEqual(Z.err(Z.A.prepare_prefix_adoption, kw["data"], kw["k"], kw["rid"], kw["when"]), want)
        out = Z.refusal(Z.A.prepare_prefix_adoption, self.data, self.k, "", naive)
        self.assertEqual((out[0], out[1]), ("InputError", "datetime_missing_timezone"))      # before the id
        self.assertEqual(Z.err(Z.A.prepare_prefix_adoption, valid_file, 3, "", Z.WHEN),
                         ("adoption_invalid", "request_id", "request_id"))                # before the diagnosis
        self.assertEqual(Z.err(Z.A.prepare_prefix_adoption, valid_file, 3, "ad1", Z.WHEN), NOT_ADOPTABLE)

    def test_a_non_utc_instant_is_written_as_utc_text(self):
        jst = datetime.timezone(datetime.timedelta(hours=9))
        plan = Z.prep(self.data, self.k, when=datetime.datetime(2026, 11, 3, 10, 2, 3, tzinfo=jst))
        self.assertEqual(plan.basis["requested_at"], "2026-11-03T01:02:03Z")
        self.assertEqual(plan.basis["candidate_record"]["requested_at"], "2026-11-03T01:02:03Z")

    def test_the_inputs_are_not_changed(self):
        before = bytes(self.data)
        Z.prep(self.data, self.k)
        self.assertEqual(self.data, before)


class DiagnosisStates(unittest.TestCase):
    def setUp(self):
        self.b, self.data, self.k = Z.new_world()

    def test_valid_no_valid_prefix_and_unreadable_are_not_adoptable(self):
        b = X.ex_new()
        broken_genesis = X.file_of(X.with_hash(b.events, 0))
        files = {"VALID": X.history_file(b), "NO_VALID_PREFIX": broken_genesis,
                 "UNREADABLE bad json": b"{not json", "UNREADABLE empty": b"", "UNREADABLE utf8": b"\xff\xfe\x00",
                 "UNREADABLE schema": X.file_of(b.events, schema_version=3),
                 "UNREADABLE core_sha": X.file_of(b.events, core_sha="0" * 40)}
        want = {"VALID": "VALID", "NO_VALID_PREFIX": "NO_VALID_PREFIX"}
        for name, data in files.items():
            with self.subTest(name):
                self.assertEqual(X.diagnose(data)["status"], want.get(name, "UNREADABLE"))
                for k in (1, 3, 7):
                    self.assertEqual(Z.err(Z.prep, data, k), NOT_ADOPTABLE)

    def test_a_schema_1_snapshot_with_a_damaged_tail_is_refused_as_schema_1(self):
        snap = X.v1_world(4).snap()
        data = X.v1_doc_file(X.with_hash(snap.events, 4))
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["schema_version"], d["verified"]["count"]), ("PREFIX_ONLY", 1, 4))
        self.assertEqual(Z.err(Z.prep, data, 4), ("adoption_invalid", "data", "schema_1"))
        self.assertEqual(Z.err(Z.prep, data, 3), ("adoption_invalid", "data", "schema_1"))       # before the count

    def test_the_count_must_be_the_diagnosis_count(self):
        self.assertEqual(X.diagnose(self.data)["verified"]["count"], self.k)
        for k in (self.k - 1, self.k + 1, 1, 100):
            with self.subTest(k):
                self.assertEqual(Z.err(Z.prep, self.data, k), ("adoption_invalid", "adopt_count", "count_mismatch"))
        self.assertEqual(Z.prep(self.data, self.k).status, "READY")

    def test_a_header_only_difference_adopts_every_record(self):
        events = self.b.events
        data = X.file_of(events, head_hash=Z.ZERO)
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["verified"]["count"], d["discarded"]["count"]), ("PREFIX_ONLY", 7, 0))
        plan = Z.prep(data, 7)
        self.assertEqual(plan.basis["discarded"], {"from_index": 7, "count": 0, "items": []})
        self.assertEqual(plan.basis["candidate_record"]["evidence"]["claimed_head_hash"], Z.ZERO)
        self.assertEqual(plan.basis["candidate_head_seq"], 7)
        V.validate_history(V.History.from_dict(plan.basis["candidate_history"]))

    def test_a_longest_prefix_that_is_not_the_one_a_shorter_search_would_find(self):
        # a restore window cut in the middle fails, a longer prefix passes: the diagnosis count is the longest one
        events = H.example_r1().events                               # RESTORE at 7, its records 8..10
        data = X.file_of(X.with_hash(events, 9))
        d = X.diagnose(data)
        self.assertEqual(d["status"], "PREFIX_ONLY")
        k = d["verified"]["count"]
        self.assertEqual(Z.err(Z.prep, data, k - 1)[2], "count_mismatch")
        self.assertEqual(Z.prep(data, k).basis["adopt_count"], k)


class MigrationTrace(unittest.TestCase):
    def setUp(self):
        self.m = X.ex_m()                                              # 0..6 moved records, 7 SCHEMA_MIGRATION
        self.m_empty = X.ex_m_empty()

    def test_example_m_with_only_the_migration_hash_broken(self):
        data = X.file_of(X.with_hash(self.m.events, 7))
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["verified"]["count"], d["verified"]["migrated"]), ("PREFIX_ONLY", 2, False))
        self.assertEqual(d["discarded"]["items"][-1]["kind"], "SCHEMA_MIGRATION")
        self.assertEqual(Z.err(Z.prep, data, 2), ("adoption_invalid", "data", "migration_discarded"))

    def test_example_m_with_the_migration_kind_unreadable_is_found_by_the_origin_behind_it(self):
        events = Z.deep(self.m.events)
        events[7]["kind"] = "?"
        data = X.file_of(events)
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["verified"]["count"], d["verified"]["migrated"]), ("PREFIX_ONLY", 2, False))
        self.assertNotIn("SCHEMA_MIGRATION", [i["kind"] for i in d["discarded"]["items"]])
        self.assertTrue(any(e.get("origin") for e in events[2:7]))
        self.assertEqual(Z.err(Z.prep, data, 2), ("adoption_invalid", "data", "migration_discarded"))

    def test_the_empty_world_example_with_the_migration_alone_on_the_discarded_side(self):
        events = self.m_empty.events
        self.assertEqual(events[-1]["kind"], "SCHEMA_MIGRATION")
        data = X.file_of(X.with_hash(events, len(events) - 1))
        d = X.diagnose(data)
        self.assertEqual((d["verified"]["count"], d["discarded"]["count"], d["verified"]["migrated"]),
                         (len(events) - 1, 1, False))
        self.assertEqual(Z.err(Z.prep, data, len(events) - 1), ("adoption_invalid", "data", "migration_discarded"))

    def test_nothing_readable_on_the_discarded_side_is_not_judged(self):
        # the only trace is a migration whose kind is unreadable and no record behind it carries an origin: it cannot be
        # found (design 5.2: it stays in the plan's discarded block as "?")
        events = Z.deep(self.m_empty.events)
        events[-1]["kind"] = "?"
        data = X.file_of(events)
        plan = Z.prep(data, len(events) - 1)
        self.assertEqual([i["kind"] for i in plan.basis["discarded"]["items"]], ["?"])

    def test_a_migrated_prefix_may_be_adopted_when_its_tail_is_damaged(self):
        b = X.ex_m()
        b.apply(D[5], 30.0)
        b.apply(D[6], 31.0)
        data, k = Z.damaged_last(b)
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["verified"]["count"], d["verified"]["migrated"]), ("PREFIX_ONLY", k, True))
        plan = Z.prep(data, k)
        self.assertEqual(plan.status, "READY")
        chk = V.validate_history(V.History.from_dict(plan.basis["candidate_history"]))
        self.assertTrue(chk.migrated)
        self.assertEqual(plan.basis["candidate_record"]["parent_seq"], k - 1)

    def test_a_migrated_prefix_with_a_damaged_moved_record_is_not_adopted_when_the_trace_is_behind(self):
        # the migration record is in the middle of the prefix; the damage is in a record after it: adoptable
        b = X.ex_m()
        b.apply(D[5], 30.0)
        b.apply(D[6], 31.0)
        data, k = Z.damaged_at(b, 9)
        self.assertEqual(Z.prep(data, X.diagnose(data)["verified"]["count"]).status, "READY")

    def test_a_trace_on_the_discarded_side_does_not_matter_when_the_prefix_keeps_its_migration(self):
        b = X.ex_m()
        b.apply(D[5], 30.0)
        b.apply(D[6], 31.0)
        events = Z.deep(b.events)
        events[-1]["origin"] = {"x": 1}              # the hash no longer fits: the tail is discarded, with a trace in it
        data = X.file_of(events)
        d = X.diagnose(data)
        k = d["verified"]["count"]
        self.assertEqual((d["status"], k, d["verified"]["migrated"], d["discarded"]["count"]),
                         ("PREFIX_ONLY", len(events) - 1, True, 1))
        self.assertEqual(Z.prep(data, k).status, "READY")

    def test_an_origin_that_is_not_null_counts_whatever_it_is(self):
        b = X.ex_new()
        for name, value, trace in (("null", None, False), ("zero", 0, True), ("empty dict", {}, True),
                                   ("empty text", "", True), ("false", False, True), ("dict", {"x": 1}, True)):
            with self.subTest(name):
                events = Z.deep(b.events)
                events[5]["origin"] = value
                data = X.file_of(events)
                d = X.diagnose(data)
                self.assertEqual((d["status"], d["verified"]["count"]), ("PREFIX_ONLY", 5))
                if trace:
                    self.assertEqual(Z.err(Z.prep, data, 5), ("adoption_invalid", "data", "migration_discarded"))
                else:
                    self.assertEqual(Z.prep(data, 5).status, "READY")

    def test_the_origin_of_a_record_that_is_not_a_dict_is_not_read(self):
        events = Z.deep(X.ex_new().events)
        doc = H.header(events[:5])
        doc["events"] = events[:5] + [["origin", 5], 7]
        data = X.doc_bytes(doc)
        d = X.diagnose(data)
        self.assertEqual((d["status"], d["verified"]["count"], [i["kind"] for i in d["discarded"]["items"]]),
                         ("PREFIX_ONLY", 5, ["?", "?"]))
        self.assertEqual(Z.prep(data, 5).status, "READY")


class RequestIds(unittest.TestCase):
    def test_every_id_of_the_physical_prefix_is_taken_even_when_the_record_is_superseded(self):
        b = H.example_r()                                              # three restores; many records are superseded
        n = len(b.events)
        data, _ = Z.damaged_at(b, n - 1)
        k = 18                                                         # the last restore (18) and its batch are cut as a whole
        self.assertEqual(b.events[k]["kind"], "RECOVERY_RESTORE")
        self.assertEqual(X.diagnose(data)["verified"]["count"], k)
        prefix = Z.prefix_events(data, k)
        chain = set(H.chain_of(prefix))
        ids = {e["request_id"] for e in prefix if e.get("request_id") is not None}
        self.assertGreaterEqual(len(ids), 4)
        outside = {e["request_id"] for i, e in enumerate(prefix) if i not in chain and e.get("request_id")}
        self.assertTrue(outside - {prefix[s].get("request_id") for s in chain})
        for rid in sorted(ids):
            with self.subTest(rid):
                self.assertEqual(Z.err(Z.prep, data, k, rid), ("history_request_conflict", "request_id", None))
        self.assertEqual(Z.prep(data, k, "fresh-id").status, "READY")

    def test_the_kinds_of_the_records_whose_id_is_taken(self):
        for name, b, want_k in (("migrated", X.ex_m(), None), ("restart", X.ex_u(), None), ("restore", H.example_r1(), 7)):
            with self.subTest(name):
                b2 = H.HB(world=b.w, events=b.events)
                b2.apply(D[8], 36.0) if name != "restore" else None
                data, k = Z.damaged_last(b2)
                k = want_k or k
                self.assertEqual(X.diagnose(data)["verified"]["count"], k)
                prefix = Z.prefix_events(data, k)
                kinds = set()
                for e in prefix:
                    rid = e.get("request_id")
                    if rid:
                        kinds.add(e["kind"])
                        self.assertEqual(Z.err(Z.prep, data, k, rid), ("history_request_conflict", "request_id", None))
                self.assertTrue(kinds, name)

    def test_the_readable_ids_of_the_discarded_side_are_taken(self):
        b = X.ex_new()
        b.declare(D[7], "qd")
        b.restart(D[9], "qs")
        data, k = Z.damaged_at(b, 6)
        items = X.diagnose(data)["discarded"]["items"]
        ids = [i["request_id"] for i in items if i["request_id"]]
        self.assertEqual(ids, ["qd", "qs"])
        for rid in ids:
            with self.subTest(rid):
                self.assertEqual(Z.err(Z.prep, data, k, rid), ("history_request_conflict", "request_id", None))
        self.assertEqual(Z.prep(data, k, "qx").status, "READY")

    def test_an_unreadable_id_of_the_discarded_side_is_not_used(self):
        b = X.ex_new()
        b.declare(D[7], "qd")
        events = Z.deep(b.events)
        events[7]["request_id"] = {"x": 1}                             # unreadable: not a record id
        data = X.file_of(X.with_hash(events, 6))
        k = X.diagnose(data)["verified"]["count"]
        self.assertEqual(k, 6)
        items = X.diagnose(data)["discarded"]["items"]
        self.assertEqual([i["request_id"] for i in items], [None, None])
        self.assertEqual(Z.prep(data, k, "qd").status, "READY")             # the id "qd" is not named by anything readable

    def test_the_id_of_the_adoption_may_not_be_the_id_of_a_discarded_record_only_by_its_readable_form(self):
        events = Z.deep(X.ex_new().events)
        events[6]["request_id"] = "not a valid id"                     # has spaces: unreadable
        data = X.file_of(events[:6] + [events[6]])
        k = X.diagnose(data)["verified"]["count"]
        self.assertEqual(Z.prep(data, k, "ok-id").status, "READY")


class Values(unittest.TestCase):
    def check(self, data, k, rid="ad1", when=Z.WHEN, when_text=Z.WHEN_TEXT):
        plan = Z.prep(data, k, rid, when)
        want = Z.expected_basis(data, k, rid, when_text)
        basis = plan.basis
        self.assertEqual(len(basis), 21)
        self.assertEqual(set(basis), set(want))
        for key in want:
            self.assertEqual(basis[key], want[key], key)
        self.assertEqual(plan.plan_hash, Z.sha_text(Z.cj(basis)))
        self.assertEqual(plan.to_dict(), {"basis": want, "plan_hash": Z.sha_text(Z.cj(want))})
        rec = basis["candidate_record"]
        self.assertEqual(set(rec), {"kind", "seq", "parent_seq", "parent_hash", "evidence", "request_id", "request_hash",
                                    "request_basis", "reason_code", "requested_at", "state_after", "event_hash"})
        self.assertEqual(rec, Z.record_of(Z.prefix_events(data, k), Z.evidence_of(data, k), rid, when_text))
        return plan

    def test_the_new_world(self):
        b, data, k = Z.new_world()
        plan = self.check(data, k)
        self.assertEqual(plan.basis["operation"], "soxl-v2-history-prefix-adoption-plan/1")
        self.assertEqual(plan.basis["reason_code"], "ADOPT_VERIFIED_PREFIX")
        self.assertEqual(plan.status, "READY")
        self.assertIs(plan.committed, False)

    def test_other_damage_positions_and_sizes(self):
        b = X.ex_new()
        for index in (1, 2, 4, 6):
            with self.subTest(index):
                data, k = Z.damaged_at(b, index)
                self.assertEqual(X.diagnose(data)["verified"]["count"], k)
                self.check(data, k, rid="id-%d" % index)

    def test_histories_with_every_kind_of_record_before_the_damage(self):
        for name, builder, want_k in (("restart", X.ex_u(), None), ("restore", H.example_r1(), 7),
                                      ("restore x3", H.example_r(), 18), ("migrated", X.ex_m(), None)):
            with self.subTest(name):
                b = H.HB(world=builder.w, events=builder.events)
                b.apply(D[9], 38.0) if name in ("restart", "migrated") else None
                data, k = Z.damaged_last(b)
                k = want_k or k                       # a damaged record inside a restore batch cuts the whole batch
                self.assertEqual(X.diagnose(data)["verified"]["count"], k)
                self.check(data, k, rid="id-%s" % name.replace(" ", ""))

    def test_the_claimed_values_come_from_the_header_when_their_form_is_right(self):
        b = X.ex_new()
        events = b.events
        cases = {
            "head_seq other": ({"head_seq": 99}, 99, None), "head_seq negative": ({"head_seq": -5}, -5, None),
            "head_seq bool": ({"head_seq": True}, None, None), "head_seq text": ({"head_seq": "6"}, None, None),
            "head_seq null": ({"head_seq": None}, None, None),
            "head_hash zeros": ({"head_hash": Z.ZERO}, None, Z.ZERO),
            "head_hash upper-case": ({"head_hash": "A" * 64}, None, None), "head_hash text": ({"head_hash": "zz"}, None, None),
            "head_hash int": ({"head_hash": 5}, None, None),
        }
        for name, (edit, seq, hsh) in cases.items():
            with self.subTest(name):
                data = X.file_of(events, **edit)
                k = X.diagnose(data)["verified"]["count"]
                plan = self.check(data, k, rid="id-x")
                ev = plan.basis["candidate_record"]["evidence"]
                if "head_seq" in edit:
                    self.assertEqual(ev["claimed_head_seq"], seq)
                else:
                    self.assertEqual(ev["claimed_head_seq"], events[-1]["seq"])
                if "head_hash" in edit:
                    self.assertEqual(ev["claimed_head_hash"], hsh)

    def test_claimed_head_seq_is_not_the_verified_head_seq(self):
        b, data, k = Z.new_world()
        plan = Z.prep(data, k)
        ev = plan.basis["candidate_record"]["evidence"]
        self.assertEqual(plan.basis["prefix_head_seq"], k - 1)
        self.assertEqual(ev["claimed_head_seq"], k)                    # the header of the damaged file says 6
        self.assertNotEqual(ev["claimed_head_seq"], plan.basis["prefix_head_seq"])
        self.assertEqual(ev["discarded_from_seq"], k)
        self.assertEqual(ev["raw_sha256"], Z.sha_bytes(data))
        self.assertEqual(ev["raw_size"], len(data))

    def test_the_plan_is_independent_of_how_the_instant_is_written(self):
        b, data, k = Z.new_world()
        when = datetime.datetime(2026, 11, 3, 1, 2, 3, 250000, tzinfo=datetime.timezone.utc)
        text = Z.requested_text(when)                                  # the existing function of the recovery stage
        utc = Z.prep(data, k, when=when)
        self.assertEqual(utc.basis["requested_at"], text)
        self.assertEqual(utc.basis, Z.expected_basis(data, k, "ad1", text))

    def test_the_candidate_is_checked_and_has_the_state_of_the_prefix(self):
        b, data, k = Z.new_world()
        plan = Z.prep(data, k)
        cand = V.History.from_dict(plan.basis["candidate_history"])
        chk = V.validate_history(cand)
        self.assertEqual((chk.head_seq, chk.head_hash, chk.state_digest, cand.digest),
                         (plan.basis["candidate_head_seq"], plan.basis["candidate_head_hash"],
                          plan.basis["candidate_state_digest"], plan.basis["candidate_digest"]))
        self.assertEqual(plan.basis["candidate_state_digest"], plan.basis["prefix_state_digest"])
        self.assertEqual(cand.current_state, Z.prefix_events(data, k)[-1]["state_after"])
        self.assertEqual(cand.events[:k], Z.prefix_events(data, k))
        self.assertEqual(G.diagnose_history_bytes(Z.candidate_bytes(data, k)).status, "VALID")

    def test_the_same_input_gives_the_same_plan(self):
        b, data, k = Z.new_world()
        self.assertEqual(Z.prep(data, k), Z.prep(data, k))
        self.assertNotEqual(Z.prep(data, k, "ad1"), Z.prep(data, k, "ad2"))
        self.assertNotEqual(Z.prep(data, k).plan_hash,
                            Z.prep(data, k, when=datetime.datetime(2026, 11, 3, 1, 2, 4, tzinfo=datetime.timezone.utc)).plan_hash)

    def test_the_request_hash_ignores_the_time_and_the_basis_does_not(self):
        b, data, k = Z.new_world()
        a = Z.prep(data, k)
        c = Z.prep(data, k, when=datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc))
        self.assertEqual(a.basis["request_hash"], c.basis["request_hash"])
        self.assertNotEqual(a.plan_hash, c.plan_hash)


if __name__ == "__main__":
    unittest.main()
