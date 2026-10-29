"""C-09: hash chain, prefix and reference rules, creation-time state, request batches and the stored digests."""
import unittest

import r_helpers as H
from r_helpers import D, R
from v2_persistence.codec import Snapshot


def row(record_id, d, value, hour=20):
    return H.P.obs(record_id, d, value, hour=hour)


class Built(unittest.TestCase):
    """A set with a two-record request (ROW_REMOVED + ADDED) and a one-record declaration."""

    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.a = self.w.ledger[0]
        self.b = row("B1", D[1], 40.0, hour=21)
        self.ledger = [self.b]
        cmds = [H.ack(self.snap, "ROW_REMOVED", D[1], []), H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])]
        first = H.run(self.w, R.empty_resolutions(), cmds, self.ledger, D[1], rid="req-a")
        second = H.run(self.w, first.resolutions, [H.declare(D[2])], self.ledger, D[2], rid="req-b")
        self.rs = second.resolutions

    def check(self, rs, snap=None):
        return R.validate_resolutions(snap or self.snap, rs)


class Baseline(Built):
    def test_the_built_set_is_valid(self):
        chk = self.check(self.rs)
        self.assertEqual((chk.record_count, chk.request_ids, chk.declared_days), (3, ("req-a", "req-b"), (D[2],)))
        self.assertEqual(chk.resolutions_digest, self.rs.digest)

    def test_state_after_is_the_prefix_state_and_the_base_does_not_change(self):
        before = self.snap.current_state
        for rec in self.rs.records:
            self.assertEqual(rec["state_after"], before)
        self.assertEqual(self.w.snap().current_state, before)
        self.assertIsNotNone(before["base"])
        self.assertEqual(self.w.snap().events[1]["state_after"]["base"], before["base"])

    def test_every_record_keeps_the_ledger_digest_of_its_creation(self):
        recs = self.rs.records
        expect = L_digest([self.b])
        self.assertEqual([r["ledger_digest"] for r in recs], [expect] * 3)

    def test_batch_members_share_basis_hash_and_head(self):
        r0, r1, r2 = self.rs.records
        for key in ("request_id", "request_hash", "request_basis", "source_head_seq", "source_head_hash",
                    "ledger_digest", "requested_at"):
            self.assertEqual(r0[key], r1[key], key)
        self.assertNotEqual(r0["request_id"], r2["request_id"])
        self.assertEqual((r0["command_index"], r1["command_index"], r0["command_count"]), (0, 1, 2))
        self.assertNotIn("requested_at", H.cj({k: v for k, v in r0["request_basis"].items() if k != "requested_at"}))


def L_digest(rows):
    return H.L.ledger_digest([H.L.parse_row(r) for r in rows])


class Tampering(Built):
    def test_content_change_without_rehash(self):
        bad = H.forge(self.rs, lambda recs: recs[2].__setitem__("d", D[3]), rehash=False)
        H.expect_rule(self, "resolution_hash", self.check, bad)

    def test_chain_head_and_sequence(self):
        recs = lambda f: H.forge(self.rs, f, rehash=False)
        H.expect_rule(self, "parent_hash", self.check, recs(lambda r: r[1].__setitem__("parent_resolution_hash", "a" * 64)))
        H.expect_rule(self, "seq", self.check, recs(lambda r: r[1].__setitem__("resolution_seq", 5)))
        data = self.rs.to_dict()
        data["head_resolution_hash"] = "b" * 64
        H.expect_rule(self, "head", self.check, R.ResolutionSet.from_dict(data))
        data = self.rs.to_dict()
        data["head_resolution_seq"] = True
        H.expect_rule(self, "head", self.check, R.ResolutionSet.from_dict(data))

    def test_truncated_batch(self):
        bad = H.forge(self.rs, lambda recs: recs.pop(1))                       # the first record claims two commands
        H.expect_rule(self, "batch", self.check, bad)
        bad = H.forge(self.rs, lambda recs: recs.pop(0))                       # starts at command_index 1
        H.expect_rule(self, "batch", self.check, bad)

    def test_request_basis_must_match_every_member(self):
        def f(recs):
            recs[1]["request_basis"]["check_d"] = D[2]
        H.expect_rule(self, "batch", self.check, H.forge(self.rs, f))

        def g(recs):
            recs[0]["request_basis"]["commands"][0]["d"] = D[2]
            recs[1]["request_basis"]["commands"][0]["d"] = D[2]
            for r in recs[:2]:
                H.refresh_request(r)
        H.expect_rule(self, "batch", self.check, H.forge(self.rs, g))

    def test_request_hash_and_reason(self):
        H.expect_rule(self, "request_hash", self.check,
                      H.forge(self.rs, lambda recs: [r.__setitem__("request_hash", "c" * 64) for r in recs[:2]]))

        def reason(recs):
            for r in recs[:2]:
                r["request_basis"]["reason_code"] = "MARK_SESSION_MISSING"
                H.refresh_request(r)
        H.expect_rule(self, "reason_code", self.check, H.forge(self.rs, reason))
        H.expect_rule(self, "reason_code", self.check,
                      H.forge(self.rs, lambda recs: recs[0].__setitem__("reason_code", "MARK_SESSION_MISSING")))

    def test_source_head_prefix_and_state(self):
        H.expect_rule(self, "source_head", self.check,
                      H.forge(self.rs, lambda recs: [r.__setitem__("source_head_hash", "d" * 64) for r in recs[:2]]))
        H.expect_rule(self, "source_head", self.check,
                      H.forge(self.rs, lambda recs: [r.__setitem__("source_head_seq", 2) for r in recs[:2]]))

        def state(recs):
            for r in recs[:2]:
                r["state_after"]["streak"] = 3
        H.expect_rule(self, "state_after", self.check, H.forge(self.rs, state))

    def test_unknown_keys_kind_variant_and_types(self):
        H.expect_rule(self, "record_keys", self.check, H.forge(self.rs, lambda recs: recs[0].__setitem__("note", "x")))
        data = self.rs.to_dict()
        data["extra"] = 1
        H.expect_rule(self, "header_keys", self.check, R.ResolutionSet.from_dict(data))
        data = self.rs.to_dict()
        data["schema"] = "other/1"
        H.expect_rule(self, "schema", self.check, R.ResolutionSet.from_dict(data))
        H.expect_rule(self, "kind", self.check, H.forge(self.rs, lambda recs: recs[0].__setitem__("kind", "RESTART_UNKNOWN")))
        H.expect_rule(self, "batch", self.check, H.forge(self.rs, lambda recs: recs[0].__setitem__("command_index", True)))
        H.expect_rule(self, "type", self.check, "not a set")

    def test_declared_context_must_continue_the_saved_history(self):
        def shifted_frontier_session(recs):
            recs[2]["session_context"][0]["close_at"] = "2026-03-03T21:01:00Z"
        H.expect_rule(self, "session_context", self.check, H.forge(self.rs, shifted_frontier_session))

        def shifted_declared_day(recs):
            recs[2]["session_context"][1]["close_at"] = "2026-03-04T21:01:00Z"
        self.check(H.forge(self.rs, shifted_declared_day))        # the declared day itself is only compared with sessions later

    def test_a_stored_record_cannot_name_a_fixed_row(self):
        fixed = H.ref_of(self.snap, 1)["fingerprint"]
        names = sorted([H.fp(self.b), fixed])

        def name_fixed(recs):
            for r in recs[:2]:
                r["request_basis"]["commands"][1]["record_fingerprints"] = names
                H.refresh_request(r)
            recs[1]["record_fingerprints"] = names
        H.expect_rule(self, "exclude_applied", self.check, H.forge(self.rs, name_fixed))

    def test_check_d_of_the_basis(self):
        def early(recs):
            for r in recs[:2]:
                r["request_basis"]["check_d"] = D[0]
                H.refresh_request(r)
        H.expect_rule(self, "check_d", self.check, H.forge(self.rs, early))

        def before_day(recs):
            r = recs[2]
            r["request_basis"]["check_d"] = D[1]
            H.refresh_request(r)
        H.expect_rule(self, "check_d", self.check, H.forge(self.rs, before_day))     # the day D2 is after check_d


class LateCheckD(unittest.TestCase):
    def test_check_d_of_a_late_record_is_bounded_by_its_own_prefix(self):
        w = H.world(0)
        w.apply(D[3], 27.0, "R3")
        snap = w.snap()
        late1 = row("L1", D[1], 20.0)
        res = H.run(w, R.empty_resolutions(), [H.late(D[1], [H.fp(late1)], H.apply_missing(snap, 1))],
                    [w.ledger[0], late1], D[3])

        def too_early(recs):
            recs[0]["request_basis"]["check_d"] = D[2]               # after the day D1 but before the latest APPLY D3
            H.refresh_request(recs[0])
        H.expect_rule(self, "check_d", R.validate_resolutions, snap, H.forge(res.resolutions, too_early))


class References(unittest.TestCase):
    def setUp(self):
        self.w = H.world(2)
        self.snap2 = self.w.snap()
        self.snap1 = Snapshot.from_dict(dict(self.snap2.to_dict(), events=self.snap2.events[:2],
                                             head_seq=1, head_hash=self.snap2.events[1]["event_hash"],
                                             current_state=self.snap2.events[1]["state_after"]))
        self.a1, self.a2 = self.w.ledger
        self.b2 = row("B2", D[2], 40.0, hour=21)

    def test_an_apply_made_after_the_record_cannot_be_used_as_its_evidence(self):
        cmd = H.ack(self.snap2, "ADDED", D[2], [H.fp(self.b2)], seq=2)
        res = H.run(self.w, R.empty_resolutions(), [cmd], [self.a1, self.a2, self.b2], D[2])
        self.assertEqual(R.validate_resolutions(self.snap2, res.resolutions).record_count, 1)

        def back_to_prefix(recs):
            for r in recs:
                r["source_head_seq"] = 1
                r["source_head_hash"] = self.snap2.events[1]["event_hash"]
                r["state_after"] = self.snap2.events[1]["state_after"]
        H.expect_rule(self, "applied_ref", R.validate_resolutions, self.snap2, H.forge(res.resolutions, back_to_prefix))

    def test_a_record_stays_valid_when_the_snapshot_grows_and_is_judged_by_its_own_prefix(self):
        b1 = row("B1", D[1], 40.0, hour=21)
        cmd = H.ack(self.snap1, "ADDED", D[1], [H.fp(b1)], seq=1)
        w1 = H.P.World()
        w1.apply(D[1], 27.0, "R1")
        res = H.run(w1, R.empty_resolutions(), [cmd], [self.a1, b1], D[1])
        self.assertEqual(res.resolutions.records[0]["source_head_seq"], 1)
        self.assertEqual(R.validate_resolutions(self.snap2, res.resolutions).record_count, 1)
        eff = R.resolve_observations(self.snap2, res.resolutions, self.w.sessions, [self.a1, self.a2, b1], D[2])
        self.assertEqual(eff.rows, [H.cols(self.a1), H.cols(self.a2)])
        rec = res.resolutions.records[0]
        self.assertNotEqual(rec["state_after"], self.snap2.current_state)        # the prefix state, not today's state

    def test_namespaces_are_not_mixed(self):
        w = H.world(0)
        w.apply(D[3], 27.0, "R3")
        snap = w.snap()
        late1 = row("L1", D[1], 20.0)
        mixed = {"kind": "APPLY", "resolution_seq": 1, "resolution_hash": "e" * 64}
        H.expect_rule(self, "command_shape", H.plan_for, w, R.empty_resolutions(),
                      [H.late(D[1], [H.fp(late1)], mixed)], [w.ledger[0], late1], D[3])
        res = H.run(w, R.empty_resolutions(), [H.late(D[1], [H.fp(late1)], H.apply_missing(snap, 1))],
                    [w.ledger[0], late1], D[3])

        def decl_kind(recs):
            r = recs[0]
            r["missing_ref"] = {"kind": "DECLARE_MISSING", "resolution_seq": 1, "resolution_hash": "f" * 64}
            r["request_basis"]["commands"][0]["missing_ref"] = r["missing_ref"]
            H.refresh_request(r)
        H.expect_rule(self, "missing_ref", R.validate_resolutions, snap, H.forge(res.resolutions, decl_kind))

        def future_apply(recs):
            r = recs[0]
            r["missing_ref"] = {"kind": "APPLY", "seq": 1, "event_hash": "0" * 64}
            r["request_basis"]["commands"][0]["missing_ref"] = r["missing_ref"]
            H.refresh_request(r)
        H.expect_rule(self, "missing_ref", R.validate_resolutions, snap, H.forge(res.resolutions, future_apply))


class LedgerDigestDoesNotExpireRecords(Built):
    def test_a_later_change_of_the_ledger_alone_does_not_invalidate_old_records(self):
        extra = row("E9", D[8], 27.0)
        self.check(self.rs)
        eff = R.resolve_observations(self.snap, self.rs, self.w.sessions, [self.b, extra], D[1])
        self.assertEqual(len(eff.rows), 2)

    def test_ledger_digest_ignores_order_and_offset_but_counts_duplicates(self):
        rows = [row("A", D[1], 27.0), row("B", D[2], 28.0)]
        self.assertEqual(L_digest(rows), L_digest(list(reversed(rows))))
        tz9 = H.P.timezone(H.P.timedelta(hours=9))
        y, m, d = (int(x) for x in D[2].split("-"))
        moved = dict(rows[0], observed_at_iso8601=H.P.datetime(y, m, d, 10, 0, tzinfo=tz9).isoformat())
        self.assertEqual(L_digest(rows), L_digest([moved, rows[1]]))
        self.assertNotEqual(L_digest(rows), L_digest(rows + [rows[0]]))
        self.assertNotEqual(L_digest(rows), L_digest([rows[0]]))


if __name__ == "__main__":
    unittest.main()
