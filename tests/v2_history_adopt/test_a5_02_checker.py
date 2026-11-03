"""A5-02 kind and keys, A5-03 a valid adoption record, A5-04 each rule of the record, A5-05 where it may stand.

Every history here is written by the independent builder (a5_helpers.record_of) and judged by the unchanged
validate_history that now knows the eighth record kind."""
import unittest

import a5_helpers as Z
from a5_helpers import GONE, H, V, D

OLD_KINDS = ("GENESIS", "APPLY", "ACK", "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION")
TWELVE = {"kind", "seq", "parent_seq", "parent_hash", "evidence", "request_id", "request_hash", "request_basis",
          "reason_code", "requested_at", "state_after", "event_hash"}
PUBLIC_24 = ["History", "encode_history", "decode_history", "validate_history", "make_history_genesis",
             "migrated_sources", "prepare_migration_plan", "confirm_migration_plan", "HistoryCheck", "Boundary",
             "MigrationPlan", "MigrationConfirmResult", "SCHEMA_VERSION_V2", "KINDS", "GENESIS", "APPLY", "ACK",
             "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION",
             "READY", "CONFIRMED_IN_MEMORY"]


def world():
    b, data, k = Z.new_world()
    return b, data, k, Z.prefix_events(data, k)


def history_with(prefix, rec):
    return H.history_of(prefix + [rec])


def header_of_whole(prefix, whole, broken):
    """A history whose header is the one of the whole record but whose last record is `broken` (a key is missing, so
    the builder's header cannot be taken from it)."""
    doc = H.header(Z.deep(prefix) + [whole])
    doc["events"][-1] = broken
    return V.History.from_dict(doc)


class KindAndKeys(unittest.TestCase):
    def test_the_eighth_kind_is_the_last_and_the_seven_before_keep_their_order(self):
        self.assertEqual(V.KINDS, OLD_KINDS + ("RECOVERY_PREFIX_ADOPTION",))
        self.assertEqual(len(V.KINDS), 8)
        self.assertEqual(V.RECOVERY_PREFIX_ADOPTION, "RECOVERY_PREFIX_ADOPTION")

    def test_the_public_names_are_24(self):
        self.assertEqual(sorted(V.__all__), sorted(PUBLIC_24))
        self.assertEqual(len(V.__all__), 24)
        for name in V.__all__:
            self.assertTrue(hasattr(V, name), name)

    def test_the_record_has_exactly_twelve_keys(self):
        import v2_history.values as values
        self.assertEqual(values.RECORD_KEYS["RECOVERY_PREFIX_ADOPTION"], frozenset(TWELVE))
        b, data, k, prefix = world()
        rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1")
        self.assertEqual(set(rec), TWELVE)

    def test_an_extra_or_a_missing_key_is_record_keys(self):
        b, data, k, prefix = world()
        for key in sorted(TWELVE - {"kind"}):
            with self.subTest("missing " + key):
                rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1", over={key: GONE})
                H.expect_rule(self, "record_keys", header_of_whole(prefix, Z.record_of(prefix, Z.evidence_of(data, k), "ad1"), rec))
        for key in ("x", "prev_hash", "ledger_digest", "origin"):
            with self.subTest("extra " + key):
                rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1", over={key: 1})
                H.expect_rule(self, "record_keys", history_with(prefix, rec))

    def test_the_record_does_not_carry_the_keys_of_the_other_control_records(self):
        b, data, k, prefix = world()
        rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1")
        for foreign in ("replay", "superseded_seqs", "source", "ledger_digest", "prev_hash", "resume_after"):
            self.assertNotIn(foreign, rec)


class ValidRecord(unittest.TestCase):
    def test_prefix_and_record_pass_with_the_expected_check(self):
        b, data, k, prefix = world()
        before = V.validate_history(H.history_of(prefix))
        rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1")
        after = V.validate_history(history_with(prefix, rec))
        self.assertEqual((after.head_seq, after.head_hash), (k, rec["event_hash"]))
        self.assertEqual(after.record_count, k + 1)
        self.assertEqual(after.effective_seqs, tuple(range(k + 1)))            # the record joins the effective chain
        self.assertEqual(after.superseded_seqs, ())
        self.assertEqual(after.state_digest, before.state_digest)               # the state is the prefix' state
        self.assertEqual(after.current_boundary, before.current_boundary)       # no new interval
        self.assertEqual((after.latest_apply_d, after.processing_after, after.migrated),
                         (before.latest_apply_d, before.processing_after, before.migrated))
        self.assertNotEqual(after.history_digest, before.history_digest)

    def test_the_header_current_state_is_the_prefix_state(self):
        b, data, k, prefix = world()
        h = history_with(prefix, Z.record_of(prefix, Z.evidence_of(data, k), "ad1"))
        self.assertEqual(h.current_state, prefix[-1]["state_after"])
        self.assertEqual(h.head_seq, k)

    def test_an_adoption_after_an_adoption_is_valid(self):
        b, data, k, prefix = world()
        first = Z.record_of(prefix, Z.evidence_of(data, k), "ad1")
        events = prefix + [first]
        second = Z.record_of(events, dict(Z.evidence_of(data, k), discarded_from_seq=k + 1), "ad2")
        self.assertEqual(second["evidence"]["discarded_from_seq"], second["seq"])
        chk = V.validate_history(H.history_of(events + [second]))
        self.assertEqual((chk.head_seq, chk.effective_seqs), (k + 1, tuple(range(k + 2))))
        first_chk = V.validate_history(H.history_of(events))
        self.assertEqual(chk.state_digest, first_chk.state_digest)

    def test_claimed_head_values_are_not_range_checked(self):
        b, data, k, prefix = world()
        base = Z.evidence_of(data, k)
        for name, value in (("seq none", {"claimed_head_seq": None}), ("seq negative", {"claimed_head_seq": -7}),
                            ("seq zero", {"claimed_head_seq": 0}), ("seq huge", {"claimed_head_seq": 10 ** 12}),
                            ("hash none", {"claimed_head_hash": None}), ("hash zeros", {"claimed_head_hash": "0" * 64}),
                            ("size one", {"raw_size": 1})):
            with self.subTest(name):
                rec = Z.record_of(prefix, dict(base, **value), "ad1")
                V.validate_history(history_with(prefix, rec))

    def test_apply_after_the_record_has_the_record_as_its_parent(self):
        b, data, k, prefix = world()
        events = prefix + [Z.record_of(prefix, Z.evidence_of(data, k), "ad1")]
        builder = H.HB(world=b.w, events=events)
        builder.apply(D[6])
        chk = builder.check()
        self.assertEqual(builder.events[-1]["parent_seq"], k)
        self.assertEqual(chk.effective_seqs, tuple(range(k + 2)))
        self.assertEqual(chk.latest_apply_d, D[6])


class EachRule(unittest.TestCase):
    """Design 3.2: the seven checks in their order; each is broken alone and the rule it names is the one reported."""

    def setUp(self):
        self.b, self.data, self.k, self.prefix = world()
        self.ev = Z.evidence_of(self.data, self.k)

    def rule(self, **kw):
        rec = Z.record_of(self.prefix, kw.pop("evidence", self.ev), kw.pop("rid", "ad1"), **kw)
        return H.rule_of(self, history_with(self.prefix, rec))

    def test_1_request_id(self):
        b = H.example_u()                                                       # a RESTART_UNKNOWN with id q1
        prefix = b.events
        rec = Z.record_of(prefix, self.ev, "q1")
        H.expect_rule(self, "request_id", H.history_of(prefix + [rec]))
        for bad in ("", "has space", 5, None, "x" * 500):
            with self.subTest(repr(bad)[:20]):
                rec = Z.record_of(self.prefix, self.ev, bad)
                H.expect_rule(self, "request_id", history_with(self.prefix, rec))

    def test_2_state_after(self):
        for name, state in (("initial state", H.initial_state()), ("none", None), ("other", {"x": 1})):
            with self.subTest(name):
                self.assertEqual(self.rule(over={"state_after": state}), "state_after")

    def test_3_adoption_evidence_keys_and_type(self):
        for name, ev in (("none", None), ("list", []), ("string", "x"), ("empty", {})):
            with self.subTest(name):
                self.assertEqual(self.rule(evidence=ev), "adoption_evidence")
        for key in sorted(self.ev):
            with self.subTest("missing " + key):
                ev = dict(self.ev)
                del ev[key]
                self.assertEqual(self.rule(evidence=ev), "adoption_evidence")
        for extra in ("x", "claimed_core_sha"):
            with self.subTest("extra " + extra):
                self.assertEqual(self.rule(evidence=dict(self.ev, **{extra: 1})), "adoption_evidence")

    def test_3_adoption_evidence_values(self):
        cases = {
            "raw_sha256 upper-case": {"raw_sha256": "A" * 64}, "raw_sha256 short": {"raw_sha256": "a" * 63},
            "raw_sha256 long": {"raw_sha256": "a" * 65}, "raw_sha256 int": {"raw_sha256": 5},
            "raw_sha256 none": {"raw_sha256": None},
            "raw_size zero": {"raw_size": 0}, "raw_size negative": {"raw_size": -1}, "raw_size bool": {"raw_size": True},
            "raw_size float": {"raw_size": 3.0}, "raw_size text": {"raw_size": "3"}, "raw_size none": {"raw_size": None},
            "schema 1": {"claimed_schema_version": 1}, "schema 3": {"claimed_schema_version": 3},
            "schema text": {"claimed_schema_version": "2"}, "schema bool": {"claimed_schema_version": True},
            "schema none": {"claimed_schema_version": None}, "schema float": {"claimed_schema_version": 2.0},
            "head_seq bool": {"claimed_head_seq": True}, "head_seq text": {"claimed_head_seq": "5"},
            "head_seq float": {"claimed_head_seq": 5.0}, "head_seq list": {"claimed_head_seq": [5]},
            "head_hash upper-case": {"claimed_head_hash": "A" * 64}, "head_hash short": {"claimed_head_hash": "a" * 5},
            "head_hash int": {"claimed_head_hash": 0},
            "discarded_from before": {"discarded_from_seq": self.k - 1},
            "discarded_from after": {"discarded_from_seq": self.k + 1}, "discarded_from bool": {"discarded_from_seq": True},
            "discarded_from text": {"discarded_from_seq": str(self.k)}, "discarded_from none": {"discarded_from_seq": None},
            "discarded_from zero": {"discarded_from_seq": 0},
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(evidence=dict(self.ev, **change)), "adoption_evidence")

    def test_3_the_evidence_rule_is_the_only_one_that_fails_for_these(self):
        # the basis carries the same evidence and the hashes are fresh, so nothing else is wrong
        rec = Z.record_of(self.prefix, dict(self.ev, raw_size=0), "ad1")
        self.assertEqual(rec["request_basis"]["evidence"], rec["evidence"])
        self.assertEqual(rec["request_hash"], H.request_hash(rec["request_basis"]))
        H.expect_rule(self, "adoption_evidence", history_with(self.prefix, rec))

    def test_4_request_basis(self):
        other = dict(self.ev, raw_size=self.ev["raw_size"] + 1)
        cases = {
            "evidence differs": dict(basis_over={"evidence": other}),
            "request_id differs": dict(basis_over={"request_id": "other"}),
            "key missing reason": dict(basis_over={"reason_code": GONE}),
            "key missing evidence": dict(basis_over={"evidence": GONE}),
            "key missing request_id": dict(basis_over={"request_id": GONE}),
            "key missing requested_at": dict(basis_over={"requested_at": GONE}),
            "extra key": dict(basis_over={"x": 1}),
            "basis none": dict(over={"request_basis": None}),
            "basis list": dict(over={"request_basis": []}),
            "basis text": dict(over={"request_basis": "x"}),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(**kw), "request_basis")

    def test_5_requested_at(self):
        later = "2026-11-04T00:00:00Z"
        cases = {
            "basis differs": dict(basis_over={"requested_at": later}),
            "record differs": dict(over={"requested_at": later}),
            "not canonical text in both": dict(when="2026-11-03T01:02:03+00:00"),
            "not text in both": dict(when=5),
            "none in both": dict(when=None),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(**kw), "requested_at")

    def test_6_reason_code(self):
        cases = {
            "basis only": dict(basis_over={"reason_code": "RESTORE_VERIFIED_RECORD"}),
            "record only": dict(over={"reason_code": "RESTORE_VERIFIED_RECORD"}),
            "both other": dict(basis_over={"reason_code": "OTHER"}, over={"reason_code": "OTHER"}),
            "record none": dict(over={"reason_code": None}),
            "record lower-case": dict(over={"reason_code": "adopt_verified_prefix"}),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(**kw), "reason_code")

    def test_7_request_hash(self):
        full_basis = Z.record_of(self.prefix, self.ev, "ad1")["request_basis"]
        cases = {
            "zeros": "0" * 64, "upper-case": "A" * 64, "short": "a" * 63, "none": None, "int": 5,
            "hash of the basis with requested_at": Z.sha_text(Z.cj(full_basis)),
        }
        for name, value in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rule(over={"request_hash": value}), "request_hash")

    def test_the_order_of_the_checks(self):
        # a record that breaks several at once reports the first of the design's order
        both = self.rule(over={"state_after": H.initial_state(), "request_hash": "0" * 64})
        self.assertEqual(both, "state_after")
        both = self.rule(evidence=dict(self.ev, raw_size=0), over={"request_hash": "0" * 64})
        self.assertEqual(both, "adoption_evidence")
        both = self.rule(basis_over={"request_id": "z"}, over={"requested_at": "2026-11-04T00:00:00Z"})
        self.assertEqual(both, "request_basis")
        both = self.rule(basis_over={"requested_at": "2026-11-04T00:00:00Z", "reason_code": "O"})
        self.assertEqual(both, "requested_at")
        both = self.rule(basis_over={"reason_code": "O"}, over={"request_hash": "0" * 64})
        self.assertEqual(both, "reason_code")
        both = self.rule(over={"request_id": "q1"})
        self.assertEqual(both, "request_basis")                     # the basis keeps the other id: the id itself is fine


class Placement(unittest.TestCase):
    """A5-05: the position of the record is judged by the rules that already exist."""

    def adoption_at(self, events, pos, rid="adx"):
        data = Z.X.file_of(events[:pos] + [Z.deep(events[pos - 1])])           # only the evidence values are needed
        return Z.record_of(events[:pos], Z.evidence_of(data, pos), rid)

    def test_before_the_migration(self):
        b, _ = H.example_m()
        ev = b.events
        rec = self.adoption_at(ev, 2)
        got = H.insert_record(ev, 2, rec)
        H.expect_rule(self, "migration_position", H.rebuild(got))

    def test_inside_a_request_batch(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.resolution([{"kind": "ACK", "variant": "ADDED", "d": D[1], "fps": [H.fp(H.P.obs("X%d" % i, D[1], 40.0 + i))],
                       "applied": 1} for i in range(3)], "qb")                   # records 2, 3, 4
        for pos in (3, 4):
            with self.subTest(pos):
                got = H.insert_record(b.events, pos, self.adoption_at(b.events, pos))
                H.expect_rule(self, "batch", H.rebuild(got))
        after_batch = H.deep(b.events)
        V.validate_history(H.history_of(after_batch + [self.adoption_at(after_batch, len(after_batch))]))

    def test_inside_the_window_of_a_restore(self):
        ev = H.example_r1().events                                              # RESTORE at 7, records 8..10 follow
        for pos in (8, 9, 10):
            with self.subTest(pos):
                got = H.insert_record(ev, pos, self.adoption_at(ev, pos))
                H.expect_rule(self, "restore_incomplete", H.rebuild(got))
        V.validate_history(H.history_of(ev + [self.adoption_at(ev, len(ev))]))     # after the whole window it is fine

    def test_the_parent_must_be_the_record_before(self):
        b, data, k, prefix = world()
        for parent in (0, k - 2, k, None):
            with self.subTest(parent):
                rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1", over={"parent_seq": parent})
                H.expect_rule(self, "parent", history_with(prefix, rec))
        rec = Z.record_of(prefix, Z.evidence_of(data, k), "ad1", over={"parent_hash": "0" * 64})
        H.expect_rule(self, "audit_hash", history_with(prefix, rec))               # the audit chain, a rule of its own

    def test_a_request_id_of_an_effective_record_is_refused_in_every_kind_of_record(self):
        histories = {"restart": H.example_u().events, "migrated": H.example_m()[0].events,
                     "restore": H.example_r1().events}
        seen = set()
        for name, ev in histories.items():
            chain = H.chain_of(ev)
            for s in chain:
                rid = ev[s].get("request_id")
                if not rid:
                    continue
                seen.add(ev[s]["kind"])
                with self.subTest("%s %s %s" % (name, ev[s]["kind"], rid)):
                    rec = self.adoption_at(ev, len(ev), rid=rid)
                    H.expect_rule(self, "request_id", H.history_of(ev + [rec]))
        self.assertTrue({"RESTART_UNKNOWN", "SCHEMA_MIGRATION", "RECOVERY_RESTORE", "ACK"} <= seen, seen)

    def test_the_checker_looks_at_the_chain_view_only_so_the_physical_ids_are_the_adoption_plans_work(self):
        # an id that only a superseded record used is not in the chain view: B-1 accepts it (prepare refuses it, A5-11)
        ev = H.example_r().events
        chain = set(H.chain_of(ev))
        gone = sorted({e["request_id"] for i, e in enumerate(ev) if i not in chain and e.get("request_id")}
                      - {ev[s].get("request_id") for s in chain})
        self.assertTrue(gone)
        for rid in gone:
            with self.subTest(rid):
                rec = self.adoption_at(ev, len(ev), rid=rid)
                V.validate_history(H.history_of(ev + [rec]))

    def test_the_id_of_a_later_record_is_refused_too(self):
        b, data, k, prefix = world()
        rec = Z.record_of(prefix, Z.evidence_of(data, k), "twice")
        events = prefix + [rec]
        builder = H.HB(world=b.w, events=events)
        builder.restart(D[7], "twice")
        H.expect_rule(self, "request_id", builder.history())

    def test_a_record_after_an_adoption_may_be_any_ordinary_kind(self):
        b, data, k, prefix = world()
        events = prefix + [Z.record_of(prefix, Z.evidence_of(data, k), "ad1")]
        builder = H.HB(world=b.w, events=events)
        builder.apply(D[6])
        builder.declare(D[7], "qd")
        builder.restart(D[9], "qr")
        builder.check()


if __name__ == "__main__":
    unittest.main()
