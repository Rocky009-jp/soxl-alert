"""SC-02: the range tests form one gap-free chain.

The range tests are found automatically (a tests/**/test_*.py with a top-level START and a class FilesChanged) and
START / END are read from their syntax tree at REV, never by importing them. The chain starts at the one START that is
no END, passes through every range test exactly once, each START is an ancestor of its END, each END is an ancestor of
the tip, and END = None is allowed only on the last range. A chain whose beginning exists in the history but whose
middle is missing fails; a tree without history skips.
"""
import copy
import unittest

import sc_helpers as C
from test_sc_03_scope import REV, START

CHAIN_START = "adfdf765aeca0d01c8f10b596a6fac59d7c1a07e"
CHAIN = [  # path: START -> END of the accepted ranges, in order
    ("tests/v2_history_ops/test_b17_scope.py", CHAIN_START, "b328844fdeda235cf95bf7851ba9e3d7d55aa7bb"),
    ("tests/v2_history_restart/test_r3_07_scope.py", "b328844fdeda235cf95bf7851ba9e3d7d55aa7bb",
     "d82a5ced64658c2e736b82b1a2f1925636055417"),
    ("tests/v2_history_restore/test_r4_09_scope.py", "d82a5ced64658c2e736b82b1a2f1925636055417",
     "ac219801d290ebb59b720f37a086103b6e1251c9"),
    ("tests/v2_history_diagnose/test_d5_08_scope.py", "ac219801d290ebb59b720f37a086103b6e1251c9",
     "c8ba08f15ea28248a9fe7924f32ce136fc16d5e6"),
    ("tests/v2_history_adopt/test_a5_08_scope.py", "c8ba08f15ea28248a9fe7924f32ce136fc16d5e6",
     "b626c98af5f01bc94e7b41d86aadde9663695eb9"),
]


def ancestor(older, newer):
    return C.is_ancestor(older, newer)


class Chain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skip_reason = None
        cls.rows = []
        if not C.commit_exists(CHAIN_START):
            cls.skip_reason = "the history is not available in this checkout"
        elif not C.commit_exists(REV):
            cls.skip_reason = "the revision under test is not available"
        else:
            cls.rows = C.range_tests(REV)

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def test_the_range_tests_found_are_the_accepted_five_and_this_stage(self):
        paths = sorted(r["path"] for r in self.rows)
        self.assertEqual(paths, sorted([c[0] for c in CHAIN] + ["tests/v2_scope_chain/test_sc_03_scope.py"]))

    def test_the_real_chain_has_no_gap_and_no_overlap(self):
        self.assertEqual(C.judge_chain(self.rows, ancestor, REV, CHAIN_START), [])

    def test_the_real_chain_is_in_the_accepted_order(self):
        by_start = {r["start"]: r for r in self.rows}
        walked, current = [], by_start[CHAIN_START]
        while True:
            walked.append(current)
            if current["end"] is None:
                break
            current = by_start[current["end"]]
        self.assertEqual([(r["path"], r["start"], r["end"]) for r in walked[:5]], CHAIN)
        self.assertEqual(len(walked), 6)
        last = walked[-1]
        self.assertEqual((last["path"], last["start"]), ("tests/v2_scope_chain/test_sc_03_scope.py", START))

    def test_the_open_range_is_the_last_one_only(self):
        opens = [r["path"] for r in self.rows if r["end"] is None]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0], "tests/v2_scope_chain/test_sc_03_scope.py")


class ChainJudge(unittest.TestCase):
    """The judge rejects wrong tables (the tables are built here from the rows read from the syntax trees)."""

    @classmethod
    def setUpClass(cls):
        cls.skip_reason = None
        cls.rows = []
        if not C.commit_exists(CHAIN_START):
            cls.skip_reason = "the history is not available in this checkout"
        elif not C.commit_exists(REV):
            cls.skip_reason = "the revision under test is not available"
        else:
            cls.rows = C.range_tests(REV)

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)
        self.table = copy.deepcopy(self.rows)
        self.assertEqual(C.judge_chain(self.table, ancestor, REV, CHAIN_START), [])

    def row(self, name):
        return [r for r in self.table if r["path"].endswith(name)][0]

    def problems(self):
        return C.judge_chain(self.table, ancestor, REV, CHAIN_START)

    def test_a_duplicated_start_is_rejected(self):
        self.row("test_r3_07_scope.py")["start"] = self.row("test_b17_scope.py")["start"]
        self.assertTrue(any("more than once" in p for p in self.problems()), self.problems())

    def test_a_gap_is_rejected(self):
        self.table = [r for r in self.table if not r["path"].endswith("test_r4_09_scope.py")]
        self.assertTrue(any("gap" in p or "chain beginnings" in p for p in self.problems()), self.problems())

    def test_a_range_that_the_chain_does_not_reach_is_rejected(self):
        """Two extra ranges that follow each other in a loop have no beginning of their own; the walk from the real
        beginning does not reach them."""
        first, second = "a" * 40, "b" * 40
        self.table.append({"path": "tests/x/test_loop_1.py", "start": first, "end": second})
        self.table.append({"path": "tests/x/test_loop_2.py", "start": second, "end": first})
        self.assertTrue(any("gap" in p for p in self.problems()), self.problems())

    def test_a_gap_at_the_beginning_is_rejected(self):
        self.table = [r for r in self.table if not r["path"].endswith("test_b17_scope.py")]
        self.assertTrue(any("begins at" in p for p in self.problems()), self.problems())

    def test_an_end_that_is_not_an_ancestor_of_its_start_is_rejected(self):
        row = self.row("test_d5_08_scope.py")
        row["start"], row["end"] = row["end"], row["start"]      # END is older than START
        self.table.sort(key=lambda r: r["path"])
        self.assertTrue(self.problems())
        self.assertTrue(any("ancestor" in p or "chain" in p for p in self.problems()), self.problems())

    def test_a_start_that_is_not_an_ancestor_of_the_end_is_rejected_with_a_connected_chain(self):
        a, b = self.row("test_r4_09_scope.py"), self.row("test_d5_08_scope.py")
        outside = "0" * 40
        a["end"] = outside
        b["start"] = outside                                    # still connected, but not a commit of the history
        self.assertTrue(any("ancestor" in p for p in self.problems()), self.problems())

    def test_two_open_ranges_are_rejected(self):
        self.row("test_a5_08_scope.py")["end"] = None
        self.assertTrue(any("open range" in p for p in self.problems()), self.problems())

    def test_an_open_range_that_is_not_last_is_rejected(self):
        self.row("test_b17_scope.py")["end"] = None
        self.assertTrue(any("open range" in p or "gap" in p for p in self.problems()), self.problems())

    def test_a_missing_end_is_rejected(self):
        self.row("test_d5_08_scope.py")["end"] = "<missing>"
        self.assertTrue(any("no END" in p for p in self.problems()), self.problems())

    def test_an_end_that_is_not_an_ancestor_of_the_tip_is_rejected(self):
        row = self.row("test_b17_scope.py")
        other = self.row("test_r3_07_scope.py")
        fake = "f" * 40
        row["end"] = fake
        other["start"] = fake
        self.assertTrue(self.problems())

    def test_a_chain_without_any_beginning_is_rejected(self):
        self.row("test_b17_scope.py")["start"] = self.row("test_a5_08_scope.py")["end"]
        self.assertTrue(self.problems())


if __name__ == "__main__":
    unittest.main()
