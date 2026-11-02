"""D5-06 VALID, D5-14 claimed and verified."""
import unittest

import d5_helpers as X
from d5_helpers import G


def expected_verified(check, events, document_text):
    """The verified keys from the checker's own result and from independent facts about the document."""
    return {"count": len(events), "head_seq": check.head_seq, "head_hash": check.head_hash,
            "state_digest": X.text_sha(X.cj(events[-1]["state_after"])), "document_digest": X.text_sha(document_text),
            "boundary": {"kind": check.current_boundary.kind, "seq": check.current_boundary.seq,
                         "after": check.current_boundary.after},
            "latest_apply_d": check.latest_apply_d, "processing_after": check.processing_after,
            "effective_count": len(check.effective_seqs), "superseded_count": len(check.superseded_seqs),
            "migrated": check.migrated}


class ValidHistories(unittest.TestCase):
    def check_valid(self, builder):
        data = X.history_file(builder)
        check = X.V.validate_history(builder.history())
        d = X.diagnose(data)
        text = data.decode("utf-8")
        self.assertEqual(d["status"], "VALID")
        self.assertEqual(d["operation"], "soxl-v2-history-diagnosis/1")
        self.assertEqual(d["schema_version"], 2)
        self.assertIsNone(d["failure"])
        self.assertIsNone(d["discarded"])
        self.assertIs(d["canonical_text"], True)
        self.assertEqual(d["raw_sha256"], X.sha(data))
        self.assertEqual(d["raw_size"], len(data))
        self.assertEqual(d["verified"], expected_verified(check, builder.events, text))
        self.assertEqual(d["verified"]["document_digest"], d["raw_sha256"])
        self.assertEqual(d["verified"]["count"], len(builder.events))
        self.assertEqual(d["claimed"], {"schema_version": 2, "core_sha_matches": True, "head_seq": len(builder.events) - 1,
                                        "head_hash": builder.events[-1]["event_hash"],
                                        "event_count": len(builder.events)})
        return d

    def test_a_new_history(self):
        d = self.check_valid(X.ex_new())
        self.assertIs(d["verified"]["migrated"], False)
        self.assertEqual(d["verified"]["effective_count"], 7)
        self.assertEqual(d["verified"]["superseded_count"], 0)

    def test_a_migrated_history(self):
        d = self.check_valid(X.ex_m())
        self.assertIs(d["verified"]["migrated"], True)

    def test_a_migrated_history_without_earlier_acknowledgements(self):
        self.assertIs(self.check_valid(X.ex_m_empty())["verified"]["migrated"], True)

    def test_example_r_three_restores(self):
        d = self.check_valid(X.ex_r())
        self.assertEqual(d["verified"]["count"], 23)
        self.assertEqual(d["verified"]["effective_count"], 8)
        self.assertEqual(d["verified"]["superseded_count"], 15)

    def test_example_r_b(self):
        self.check_valid(X.ex_rb())

    def test_a_restart_history(self):
        d = self.check_valid(X.ex_u())
        self.assertEqual(d["verified"]["boundary"]["kind"], "RESTART_UNKNOWN")

    def test_a_declared_and_acknowledged_history(self):
        self.check_valid(X.H.example_r13())

    def test_the_same_value_written_with_indentation_is_valid_but_not_canonical(self):
        for builder in (X.ex_new(), X.ex_r(), X.ex_m()):
            data = X.history_file(builder)
            wide = X.indented(data)
            self.assertNotEqual(wide, data)
            d = X.diagnose(wide)
            same = X.diagnose(data)
            self.assertEqual(d["status"], "VALID")
            self.assertIs(d["canonical_text"], False)
            self.assertEqual(d["raw_sha256"], X.sha(wide))
            self.assertEqual(d["raw_size"], len(wide))
            self.assertEqual(d["verified"], same["verified"])
            self.assertEqual(d["verified"]["document_digest"], X.sha(data))
            self.assertNotEqual(d["verified"]["document_digest"], d["raw_sha256"])

    def test_canonical_text_never_changes_the_status(self):
        data = X.history_file(X.ex_new())
        for variant in (X.indented(data), data + b"\n", b"  " + data, data.replace(b",", b" ,", 3)):
            d = X.diagnose(variant)
            self.assertEqual(d["status"], "VALID")
            self.assertIs(d["canonical_text"], False)

    def test_a_trailing_newline_is_valid_but_not_canonical(self):
        data = X.history_file(X.ex_new())
        self.assertIs(X.diagnose(data + b"\n")["canonical_text"], False)


class ClaimedValues(unittest.TestCase):
    def test_claimed_types_are_checked(self):
        events = X.ex_new().events
        n = len(events)
        cases = [
            ({"head_seq": True}, {"head_seq": None}),
            ({"head_seq": 3.0}, {"head_seq": None}),
            ({"head_seq": "6"}, {"head_seq": None}),
            ({"head_seq": 99}, {"head_seq": 99}),
            ({"head_hash": "ABC"}, {"head_hash": None}),
            ({"head_hash": "A" * 64}, {"head_hash": None}),
            ({"head_hash": 5}, {"head_hash": None}),
            ({"head_hash": "0" * 64}, {"head_hash": "0" * 64}),
        ]
        for edit, expected in cases:
            d = X.diagnose(X.file_of(events, **edit))
            self.assertEqual(d["status"], "PREFIX_ONLY", edit)
            claimed = d["claimed"]
            for key, value in expected.items():
                self.assertEqual(claimed[key], value, edit)
            self.assertEqual(claimed["event_count"], n)
            self.assertEqual(claimed["schema_version"], 2)
            self.assertIs(claimed["core_sha_matches"], True)

    def test_event_count_is_only_given_for_a_list(self):
        events = X.ex_new().events
        for value in ("text", {}, None, 7):
            d = X.diagnose(X.file_of(events, events=value))
            self.assertEqual(d["status"], "NO_VALID_PREFIX", repr(value))
            self.assertIsNone(d["claimed"]["event_count"])
        d = X.diagnose(X.file_of(events, events=[]))
        self.assertEqual(d["claimed"]["event_count"], 0)

    def test_claimed_is_not_the_checked_value(self):
        events = X.ex_new().events
        d = X.diagnose(X.file_of(events, head_seq=40))
        self.assertEqual(d["claimed"]["head_seq"], 40)
        self.assertEqual(d["verified"]["head_seq"], len(events) - 1)


class StateAndDocumentDigests(unittest.TestCase):
    def test_state_digest_is_of_the_last_state_after(self):
        b = X.ex_new()
        d = X.diagnose(X.history_file(b))
        self.assertEqual(d["verified"]["state_digest"], X.text_sha(X.cj(b.events[-1]["state_after"])))

    def test_state_digest_of_a_prefix_is_of_its_own_last_record(self):
        b = X.ex_new()
        events = X.with_hash(b.events, 5)
        d = X.diagnose(X.file_of(events))
        self.assertEqual(d["verified"]["count"], 5)
        self.assertEqual(d["verified"]["state_digest"], X.text_sha(X.cj(b.events[4]["state_after"])))
        self.assertNotEqual(d["verified"]["state_digest"], X.text_sha(X.cj(b.events[-1]["state_after"])))

    def test_document_digest_of_a_prefix_is_of_the_rebuilt_document(self):
        b = X.ex_new()
        events = X.with_hash(b.events, 5)
        d = X.diagnose(X.file_of(events))
        rebuilt = X.cj(X.H.header(X.deep(events[:5])))
        self.assertEqual(d["verified"]["document_digest"], X.text_sha(rebuilt))
        self.assertNotEqual(d["verified"]["document_digest"], d["raw_sha256"])

    def test_the_status_names_are_the_four_exported_constants(self):
        self.assertEqual((G.VALID, G.PREFIX_ONLY, G.NO_VALID_PREFIX, G.UNREADABLE),
                         ("VALID", "PREFIX_ONLY", "NO_VALID_PREFIX", "UNREADABLE"))


if __name__ == "__main__":
    unittest.main()
