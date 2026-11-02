"""D5-11 schema 1 (the S2 snapshot bytes): the checker of its own version, the v1 column of verified."""
import unittest

import d5_helpers as X
from v2_persistence.codec import Snapshot
from v2_persistence.recompute import validate_snapshot


def v1_verified_expected(snapshot):
    events = snapshot.events
    valid = validate_snapshot(snapshot)
    state = valid.state.to_dict()
    last_apply = valid.applies[-1].d if valid.applies else None
    return {"count": len(events), "head_seq": events[-1]["seq"], "head_hash": events[-1]["event_hash"],
            "state_digest": X.text_sha(X.cj(state)), "document_digest": X.text_sha(X.encode_snapshot(snapshot)),
            "boundary": {"kind": "GENESIS", "seq": 0, "after": events[0]["start_after"]},
            "latest_apply_d": last_apply, "processing_after": state["as_of_d"] or events[0]["start_after"],
            "effective_count": len(events), "superseded_count": 0, "migrated": None}


class ValidSnapshot(unittest.TestCase):
    def test_a_valid_snapshot(self):
        w = X.v1_world(4)
        snap = w.snap()
        data = X.v1_file(snap)
        with X.Spy() as spy:
            d = X.diagnose(data)
        self.assertEqual(d["status"], "VALID")
        self.assertEqual(d["schema_version"], 1)
        self.assertIs(d["canonical_text"], True)
        self.assertIsNone(d["failure"])
        self.assertIsNone(d["discarded"])
        self.assertEqual(d["verified"], v1_verified_expected(snap))
        self.assertEqual(d["verified"]["document_digest"], d["raw_sha256"])
        self.assertIsNone(d["verified"]["migrated"])
        self.assertEqual(d["verified"]["count"], 5)
        self.assertEqual(d["claimed"]["schema_version"], 1)
        self.assertEqual({c[0] for c in spy.calls}, {1}, "schema 1 goes to the snapshot checker only")
        self.assertEqual(len(spy.calls), 1)

    def test_a_genesis_only_snapshot(self):
        snap = X.v1_world(0).snap()
        d = X.diagnose(X.v1_file(snap))
        self.assertEqual(d["status"], "VALID")
        self.assertEqual(d["verified"], v1_verified_expected(snap))
        self.assertIsNone(d["verified"]["latest_apply_d"])
        self.assertEqual(d["verified"]["processing_after"], X.D[0])

    def test_an_indented_snapshot(self):
        snap = X.v1_world(3).snap()
        data = X.v1_file(snap)
        d = X.diagnose(X.indented(data))
        self.assertEqual(d["status"], "VALID")
        self.assertIs(d["canonical_text"], False)
        self.assertEqual(d["verified"]["document_digest"], X.sha(data))

    def test_a_valid_v2_history_never_reaches_the_snapshot_checker(self):
        with X.Spy() as spy:
            d = X.diagnose(X.history_file(X.ex_new()))
        self.assertEqual(d["status"], "VALID")
        self.assertEqual({c[0] for c in spy.calls}, {2})


class DamagedSnapshot(unittest.TestCase):
    def test_a_damaged_last_record(self):
        w = X.v1_world(4)
        snap = w.snap()
        events = X.with_hash(snap.events, 4)
        with X.Spy() as spy:
            d = X.diagnose(X.v1_doc_file(events))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(d["verified"]["count"], 4)
        self.assertEqual(d["verified"]["head_seq"], 3)
        self.assertIsNone(d["verified"]["migrated"])
        self.assertEqual(d["discarded"]["from_index"], 4)
        self.assertEqual(d["discarded"]["items"], [{"index": 4, "kind": "APPLY", "seq": 4, "d": X.D[4],
                                                    "request_id": None}])
        self.assertEqual(d["failure"], {"stage": "validate", "code": "snapshot_invalid", "field": "snapshot",
                                        "rule": "event_hash"})
        self.assertEqual({c[0] for c in spy.calls}, {1})
        self.assertEqual(spy.ks(1), [5, 5, 4])
        # the verified part equals the checker's own result for the first four records under their own header
        self.assertEqual(d["verified"], v1_verified_expected(Snapshot.from_dict(X.snapshot_dict(snap.events[:4]))))

    def test_a_header_only_difference(self):
        snap = X.v1_world(3).snap()
        n = len(snap.events)
        d = X.diagnose(X.v1_doc_file(snap.events, head_hash=X.ZERO))
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], n)
        self.assertEqual(d["discarded"], {"from_index": n, "count": 0, "items": []})
        self.assertEqual(d["failure"]["rule"], "head_hash")
        self.assertEqual(d["verified"], v1_verified_expected(snap))
        self.assertNotEqual(d["verified"]["document_digest"], d["raw_sha256"])

    def test_a_damaged_genesis(self):
        snap = X.v1_world(3).snap()
        n = len(snap.events)
        d = X.diagnose(X.v1_doc_file(X.with_hash(snap.events, 0)))
        self.assertEqual(d["status"], "NO_VALID_PREFIX")
        self.assertEqual(d["schema_version"], 1)
        self.assertIsNone(d["verified"])
        self.assertEqual(d["discarded"]["count"], n)
        self.assertEqual(d["discarded"]["from_index"], 0)

    def test_a_record_of_a_v2_kind_in_a_v1_file_is_not_a_known_kind(self):
        b = X.ex_u()                                     # ends with a RESTART_UNKNOWN
        events = X.deep(b.events)
        d = X.diagnose(X.v1_doc_file(events))
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(d["status"], "PREFIX_ONLY")
        self.assertEqual(d["verified"]["count"], 3)
        self.assertEqual(d["failure"]["code"], "unsupported_event")
        self.assertEqual(d["discarded"]["items"][0]["kind"], "?", "RESTART_UNKNOWN is not a schema-1 kind")

    def test_a_schema_1_snapshot_of_a_different_core_is_unreadable(self):
        snap = X.v1_world(2).snap()
        d = X.diagnose(X.v1_doc_file(snap.events, core_sha="a" * 40))
        self.assertEqual(d["status"], "UNREADABLE")
        self.assertEqual(d["failure"]["field"], "core_sha")

    def test_the_v1_failure_for_an_unexpected_exception_is_malformed_of_the_snapshot(self):
        snap = X.v1_world(2).snap()
        events = X.deep(snap.events)
        events[1]["confirmed_inputs"] = 5                # the checker indexes into it
        d = X.diagnose(X.v1_doc_file(events))
        self.assertEqual(d["failure"]["stage"], "validate")
        self.assertIn(d["failure"]["code"], ("snapshot_invalid",))


class VersionsAreNotMixed(unittest.TestCase):
    """The records of a GENESIS/APPLY-only file are the same in both schemas, so the declared version alone decides
    which unchanged checker is used."""

    def test_the_declared_version_selects_the_checker(self):
        snap = X.v1_world(2).snap()
        with X.Spy() as spy:
            d = X.diagnose(X.v1_doc_file(snap.events, schema_version=2))
        self.assertEqual(d["schema_version"], 2)
        self.assertEqual({c[0] for c in spy.calls}, {2}, "a file that declares version 2 is never given to validate_snapshot")
        with X.Spy() as spy:
            d = X.diagnose(X.file_of(X.ex_new().events, schema_version=1))
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual({c[0] for c in spy.calls}, {1}, "a file that declares version 1 is never given to validate_history")

    def test_a_v2_only_record_in_a_file_that_declares_version_1_is_refused_by_the_snapshot_checker(self):
        d = X.diagnose(X.file_of(X.ex_u().events, schema_version=1))
        self.assertEqual(d["schema_version"], 1)
        self.assertEqual(d["failure"]["code"], "unsupported_event")
        self.assertEqual(d["status"], "PREFIX_ONLY")

    def test_a_v2_history_with_v2_only_records_declared_as_version_2_is_valid(self):
        self.assertEqual(X.diagnose(X.file_of(X.ex_u().events))["status"], "VALID")


if __name__ == "__main__":
    unittest.main()
