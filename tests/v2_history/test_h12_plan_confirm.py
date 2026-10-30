"""H-12: migration plan and confirmation (design 5.6). plan_hash binds the whole basis; valid-but-changed inputs are
stale, invalid inputs keep their own error; a plan or its confirmation can never reach an existing store."""
import datetime as dt
import os
import tempfile
import unittest

import h_helpers as H
from h_helpers import D, V

from v2_core.sessions import SessionList
from v2_persistence.codec import encode_snapshot, sha256_text
from v2_persistence.local import LocalFileStore
from v2_persistence.store import MemoryStore
from v2_recovery import ledger as L
from v2_recovery import resolve_observations


class Base(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = H.example_m_world()
        self.plan = self.prepare()

    def prepare(self, **kw):
        args = dict(snapshot_v1=self.snap, resolutions=self.rs, sessions=self.w.sessions,
                    raw_observations=self.ledger, check_d=self.check_d, request_id="mig-1", requested_at=H.WHEN)
        args.update(kw)
        return V.prepare_migration_plan(**args)

    def confirm(self, plan=None, h=None, **kw):
        plan = plan or self.plan
        args = dict(snapshot_v1=self.snap, resolutions=self.rs, sessions=self.w.sessions,
                    raw_observations=self.ledger)
        args.update(kw)
        return V.confirm_migration_plan(plan, h or plan.plan_hash, args["snapshot_v1"], args["resolutions"],
                                        args["sessions"], args["raw_observations"])

    def forged(self, **changes):
        basis = self.plan.basis
        basis.update(changes)
        return V.MigrationPlan.from_dict({"basis": basis, "plan_hash": sha256_text(H.cj(basis))})


class PlanContents(Base):
    def test_the_basis_holds_every_input_digest_and_the_candidate(self):
        b = self.plan.basis
        self.assertEqual(sorted(b), sorted([
            "operation", "status", "source_snapshot_digest", "source_head_seq", "source_head_hash",
            "source_resolutions_digest", "request_id", "request_hash", "requested_at", "check_d", "ledger_digest",
            "sessions_digest", "effective_digest", "candidate_history", "candidate_digest", "expected_state_digest"]))
        self.assertEqual(b["operation"], "soxl-v2-history-migration-plan/1")
        self.assertEqual(self.plan.status, V.READY)
        self.assertEqual(b["source_snapshot_digest"], sha256_text(encode_snapshot(self.snap)))
        self.assertEqual((b["source_head_seq"], b["source_head_hash"]), (self.snap.head_seq, self.snap.head_hash))
        self.assertEqual(b["source_resolutions_digest"], self.rs.digest)
        self.assertEqual(b["ledger_digest"], L.ledger_digest(L.parse_ledger(self.ledger)))
        self.assertEqual(b["sessions_digest"], L.sessions_digest(self.w.sessions))
        eff = resolve_observations(self.snap, self.rs, self.w.sessions, self.ledger, self.check_d)
        self.assertEqual(b["effective_digest"], eff.effective_digest)
        self.assertEqual(b["expected_state_digest"], sha256_text(H.cj(self.snap.current_state)))
        cand = V.History.from_dict(b["candidate_history"])
        self.assertEqual(b["candidate_digest"], cand.digest)
        self.assertEqual(b["request_hash"], cand.events[-1]["request_hash"])
        self.assertEqual(self.plan.plan_hash, sha256_text(H.cj(b)))
        self.assertEqual(b["requested_at"], "2026-06-01T00:00:00Z")

    def test_no_record_carries_the_plan_hash(self):
        text = H.cj(V.History.from_dict(self.plan.basis["candidate_history"]).to_dict())
        self.assertNotIn(self.plan.plan_hash, text)

    def test_a_plan_is_deterministic_and_immutable(self):
        self.assertEqual(self.plan, self.prepare())
        self.assertEqual(self.plan.plan_hash, self.prepare().plan_hash)
        self.assertNotEqual(self.plan.plan_hash, self.prepare(request_id="mig-2").plan_hash)
        self.assertNotEqual(self.plan.plan_hash, self.prepare(requested_at=H.WHEN + dt.timedelta(hours=1)).plan_hash)
        with self.assertRaises(AttributeError):
            self.plan.status = "x"
        with self.assertRaises(TypeError):
            V.MigrationPlan()

    def test_the_hash_of_the_request_ignores_the_requested_time_but_the_plan_does_not(self):
        other = self.prepare(requested_at=H.WHEN + dt.timedelta(hours=1))
        self.assertEqual(self.plan.basis["request_hash"], other.basis["request_hash"])
        self.assertNotEqual(self.plan.plan_hash, other.plan_hash)


class PlanHashBindsTheBasis(Base):
    def test_any_changed_basis_value_with_the_old_hash_is_a_mismatch(self):
        for key, value in {
                "operation": "other", "status": "NO_CHANGE", "source_snapshot_digest": "0" * 64, "source_head_seq": 99,
                "source_head_hash": "0" * 64, "source_resolutions_digest": "0" * 64, "request_id": "mig-9",
                "request_hash": "0" * 64, "requested_at": "2030-01-01T00:00:00Z", "check_d": D[5],
                "ledger_digest": "0" * 64, "sessions_digest": "0" * 64, "effective_digest": "0" * 64,
                "candidate_history": {}, "candidate_digest": "0" * 64, "expected_state_digest": "0" * 64}.items():
            with self.subTest(key):
                basis = self.plan.basis
                basis[key] = value
                plan = V.MigrationPlan.from_dict({"basis": basis, "plan_hash": self.plan.plan_hash})
                H.expect_error(self, "migration_plan_mismatch", None, V.confirm_migration_plan,
                               plan, self.plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)

    def test_a_consistently_forged_basis_is_caught_by_the_rebuild_or_the_digests(self):
        mismatch = {"request_id": "mig-9", "request_hash": "0" * 64, "requested_at": "2030-01-01T00:00:00Z",
                    "check_d": D[5], "effective_digest": "0" * 64, "candidate_digest": "0" * 64,
                    "expected_state_digest": "0" * 64, "candidate_history": self.plan.basis["candidate_history"]}
        stale = {"source_snapshot_digest": "0" * 64, "source_head_seq": 99, "source_head_hash": "0" * 64,
                 "source_resolutions_digest": "0" * 64, "ledger_digest": "0" * 64, "sessions_digest": "0" * 64}
        for key, value in mismatch.items():
            with self.subTest("mismatch " + key):
                plan = self.forged(**{key: value if key != "candidate_history" else
                                     dict(value, current_state=dict(value["current_state"], streak=9))})
                H.expect_error(self, "migration_plan_mismatch", None, self.confirm, plan)
        for key, value in stale.items():
            with self.subTest("stale " + key):
                H.expect_error(self, "migration_plan_stale", None, self.confirm, self.forged(**{key: value}))

    def test_wrong_hash_or_wrong_type_is_a_mismatch(self):
        for bad in ("0" * 64, "xyz", None, 5, self.plan.plan_hash.upper()):
            with self.subTest(bad):
                H.expect_error(self, "migration_plan_mismatch", None, V.confirm_migration_plan, self.plan, bad,
                               self.snap, self.rs, self.w.sessions, self.ledger)
        for other in (None, "plan", self.plan.to_dict(), self.snap):
            with self.subTest(type(other).__name__):
                H.expect_error(self, "migration_plan_mismatch", None, V.confirm_migration_plan, other,
                               self.plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)

    def test_shape_errors_when_rebuilding_a_plan_from_a_dict(self):
        for bad in (None, [], {"basis": {}}, {"basis": {}, "plan_hash": "x", "extra": 1}):
            with self.subTest(repr(bad)):
                H.expect_error(self, "history_invalid", "plan_shape", V.MigrationPlan.from_dict, bad)


class ChangedButValidInputsAreStale(Base):
    def test_snapshot(self):
        self.w.apply(D[7], 30.0, "R7")
        grown = self.w.snap()
        stale = H.expect_error(self, "migration_plan_stale", None, self.confirm, snapshot_v1=grown)
        self.assertEqual(stale.field, "plan")

    def test_resolutions(self):
        extra = H.P.obs("B9", D[1], 40.0, hour=21)
        ledger = self.ledger + [extra]
        rs2 = H.RH.run(self.w, self.rs, [H.RH.ack(self.snap, "ADDED", D[1], [H.fp(extra)])], ledger, self.check_d,
                       "extra-1", snapshot=self.snap).resolutions
        self.assertNotEqual(rs2.digest, self.rs.digest)
        H.expect_error(self, "migration_plan_stale", None, self.confirm, resolutions=rs2, raw_observations=ledger)

    def test_ledger(self):
        H.expect_error(self, "migration_plan_stale", None, self.confirm,
                       raw_observations=self.ledger + [H.P.obs("S9", D[9], 40.0, role="supplemental")])
        H.expect_error(self, "migration_plan_stale", None, self.confirm, raw_observations=self.ledger[:-1])

    def test_ledger_row_order_alone_does_not_matter(self):
        self.confirm(raw_observations=list(reversed(self.ledger)))

    def test_sessions(self):
        fewer = SessionList(list(self.w.sessions.sessions)[:35])
        H.expect_error(self, "migration_plan_stale", None, self.confirm, sessions=fewer)

    def test_a_projection_that_no_longer_passes_is_stale_not_an_error(self):
        # a valid row appears for a skipped day: the projection would stop (late_observation), the digest differs first
        late = H.P.obs("L9", D[5], 23.0)
        H.expect_error(self, "migration_plan_stale", None, self.confirm, raw_observations=self.ledger + [late])


class InvalidInputsKeepTheirOwnError(Base):
    def codes(self, **kw):
        with self.assertRaises(Exception) as cm:
            self.confirm(**kw)
        self.assertNotEqual(cm.exception.code, "migration_plan_stale")
        self.assertNotEqual(cm.exception.code, "migration_plan_mismatch")
        return cm.exception.code

    def test_broken_v1_snapshot(self):
        self.assertEqual(self.codes(snapshot_v1=H.P.tampered(self.snap, lambda ev: ev[1].update(d=D[9]))),
                         "snapshot_invalid")
        self.assertEqual(self.codes(snapshot_v1=H.example_u().history()), "snapshot_invalid")

    def test_broken_resolution_set(self):
        bad = H.RH.forge(self.rs, lambda recs: recs[0].update(d=D[9]))
        self.assertEqual(self.codes(resolutions=bad), "resolution_invalid")
        self.assertEqual(self.codes(resolutions=None), "resolution_invalid")

    def test_broken_ledger_rows_and_sessions(self):
        self.assertEqual(self.codes(raw_observations=self.ledger + [dict(self.ledger[0], current_fg_value="abc")]),
                         "fg_value_invalid")
        self.assertEqual(self.codes(raw_observations="not a ledger"), "observation_invalid")
        self.assertEqual(self.codes(raw_observations=self.ledger + [5]), "observation_invalid")
        self.assertEqual(self.codes(sessions=None), "sessions_invalid")
        self.assertEqual(self.codes(sessions=[1, 2]), "sessions_invalid")

    def test_changed_and_broken_are_different_acceptance_cases(self):
        # the same plan: a valid change is stale, an invalid one is not
        valid_change = self.ledger + [H.P.obs("S9", D[9], 40.0, role="supplemental")]
        H.expect_error(self, "migration_plan_stale", None, self.confirm, raw_observations=valid_change)
        self.assertEqual(self.codes(raw_observations=valid_change + [dict(self.ledger[0], current_fg_value="abc")]),
                         "fg_value_invalid")


class ConfirmedResult(Base):
    def test_confirmation_is_in_memory_only(self):
        res = self.confirm()
        self.assertEqual(res.status, V.CONFIRMED_IN_MEMORY)
        self.assertIs(res.committed, False)
        self.assertIs(res.state_unchanged, True)
        self.assertEqual(res.plan_hash, self.plan.plan_hash)
        self.assertEqual(res.history.to_dict(), self.plan.basis["candidate_history"])
        self.assertEqual(res.history.current_state, self.snap.current_state)
        self.assertIs(self.plan.committed, False)
        self.assertRegex(repr(res), r"^MigrationConfirmResult\(status=CONFIRMED_IN_MEMORY, committed=False\)$")
        V.validate_history(res.history)

    def test_nothing_is_stored_or_changed(self):
        before = (H.cj(self.snap.to_dict()), self.rs.digest, H.cj(self.ledger), L.sessions_digest(self.w.sessions))
        self.confirm()
        self.confirm()
        self.assertEqual(before, (H.cj(self.snap.to_dict()), self.rs.digest, H.cj(self.ledger),
                                  L.sessions_digest(self.w.sessions)))

    def test_candidate_plan_and_result_cannot_reach_a_memory_store(self):
        res = self.confirm()
        store = MemoryStore()
        store.initialize(H.P.make_genesis(D[0], self.w.sessions))
        before = store.read()
        for what in (self.plan, res, res.history, self.plan.basis["candidate_history"], self.snap):
            with self.subTest(type(what).__name__):
                H.expect_error(self, "snapshot_invalid", "plan_type", store.commit, what)
        self.assertEqual(store.read(), before)

    def test_candidate_plan_and_result_cannot_reach_a_local_file_store(self):
        res = self.confirm()
        root = tempfile.mkdtemp(prefix="v2h_root_")
        store = LocalFileStore(root, writable=True, durability="file_sync_only")
        store.initialize(H.P.make_genesis(D[0], self.w.sessions))
        with open(os.path.join(root, "snapshot.json"), "rb") as f:
            before = f.read()
        listing = sorted(os.listdir(root))
        for what in (self.plan, res, res.history):
            with self.subTest(type(what).__name__):
                H.expect_error(self, "snapshot_invalid", "plan_type", store.commit, what)
        with open(os.path.join(root, "snapshot.json"), "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(sorted(os.listdir(root)), listing)

    def test_a_v2_text_in_snapshot_json_stops_the_existing_store_without_touching_the_files(self):
        res = self.confirm()
        root = tempfile.mkdtemp(prefix="v2h_root_")
        path = os.path.join(root, "snapshot.json")
        data = V.encode_history(res.history).encode("utf-8")
        with open(path, "wb") as f:
            f.write(data)
        for writable in (False, True):
            store = LocalFileStore(root, writable=writable, durability="file_sync_only")
            with self.subTest("read writable=%s" % writable):
                e = H.expect_field(self, "unsupported_schema", "schema_version", store.read)
                self.assertIsNone(e.rule)
            if writable:
                with self.subTest("initialize"):
                    H.expect_field(self, "unsupported_schema", "schema_version", store.initialize,
                                   H.P.make_genesis(D[0], self.w.sessions))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), data)
            self.assertEqual(sorted(os.listdir(root)), ["snapshot.json"])


class MemoryStoreAcceptsV1Only(unittest.TestCase):
    def test_the_existing_memory_store_still_works_for_v1(self):
        w = H.P.World()
        w.apply(D[1], 27.0)
        self.assertEqual(w.snap().head_seq, 1)


if __name__ == "__main__":
    unittest.main()
