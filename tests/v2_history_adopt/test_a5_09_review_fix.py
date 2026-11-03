"""R-01 (review of S3-B-5b): the plan's own `discarded` block is checked in its form and in what the plan itself proves,
before the data is looked at, on every path (original bytes, the candidate's bytes, other bytes, no bytes). Controls: the
shapes that the diagnosis really gives are not refused (an empty block, null read values, a negative declared seq, an
unknown kind "?", several items in sequence)."""
import unittest

import a5_helpers as Z
from a5_helpers import H, X
from v2_persistence.errors import PersistenceError

MISMATCH = ("history_plan_mismatch", "plan", None)
STALE = ("history_plan_stale", "plan", None)
DATA_TYPE = ("adoption_invalid", "data", "type")


def item(block, **edits):
    return dict(block["items"][0], **edits)


def breakages(block, count):
    """Every way to break one point of the discarded block (the plan's own values, with one item at least)."""
    first = block["items"][0]
    return {
        "empty": {},
        "not_a_dict": [],
        "none": None,
        "negative_count": dict(block, count=-1),
        "bool_count": dict(block, count=True),
        "float_count": dict(block, count=float(block["count"])),
        "text_count": dict(block, count=str(block["count"])),
        "wrong_start": dict(block, from_index=0),
        "bool_start": dict(block, from_index=True),
        "text_start": dict(block, from_index=str(block["from_index"])),
        "wrong_count": dict(block, count=block["count"] + 1),
        "count_zero_with_items": dict(block, count=0),
        "items_not_list": dict(block, items="wrong"),
        "items_tuple_like_dict": dict(block, items={"0": first}),
        "items_empty_with_count": dict(block, items=[]),
        "extra_key": dict(block, extra=0),
        "missing_key": {k: v for k, v in block.items() if k != "items"},
        "item_not_dict": dict(block, items=[7]),
        "item_empty": dict(block, items=[{}]),
        "item_extra_key": dict(block, items=[dict(first, extra=1)]),
        "item_missing_seq": dict(block, items=[{k: v for k, v in first.items() if k != "seq"}]),
        "item_wrong_index": dict(block, items=[item(block, index=count + 1)]),
        "item_bool_index": dict(block, items=[item(block, index=True)]),
        "item_text_index": dict(block, items=[item(block, index=str(first["index"]))]),
        "item_bool_seq": dict(block, items=[item(block, seq=True)]),
        "item_float_seq": dict(block, items=[item(block, seq=1.0)]),
        "item_text_seq": dict(block, items=[item(block, seq="1")]),
        "item_unknown_kind": dict(block, items=[item(block, kind="BOGUS")]),
        "item_kind_none": dict(block, items=[item(block, kind=None)]),
        "item_kind_lowercase": dict(block, items=[item(block, kind="apply")]),
        "item_bad_day": dict(block, items=[item(block, d=7)]),
        "item_bad_day_text": dict(block, items=[item(block, d="2026-13-40")]),
        "item_bad_request_id": dict(block, items=[item(block, request_id="has space")]),
        "item_request_id_number": dict(block, items=[item(block, request_id=5)]),
    }


def outcome(plan, data):
    try:
        return Z.confirm(plan, data).status
    except PersistenceError as e:
        return (e.code, e.field, e.rule)


def with_discarded(plan, value):
    """The plan whose discarded block is `value` and whose hash is calculated again: only the content is wrong."""
    return Z.refreshed(plan, lambda d: d["basis"].__setitem__("discarded", value))


class BrokenBlock(unittest.TestCase):
    def setUp(self):
        _b, self.data, self.k = Z.new_world()
        self.plan = Z.prep(self.data, self.k)
        self.candidate = Z.candidate_bytes(self.data, self.k)
        self.block = self.plan.basis["discarded"]

    def test_the_control_world_has_a_block_with_one_item(self):
        self.assertEqual((self.block["from_index"], self.block["count"], len(self.block["items"])), (self.k, 1, 1))
        self.assertEqual(outcome(self.plan, self.data), "CONFIRMED_IN_MEMORY")
        self.assertEqual(outcome(self.plan, self.candidate), "NO_CHANGE")

    def test_every_break_is_a_mismatch_on_every_path(self):
        other = self.data[:-1]
        paths = {"original": self.data, "candidate": self.candidate, "other": other, "none": None, "str": "x",
                 "bytearray": bytearray(self.candidate)}
        for name, value in breakages(self.block, self.k).items():
            plan = with_discarded(self.plan, value)
            for path, data in paths.items():
                with self.subTest("%s/%s" % (name, path)):
                    self.assertEqual(outcome(plan, data), MISMATCH)

    def test_a_block_whose_items_agree_with_a_start_that_is_not_adopt_count_is_a_mismatch(self):
        # every item is in place for the start the block states, so only the start itself is wrong
        start = self.k + 1
        value = {"from_index": start, "count": 1, "items": [item(self.block, index=start)]}
        plan = with_discarded(self.plan, value)
        for data in (self.data, self.candidate, None):
            with self.subTest(type(data).__name__):
                self.assertEqual(outcome(plan, data), MISMATCH)

    def test_items_that_are_empty_but_not_a_list_are_a_mismatch(self):
        for name, items in (("dict", {}), ("text", ""), ("none", None), ("zero", 0)):
            plan = with_discarded(self.plan, {"from_index": self.k, "count": 0, "items": items})
            for data in (self.data, self.candidate, None):
                with self.subTest("%s/%s" % (name, type(data).__name__)):
                    self.assertEqual(outcome(plan, data), MISMATCH)

    def test_the_reproduction_of_the_review_with_only_the_block_wrong_and_the_hash_right(self):
        # the review's own reproduction: only the content of the block is wrong and the hash is right
        plan = with_discarded(self.plan, {})
        self.assertEqual(plan.plan_hash, Z.sha_text(Z.cj(plan.basis)))
        self.assertEqual(outcome(plan, self.candidate), MISMATCH)
        self.assertEqual(outcome(plan, None), MISMATCH)

    def test_a_broken_block_is_refused_before_the_data_is_read(self):
        # the error of the data's type must not come first, whatever the data is
        plan = with_discarded(self.plan, {"from_index": self.k, "count": -1, "items": []})
        for data in (None, "x", 5, bytearray(b"x"), memoryview(b"x"), b"", self.data):
            with self.subTest(type(data).__name__):
                self.assertEqual(outcome(plan, data), MISMATCH)

    def test_a_good_block_still_reports_the_type_of_the_data_first_among_the_data_errors(self):
        for data in (None, "x", bytearray(self.data)):
            with self.subTest(type(data).__name__):
                self.assertEqual(outcome(self.plan, data), DATA_TYPE)

    def test_a_block_that_is_right_in_form_but_not_the_diagnosis_is_still_caught_by_the_original_bytes(self):
        # the plan alone cannot prove the content; the original bytes can (the whole basis is rebuilt and compared)
        wrong = dict(self.block, items=[item(self.block, kind="?")])
        plan = with_discarded(self.plan, wrong)
        self.assertEqual(outcome(plan, self.data), MISMATCH)
        # for the candidate's bytes the form is all that can be checked: it is not claimed to prove more
        self.assertEqual(outcome(plan, self.candidate), "NO_CHANGE")

    def test_other_bytes_of_a_good_plan_are_still_stale(self):
        self.assertEqual(outcome(self.plan, self.data[:-1]), STALE)
        self.assertEqual(outcome(self.plan, Z.X.indented(self.candidate)), STALE)

    def test_the_hash_that_is_not_calculated_again_is_a_mismatch_as_before(self):
        d = self.plan.to_dict()
        d["basis"]["discarded"] = {}
        plan = Z.A.AdoptionPlan.from_dict(d)
        self.assertEqual(outcome(plan, self.candidate), MISMATCH)


class ShapesTheDiagnosisGives(unittest.TestCase):
    """The block that prepare really makes is never refused by the new check."""

    def confirm_both(self, data, k):
        plan = Z.prep(data, k)
        self.assertEqual(outcome(plan, data), "CONFIRMED_IN_MEMORY")
        self.assertEqual(outcome(plan, Z.candidate_bytes(data, k)), "NO_CHANGE")
        return plan

    def test_an_empty_block_when_only_the_header_is_damaged(self):
        data = X.file_of(X.ex_new().events, head_hash=Z.ZERO)
        plan = self.confirm_both(data, 7)
        self.assertEqual(plan.basis["discarded"], {"from_index": 7, "count": 0, "items": []})

    def test_several_items_in_sequence(self):
        b = X.ex_new()
        data = X.file_of(X.with_hash(b.events, 2))
        d = X.diagnose(data)
        k = d["verified"]["count"]
        plan = self.confirm_both(data, k)
        items = plan.basis["discarded"]["items"]
        self.assertEqual([i["index"] for i in items], list(range(k, k + len(items))))
        self.assertGreater(len(items), 1)

    def test_null_read_values_a_negative_declared_seq_and_an_unknown_kind(self):
        ev = Z.deep(X.ex_new().events)
        tail = [{"kind": "BOGUS", "seq": -5, "d": "2026-01-02", "request_id": "rid-1"}, {"x": 1},
                {"kind": "APPLY", "seq": None, "d": None, "request_id": None}, 7]
        doc = H.header(ev[:5])
        doc["events"] = ev[:5] + tail
        data = X.doc_bytes(doc)
        plan = self.confirm_both(data, 5)
        items = plan.basis["discarded"]["items"]
        self.assertEqual([(i["kind"], i["seq"], i["d"], i["request_id"]) for i in items],
                         [("?", -5, "2026-01-02", "rid-1"), ("?", None, None, None), ("APPLY", None, None, None),
                          ("?", None, None, None)])

    def test_a_migrated_prefix_and_a_restore_prefix(self):
        moved = X.ex_m()                                # the migration record stays in the prefix: two more days, last damaged
        moved.apply(Z.D[5], 30.0)
        moved.apply(Z.D[6], 31.0)
        for name, b in (("migrated", moved), ("restore", H.example_r1())):
            with self.subTest(name):
                data, k = Z.damaged_last(b)
                self.confirm_both(data, X.diagnose(data)["verified"]["count"])

    def test_every_kind_of_the_fixed_list_is_a_good_kind_for_an_item(self):
        _b, data, k = Z.new_world()
        plan = Z.prep(data, k)
        block = plan.basis["discarded"]
        for kind in tuple(Z.V.KINDS) + ("?",):
            with self.subTest(kind):
                changed = with_discarded(plan, dict(block, items=[item(block, kind=kind)]))
                self.assertEqual(outcome(changed, Z.candidate_bytes(data, k)), "NO_CHANGE")


if __name__ == "__main__":
    unittest.main()
