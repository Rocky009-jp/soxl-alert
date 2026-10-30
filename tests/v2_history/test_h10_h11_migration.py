"""H-10 conversion of S1 + S3-A into schema 2 (design 5.2-5.7) and the reverse check through the unchanged S1 and
S3-A checkers; H-11 refusals when preparing a plan and when a migrated history is damaged."""
import unittest
from unittest import mock

import h_helpers as H
from h_helpers import D, V

import v2_history.migration as migration_module
from v2_persistence.codec import encode_snapshot, sha256_text
from v2_persistence.events import APPLY_KEYS
from v2_recovery import validate_resolutions as real_validate_resolutions
from v2_recovery.common import record_hash_of as real_record_hash_of
from v2_persistence.recompute import validate_snapshot as real_validate_snapshot

CONTENT = ("d", "confirmed_inputs", "input_hash", "skipped_sessions", "transition_result", "state_after")


class ExampleM(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = H.example_m_world()
        self.h = H.migrate(self.w, self.snap, self.rs, self.ledger, self.check_d)
        self.ev = self.h.events

    def test_the_records_follow_the_designs_table(self):
        self.assertEqual([e["kind"] for e in self.ev],
                         ["GENESIS", "APPLY", "ACK", "APPLY", "DECLARE_MISSING", "APPLY", "ACK", "SCHEMA_MIGRATION"])
        mig = self.ev[7]
        self.assertEqual([(m["v1_seq"], m["seq"]) for m in mig["event_map"]], [(0, 0), (1, 1), (2, 3), (3, 5)])
        self.assertEqual([(m["resolution_seq"], m["seq"]) for m in mig["resolution_map"]], [(1, 2), (2, 4), (3, 6)])
        self.assertEqual(sorted(mig), sorted(["kind", "seq", "parent_seq", "parent_hash", "source",
                                              "source_resolutions", "event_map", "resolution_map", "request_id",
                                              "request_hash", "request_basis", "reason_code", "requested_at",
                                              "ledger_digest", "state_after", "event_hash"]))
        self.assertEqual(mig["reason_code"], "MIGRATE_SCHEMA_1")
        self.assertEqual(mig["state_after"], self.snap.current_state)

    def test_hashes_of_untouched_events_equal_the_v1_hashes(self):
        v1 = self.snap.events
        self.assertEqual(self.ev[0]["event_hash"], v1[0]["event_hash"])
        self.assertEqual(self.ev[1]["event_hash"], v1[1]["event_hash"])       # nothing was inserted before it
        self.assertNotEqual(self.ev[3]["event_hash"], v1[2]["event_hash"])    # an ACK now stands before it
        self.assertEqual([m["v1_event_hash"] for m in self.ev[7]["event_map"]], [e["event_hash"] for e in v1])

    def test_apply_content_is_not_changed_by_one_byte(self):
        for v1_seq, v2_seq in ((1, 1), (2, 3), (3, 5)):
            with self.subTest(v1_seq):
                a, b = self.snap.events[v1_seq], self.ev[v2_seq]
                self.assertEqual(sorted(b), sorted(APPLY_KEYS))
                for key in CONTENT:
                    self.assertEqual(H.cj(a[key]), H.cj(b[key]), key)
        self.assertEqual(H.cj(self.snap.events[0]), H.cj(dict(self.ev[0])))

    def test_resolution_records_carry_their_content_origin_and_unchanged_requests(self):
        pairs = ((1, 2), (2, 4), (3, 6))
        for res_seq, v2_seq in pairs:
            with self.subTest(res_seq):
                a, b = self.rs.records[res_seq - 1], self.ev[v2_seq]
                for key in ("kind", "variant", "d", "record_fingerprints", "session_context", "frontier_before",
                            "request_id", "request_hash", "request_basis", "command_index", "command_count",
                            "reason_code", "requested_at", "ledger_digest", "state_after"):
                    self.assertEqual(H.cj(a[key]), H.cj(b[key]), key)
                self.assertEqual(b["origin"], {"resolution_seq": res_seq, "resolution_hash": a["resolution_hash"],
                                               "source_head_seq": a["source_head_seq"],
                                               "source_head_hash": a["source_head_hash"]})
                self.assertIsNone(b["replay_of"])
        for key in ("resolution_seq", "parent_resolution_hash", "resolution_hash", "source_head_seq",
                    "source_head_hash"):
            self.assertNotIn(key, self.ev[2])

    def test_references_are_in_the_v2_namespace_and_request_basis_stays_in_the_old_one(self):
        r1, r2, r3 = self.ev[2], self.ev[4], self.ev[6]
        self.assertEqual(r1["applied_ref"], {"seq": 1, "event_hash": self.ev[1]["event_hash"],
                                             "fingerprint": self.rs.records[0]["applied_ref"]["fingerprint"]})
        self.assertEqual(r3["missing_ref"], {"kind": "DECLARE_MISSING", "seq": 4, "event_hash": r2["event_hash"]})
        old = self.rs.records[2]["missing_ref"]
        self.assertEqual(old["resolution_seq"], 2)
        self.assertEqual(r3["request_basis"]["commands"][0]["missing_ref"], old)        # unchanged
        self.assertEqual(self.rs.records[0]["applied_ref"]["event_hash"], self.snap.events[1]["event_hash"])
        self.assertEqual(r1["request_basis"]["commands"][0]["applied_ref"]["seq"], 1)   # the S1 seq (same here)

    def test_source_record_and_check(self):
        mig = self.ev[7]
        self.assertEqual(mig["source"], {"schema_version": 1, "core_sha": self.snap.core_sha,
                                         "head_seq": 3, "head_hash": self.snap.head_hash,
                                         "snapshot_digest": sha256_text(encode_snapshot(self.snap))})
        self.assertEqual(mig["source_resolutions"]["digest"], self.rs.digest)
        self.assertEqual(mig["source_resolutions"]["head_resolution_seq"], 3)
        self.assertEqual(mig["source_resolutions"]["head_resolution_hash"], self.rs.head_resolution_hash)
        chk = V.validate_history(self.h)
        self.assertTrue(chk.migrated)
        self.assertEqual(chk.effective_seqs, tuple(range(8)))
        self.assertEqual(chk.superseded_seqs, ())
        self.assertEqual(chk.declared_days_in_segment, (D[3],))
        self.assertEqual(chk.processing_after, D[4])

    def test_migrated_sources_return_the_originals(self):
        snap, rs = V.migrated_sources(self.h)
        self.assertEqual(snap, self.snap)
        self.assertEqual(rs, self.rs)
        self.assertEqual(sha256_text(encode_snapshot(snap)), self.ev[7]["source"]["snapshot_digest"])
        self.assertEqual(rs.digest, self.rs.digest)

    def test_the_unchanged_checkers_really_run(self):
        calls = {"s1": 0, "s3a": 0, "hash": 0}

        def s1(snapshot):
            calls["s1"] += 1
            return real_validate_snapshot(snapshot)

        def s3a(snapshot, rset):
            calls["s3a"] += 1
            self.assertEqual(snapshot, self.snap)
            self.assertEqual(rset, self.rs)
            return real_validate_resolutions(snapshot, rset)

        def hashed(rec):
            calls["hash"] += 1
            return real_record_hash_of(rec)
        with mock.patch.object(migration_module, "validate_snapshot", side_effect=s1), \
                mock.patch.object(migration_module, "validate_resolutions", side_effect=s3a), \
                mock.patch.object(migration_module, "record_hash_of", side_effect=hashed):
            V.migrated_sources(self.h)
        self.assertEqual(calls["s1"], 2)             # once by validate_history, once by migrated_sources
        self.assertEqual(calls["s3a"], 2)
        self.assertEqual(calls["hash"], 2 * 3)

    def test_rules_of_the_old_checkers_are_passed_on_with_their_prefix(self):
        def failing_s1(_snapshot):
            raise H.PersistenceError("snapshot_invalid", "snapshot", rule="spy-s1")

        def failing_s3a(_snapshot, _rset):
            raise H.PersistenceError("resolution_invalid", "resolutions", rule="spy-s3a")
        with mock.patch.object(migration_module, "validate_snapshot", side_effect=failing_s1):
            H.expect_rule(self, "s1:spy-s1", self.h)
        with mock.patch.object(migration_module, "validate_resolutions", side_effect=failing_s3a):
            H.expect_rule(self, "s3a:spy-s3a", self.h)

    def test_not_migrated_histories_have_no_sources(self):
        H.expect_error(self, "history_invalid", "not_migrated", V.migrated_sources, H.example_u().history())


class ExampleMore(unittest.TestCase):
    def test_changed_row_removed_declaration_and_late_with_either_reference(self):
        w, snap, rs, ledger, check_d = H.example_m2_world()
        h = H.migrate(w, snap, rs, ledger, check_d)
        chk = V.validate_history(h)
        ev = h.events
        self.assertEqual([e["kind"] for e in ev],
                         ["GENESIS", "APPLY", "ACK", "APPLY", "ACK", "DECLARE_MISSING", "APPLY", "ACK", "APPLY", "ACK",
                          "SCHEMA_MIGRATION"])
        self.assertEqual([ev[i]["variant"] for i in (2, 4, 7, 9)], ["CHANGED", "ROW_REMOVED", "LATE", "LATE"])
        self.assertEqual(ev[7]["missing_ref"]["kind"], "DECLARE_MISSING")
        self.assertEqual(ev[7]["missing_ref"]["seq"], 5)
        self.assertEqual(ev[9]["missing_ref"], {"kind": "APPLY", "seq": 8, "event_hash": ev[8]["event_hash"]})
        self.assertEqual(rs.records[4]["missing_ref"]["seq"], 4)             # the S1 seq of the same APPLY
        self.assertEqual([m["seq"] for m in ev[10]["event_map"]], [0, 1, 3, 6, 8])
        self.assertEqual([m["seq"] for m in ev[10]["resolution_map"]], [2, 4, 5, 7, 9])
        self.assertEqual(chk.migrated, True)
        s, r = V.migrated_sources(h)
        self.assertEqual((s, r), (snap, rs))

    def test_an_empty_resolution_set(self):
        w, snap, rs, ledger, check_d = H.example_m_empty_world()
        h = H.migrate(w, snap, rs, ledger, check_d)
        ev = h.events
        self.assertEqual([e["kind"] for e in ev], ["GENESIS", "APPLY", "APPLY", "SCHEMA_MIGRATION"])
        self.assertEqual([e["event_hash"] for e in ev[:3]], [e["event_hash"] for e in snap.events])
        mig = ev[3]
        self.assertEqual(mig["resolution_map"], [])
        self.assertEqual(mig["source_resolutions"]["digest"], rs.digest)
        self.assertEqual(mig["source_resolutions"]["head_resolution_seq"], 0)
        self.assertIsNone(mig["source_resolutions"]["head_resolution_hash"])
        self.assertEqual(V.migrated_sources(h), (snap, rs))
        V.validate_history(h)


class PrepareRefusals(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = H.example_m_world()

    def prepare(self, **kw):
        args = dict(snapshot_v1=self.snap, resolutions=self.rs, sessions=self.w.sessions, raw_observations=self.ledger,
                    check_d=self.check_d, request_id="mig-1", requested_at=H.WHEN)
        args.update(kw)
        return V.prepare_migration_plan(**args)

    def expect(self, code, **kw):
        with self.assertRaises(H.PersistenceError if code in ("snapshot_invalid", "resolution_invalid",
                                                              "history_invalid", "migration_request_conflict",
                                                              "ledger_mismatch", "target_not_after_genesis",
                                                              "late_observation") else Exception) as cm:
            self.prepare(**kw)
        self.assertEqual(cm.exception.code, code)
        return cm.exception

    def test_an_invalid_snapshot(self):
        bad = H.P.tampered(self.snap, lambda ev: ev[1].update(d=D[9]))
        self.expect("snapshot_invalid", snapshot_v1=bad)
        self.expect("snapshot_invalid", snapshot_v1=H.example_u().history())

    def test_an_invalid_resolution_set(self):
        bad = RH_forge(self.rs, lambda recs: recs[0].update(d=D[9]))
        self.expect("resolution_invalid", resolutions=bad)
        self.expect("resolution_invalid", resolutions="not a set")

    def test_a_ledger_that_does_not_project(self):
        e = self.expect("ledger_mismatch", raw_observations=[r for r in self.ledger if r["record_id"] != "R1"])
        self.assertEqual(e.field, "observations")
        e = self.expect("late_observation", raw_observations=self.ledger + [H.P.obs("L4", D[3], 21.0, hour=22)])
        self.assertEqual(e.code, "late_observation")

    def test_invalid_ledger_rows_or_sessions_keep_the_existing_error(self):
        self.expect("fg_value_invalid", raw_observations=self.ledger + [dict(self.ledger[0], current_fg_value="abc")])
        self.expect("sessions_invalid", sessions=[1, 2])

    def test_request_id_conflicts_and_form(self):
        e = self.expect("migration_request_conflict", request_id="q1")
        self.assertEqual(e.field, "request_id")
        for bad in ("", "a b", None, 7):
            with self.subTest(bad):
                e = self.expect("history_invalid", request_id=bad)
                self.assertEqual(e.rule, "request_id")

    def test_check_d_out_of_range(self):
        self.expect("target_not_after_genesis", check_d=D[0])
        self.expect("state_ahead_of_target", check_d=D[3])
        self.expect("target_not_in_sessions", check_d="2030-01-01")
        self.expect("invalid_date", check_d="soon")

    def test_requested_at(self):
        import datetime as dt
        self.expect("datetime_missing_timezone", requested_at=dt.datetime(2026, 6, 1))
        self.expect("datetime_invalid", requested_at="2026-06-01T00:00:00Z")

    def test_a_refusal_changes_nothing(self):
        before = (H.cj(self.snap.to_dict()), self.rs.digest, H.cj(self.ledger))
        for kw in ({"request_id": "q1"}, {"check_d": D[0]}):
            with self.assertRaises(Exception):
                self.prepare(**kw)
        self.assertEqual(before, (H.cj(self.snap.to_dict()), self.rs.digest, H.cj(self.ledger)))


def RH_forge(rs, mutate):
    return H.RH.forge(rs, mutate)


class DamagedMigratedHistory(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = H.example_m_world()
        self.ev = H.migrate(self.w, self.snap, self.rs, self.ledger, self.check_d).events

    def rule(self, fn, remap=False, mig_basis=None):
        ev = H.deep(self.ev)
        fn(ev)
        if mig_basis:
            mig_basis(ev[7])
            ev[7]["request_hash"] = H.request_hash(ev[7]["request_basis"])
        return H.rule_of(self, H.rebuild(ev, remap=remap))

    def test_the_undamaged_history_is_accepted(self):
        V.validate_history(H.history_of(self.ev))

    def test_event_map(self):
        cases = {
            "hash": lambda ev: ev[7]["event_map"][2].update(v1_event_hash="0" * 64),
            "seq": lambda ev: ev[7]["event_map"][2].update(seq=2),
            "v1_seq": lambda ev: ev[7]["event_map"][2].update(v1_seq=5),
            "dropped": lambda ev: ev[7]["event_map"].pop(),
            "extra": lambda ev: ev[7]["event_map"].append({"v1_seq": 4, "v1_event_hash": "0" * 64, "seq": 8}),
            "swapped": lambda ev: ev[7]["event_map"].reverse(),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(fn), "migration_map")

    def test_resolution_map(self):
        cases = {
            "hash": lambda ev: ev[7]["resolution_map"][1].update(resolution_hash="0" * 64),
            "seq": lambda ev: ev[7]["resolution_map"][1].update(seq=3),
            "dropped": lambda ev: ev[7]["resolution_map"].pop(),
            "swapped": lambda ev: ev[7]["resolution_map"].reverse(),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(fn), "migration_map")

    def test_source(self):
        def with_basis(**kw):
            def fn(ev):
                ev[7]["source"].update(kw)
                if "snapshot_digest" in kw:
                    ev[7]["request_basis"]["source_snapshot_digest"] = kw["snapshot_digest"]
            return fn
        for name, kw in {"digest": dict(snapshot_digest="0" * 64), "head_hash": dict(head_hash="0" * 64),
                         "head_seq": dict(head_seq=2), "schema": dict(schema_version=2),
                         "core": dict(core_sha="0" * 40)}.items():
            with self.subTest(name):
                self.assertEqual(self.rule(with_basis(**kw), mig_basis=lambda m: None), "migration_source")
        ev = H.deep(self.ev)
        ev[7]["source"]["snapshot_digest"] = "0" * 64                         # the basis disagrees with the source
        ev[7]["request_hash"] = ev[7]["request_hash"]
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "migration_source")
        ev = H.deep(self.ev)
        ev[7]["source"]["extra"] = 1
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "migration_source")

    def test_source_resolutions(self):
        for name, kw in {"digest": dict(digest="0" * 64), "head_seq": dict(head_resolution_seq=2),
                         "head_hash": dict(head_resolution_hash="0" * 64), "schema": dict(schema="x")}.items():
            with self.subTest(name):
                def fn(ev, kw=kw):
                    ev[7]["source_resolutions"].update(kw)
                    if "digest" in kw:
                        ev[7]["request_basis"]["source_resolutions_digest"] = kw["digest"]
                self.assertEqual(self.rule(fn, mig_basis=lambda m: None), "migration_resolutions")
        ev = H.deep(self.ev)
        ev[7]["request_basis"]["source_resolutions_digest"] = "0" * 64        # the basis disagrees with the source
        ev[7]["request_hash"] = H.request_hash(ev[7]["request_basis"])
        self.assertEqual(H.rule_of(self, H.rebuild(ev)), "migration_resolutions")

    def test_origin(self):
        cases = {
            "resolution_hash": lambda ev: ev[4]["origin"].update(resolution_hash="0" * 64),
            "resolution_seq": lambda ev: ev[4]["origin"].update(resolution_seq=3),
            "source_head_seq": lambda ev: ev[4]["origin"].update(source_head_seq=1),
            "source_head_hash": lambda ev: ev[4]["origin"].update(source_head_hash="0" * 64),
            "extra_key": lambda ev: ev[4]["origin"].update(x=1),
            "missing_on_a_moved_record": lambda ev: ev[4].update(origin=None),
            "not_a_dict": lambda ev: ev[4].update(origin=5),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(fn, remap=True), "origin")

    def test_origin_after_the_migration_is_refused(self):
        b = H.HB(world=self.w, events=self.ev)
        b.apply(D[5], 30.0)
        rec = b.ack("ADDED", D[5], [H.fp(H.P.obs("X5", D[5], 41.0, hour=21))], "later", applied=8)
        ev = H.deep(b.events)
        ev[9]["origin"] = H.deep(ev[2]["origin"])
        H.expect_rule(self, "origin", H.rebuild(ev))

    def test_positions(self):
        # two SCHEMA_MIGRATION records
        ev = H.deep(self.ev)
        dup = H.deep(ev[7])
        dup["seq"] = 8
        dup["parent_seq"] = 7
        H.expect_rule(self, "migration_position", H.rebuild(ev + [dup]))
        # a RESTART_UNKNOWN or a RECOVERY_RESTORE inside the moved range
        for name, rec in (("restart", H.example_u().events[3]),
                          ("restore", dict(H.example_r1().events[7], parent_seq=0))):
            with self.subTest(name):
                got = H.insert_record(self.ev, 2, rec)
                H.expect_rule(self, "migration_position", H.rebuild(got))
        # the migration record in front of records that still carry an origin
        moved = H.deep(self.ev)
        moved.insert(1, moved.pop(7))
        for i, r in enumerate(moved):
            r["seq"] = i
            r["parent_seq"] = i - 1 if i else None
        H.expect_rule(self, "origin", H.rebuild(moved))

    def test_changed_apply_content_inside_the_migrated_range(self):
        ev = H.deep(self.ev)
        ev[3]["transition_result"]["notes"] = ["x"]
        H.expect_rule(self, "s1:transition_mismatch", H.rebuild(ev, remap=True))

    def test_request_fields_of_the_migration(self):
        basis_cases = {
            "request_id": ("request_basis", lambda m: m["request_basis"].update(request_id="other")),
            "check_d_before_start": ("check_d", lambda m: m["request_basis"].update(check_d=D[0])),
            "check_d_before_latest": ("check_d", lambda m: m["request_basis"].update(check_d=D[3])),
            "extra_key": ("request_basis", lambda m: m["request_basis"].update(x=1)),
            "reason": ("reason_code", lambda m: m["request_basis"].update(reason_code="X")),
        }
        for name, (rule, fn) in basis_cases.items():
            with self.subTest(name):
                ev = H.deep(self.ev)
                fn(ev[7])
                ev[7]["request_hash"] = H.request_hash(ev[7]["request_basis"])
                H.expect_rule(self, rule, H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[7]["request_hash"] = "0" * 64
        H.expect_rule(self, "request_hash", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[7]["ledger_digest"] = "zz"
        H.expect_rule(self, "ledger_digest", H.rebuild(ev))
        ev = H.deep(self.ev)
        ev[7]["requested_at"] = "2030-01-01T00:00:00Z"
        H.expect_rule(self, "requested_at", H.rebuild(ev))


if __name__ == "__main__":
    unittest.main()
