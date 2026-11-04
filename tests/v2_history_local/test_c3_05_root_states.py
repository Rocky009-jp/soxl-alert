"""C3-08: the table of design 4.2 -- four operations in six root states. Nothing in a root is touched by a refusal."""
import os
import unittest

import c3_helpers as H

TMP = ".history.0123456789abcdef0123456789abcdef.tmp"
S2TMP = ".snapshot.0123456789abcdef0123456789abcdef.tmp"
V1 = b'{"v1": "stands in for the old snapshot"}'


class Table(H.RootCase):
    def setUp(self):
        super().setUp()
        self.day = H.C2.day_case()
        self.genesis = H.C2.genesis_case()

    def make(self, state):
        if state == "empty":
            return
        if state == "history":
            return self.put_current(self.day)
        if state == "v1_only":
            return H.put(self.root, H.V1, V1)
        if state == "both":
            self.put_current(self.day)
            return H.put(self.root, H.V1, V1)
        if state == "tmp":
            self.put_current(self.day)
            return H.put(self.root, TMP, b"left behind")
        if state == "s2tmp":
            self.put_current(self.day)
            return H.put(self.root, S2TMP, b"left behind")
        if state == "lock":
            self.put_current(self.day)
            return H.put(self.root, H.LOCK, b"somebody's marker\n")
        raise AssertionError(state)

    def outcome(self, op, state):
        store = self.store()
        pub = self.genesis.pub if (op == "initialize" or (op == "reconcile" and state == "empty")) else self.day.pub
        try:
            res = getattr(store, op)() if op == "read" else getattr(store, op)(pub)
        except Exception as e:
            return (e.code, getattr(e, "rule", None))
        return ("ok", getattr(res, "outcome", getattr(res, "status", "history")))

    EXPECTED = {
        "empty": {"read": ("store_uninitialized", None), "initialize": ("ok", "INITIALIZED"),
                  "publish": ("store_uninitialized", None), "reconcile": ("ok", "NOT_PUBLISHED")},
        "history": {"read": ("ok", "history"), "initialize": ("already_initialized", None),
                    "publish": ("ok", "PUBLISHED"), "reconcile": ("ok", "NOT_PUBLISHED")},
        "v1_only": {op: ("store_layout_unsupported", "v1_only") for op in ("read", "initialize", "publish",
                                                                           "reconcile")},
        "both": {op: ("store_layout_unsupported", "v1_and_v2") for op in ("read", "initialize", "publish",
                                                                          "reconcile")},
        "tmp": {"read": ("store_artifact_present", None), "initialize": ("store_artifact_present", None),
                "publish": ("store_artifact_present", None), "reconcile": ("ok", "NOT_PUBLISHED")},
        "s2tmp": {"read": ("store_artifact_present", None), "initialize": ("store_artifact_present", None),
                  "publish": ("store_artifact_present", None), "reconcile": ("ok", "NOT_PUBLISHED")},
        "lock": {op: ("store_busy", None) for op in ("read", "initialize", "publish", "reconcile")},
    }

    def test_every_cell(self):
        for state, row in self.EXPECTED.items():
            for op, expected in row.items():
                with self.subTest(state=state, op=op):
                    root = H.make_root()
                    self.addCleanup(__import__("shutil").rmtree, root, True)
                    self.root = root
                    self.make(state)
                    self.assertEqual(self.outcome(op, state), expected)

    def test_a_refusal_leaves_the_root_as_it_was(self):
        for state in ("v1_only", "both", "tmp", "s2tmp", "lock"):
            for op in ("read", "initialize", "publish"):
                with self.subTest(state=state, op=op):
                    root = H.make_root()
                    self.addCleanup(__import__("shutil").rmtree, root, True)
                    self.root = root
                    self.make(state)
                    before = H.state_of(root)
                    self.outcome(op, state)
                    self.assertEqual(H.state_of(root), before)

    def test_reconcile_with_a_leftover_tmp_still_answers_per_the_files(self):
        # the leftover does not stop it, and the answer is about history.json only
        self.make("tmp")
        res = self.store().reconcile(self.day.pub)
        self.assertEqual(res.outcome, "NOT_PUBLISHED")
        H.put(self.root, H.HIST, H.C2.file_bytes(self.day.candidate))
        self.assertEqual(self.store().reconcile(self.day.pub).outcome, "PUBLISHED")
        self.assertEqual(H.raw(self.root, TMP), b"left behind")

    def test_the_order_of_the_checks(self):
        # lock first (the lock decides before any file is listed), then v1, then the leftovers
        self.make("both")
        H.put(self.root, TMP, b"x")
        e = self.run_err(self.store().read)
        self.assertEqual(e.code, "store_layout_unsupported")
        H.put(self.root, H.LOCK, b"x\n")
        e = self.run_err(self.store().read)
        self.assertEqual(e.code, "store_busy")

    def test_other_names_are_not_looked_at(self):
        self.make("history")
        os.mkdir(os.path.join(self.root, "quarantine"))
        H.put(self.root, "notes.txt", b"hello")
        H.put(self.root, ".snapshot.json.bak", b"x")        # does not match the pattern .snapshot.*.tmp
        H.put(self.root, ".history.keep", b"x")             # does not end with .tmp
        H.put(self.root, "x.history.1.tmp", b"x")           # does not start with .history.
        before = H.state_of(self.root)
        self.assertEqual(self.store().read(), self.day.history)
        self.store().publish(self.day.pub)
        self.assertEqual(sorted(set(H.listing(self.root)) - set(before)), [])
        self.assertTrue(os.path.isdir(os.path.join(self.root, "quarantine")))

    def test_a_directory_named_like_a_tmp_file_also_stops(self):
        self.make("history")
        os.mkdir(os.path.join(self.root, TMP))
        self.assertEqual(self.run_err(self.store().publish, self.day.pub).code, "store_artifact_present")

    def test_a_failed_listing_is_an_io_error_without_the_path(self):
        self.make("history")
        ops = H.C3Ops().fail("listdir")
        e = self.run_err(self.store(ops).read)
        self.assertStore(e, "store_io_error", "root", "scan")
        self.assertNotIn(H.SECRET, str(e) + repr(e.__dict__))
        self.assertEqual(H.listing(self.root), ["history.json"])      # the lock was released


if __name__ == "__main__":
    unittest.main()
