"""C-14: no I/O, no unlock/restore, no persistence of the new values; a day result cannot be committed anywhere."""
import ast
import os
import shutil
import tempfile
import unittest

import r_helpers as H
from r_helpers import D, R
from v2_persistence.codec import Snapshot
from v2_persistence.local import LocalFileStore
from v2_persistence.runner import make_genesis

PKG = os.path.join(H.ROOT, "v2_recovery")
ALLOWED_STDLIB = {"copy", "json", "re", "math", "dataclasses", "typing", "datetime"}
FORBIDDEN_NAMES = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                   "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                   "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "hashlib", "uuid", "webbrowser", "smtplib"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs"}


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


class NoSideEffectsInTheRuntime(unittest.TestCase):
    def test_imports_are_limited(self):
        count = 0
        for fname, tree in sources():
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                                   # a relative import inside the package
                        count += 1
                        continue
                    mods = [node.module]
                for m in mods:
                    count += 1
                    top = m.split(".")[0]
                    ok = top in ALLOWED_STDLIB or top in ("v2_core", "v2_persistence")
                    self.assertTrue(ok, "%s imports %s" % (fname, m))
                    self.assertNotIn(top, FORBIDDEN_NAMES, fname)
                    self.assertNotRegex(m, r"^v2_persistence\.local", fname)
                    self.assertNotEqual(m, "v2_persistence.store", fname)       # no MemoryStore, no commit
        self.assertGreater(count, 20)

    def test_no_io_clock_process_or_randomness_calls(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        self.assertNotIn(f.id, FORBIDDEN_CALLS, fname)
                    if isinstance(f, ast.Attribute):
                        self.assertNotIn(f.attr, FORBIDDEN_ATTRS, fname)
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_NAMES - {"time"}, fname)

    def test_nothing_unlocks_restores_restarts_or_persists(self):
        """Identifiers and string values (docstrings excluded) never name an unlock, restore, restart or sink."""
        words = ("unlock", "restore", "restart", "reinit", "outbox", "webhook", "discord", "lock", "snapshot.json",
                 "correction", "notify", "sheet")
        checked = 0
        for fname, tree in sources():
            docs = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
                    first = node.body[0]
                    if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
                        docs.add(id(first.value))
            for node in ast.walk(tree):
                values = []
                if isinstance(node, ast.Name):
                    values.append(node.id)
                elif isinstance(node, ast.Attribute):
                    values.append(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    values.append(node.name)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    values.append(node.value)
                for v in values:
                    checked += 1
                    for w in words:
                        self.assertNotIn(w, v.lower(), "%s: %r" % (fname, v))
        self.assertGreater(checked, 500)

    def test_the_package_defines_no_path_or_store_parameter(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    names = [a.arg for a in node.args.args + node.args.kwonlyargs]
                    for banned in ("path", "root", "store", "file", "filename", "url", "token", "webhook", "account"):
                        self.assertNotIn(banned, names, "%s.%s" % (fname, node.name))


class CommittedFlags(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        self.a = self.w.ledger[0]
        self.b = H.P.obs("B1", D[1], 40.0, hour=21)
        self.ledger = [self.a, self.b]
        self.cmds = [H.ack(self.snap, "ADDED", D[1], [H.fp(self.b)])]

    def test_plan_confirm_no_change_and_day_are_never_committed(self):
        plan = H.plan_for(self.w, self.rs, self.cmds, self.ledger, D[1])
        done = R.confirm_resolution_plan(plan, plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)
        again = H.plan_for(self.w, done.resolutions, self.cmds, self.ledger, D[1])
        same = R.confirm_resolution_plan(again, again.plan_hash, self.snap, done.resolutions, self.w.sessions, self.ledger)
        day = R.prepare_resolved_day(self.snap, done.resolutions, D[1], self.w.series, self.w.sessions, self.ledger)
        new_day = R.prepare_resolved_day(self.snap, done.resolutions, D[1], self.w.series, self.w.sessions, self.ledger)
        self.assertEqual((plan.status, plan.committed), ("READY", False))
        self.assertEqual((done.status, done.committed, done.state_unchanged), ("CONFIRMED_IN_MEMORY", False, True))
        self.assertEqual((again.status, again.committed), ("NO_CHANGE", False))
        self.assertEqual((same.status, same.committed), ("NO_CHANGE", False))
        self.assertEqual((day.committable, day.committed, new_day.committable), (False, False, False))
        for text in (repr(plan), repr(done), repr(same), repr(day)):
            self.assertNotIn("COMMITTED", text.replace("committed=False", ""))

    def test_the_resolution_set_is_not_part_of_the_s1_snapshot_format(self):
        done = H.run(self.w, self.rs, self.cmds, self.ledger, D[1])
        for key in ("resolutions", "records", "resolution_set"):
            data = self.snap.to_dict()
            data[key] = done.resolutions.to_dict()
            with self.assertRaises(H.PersistenceError) as cm:
                H.validate_snapshot(Snapshot.from_dict(data))
            self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "header_keys"))
        events = self.snap.events
        events.append(dict(done.resolutions.records[0], kind="ACK"))
        data = dict(self.snap.to_dict(), events=events)
        with self.assertRaises(H.PersistenceError) as cm:
            H.validate_snapshot(Snapshot.from_dict(data))
        self.assertEqual(cm.exception.code, "unsupported_event")


class CannotBeCommitted(unittest.TestCase):
    def setUp(self):
        self.w = H.world(1)
        self.snap = self.w.snap()
        self.rs = R.empty_resolutions()
        ledger = list(self.w.ledger) + [H.P.obs("R2", D[2], 33.0)]
        self.day = R.prepare_resolved_day(self.snap, self.rs, D[2], self.w.series, self.w.sessions, ledger)
        self.assertEqual(self.day.status, "PREPARED")
        done = H.run(self.w, self.rs, [H.ack(self.snap, "ROW_REMOVED", D[1], [])], [], D[1])
        self.things = [self.day, self.day.candidate_event_text, self.day.core_result, done.effective_ledger,
                       done.resolutions, R.empty_resolutions(), {"event": self.day.candidate_event_text}, None]

    def test_memory_store_refuses_every_such_value_and_stays_unchanged(self):
        store = self.w.store                                    # a real MemoryStore holding the S1 history
        before = store.read()
        for thing in self.things:
            with self.subTest(type=type(thing).__name__):
                with self.assertRaises(H.PersistenceError) as cm:
                    store.commit(thing)
                self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
        self.assertEqual(store.read(), before)
        self.assertEqual((store.read().head_seq, store.read().head_hash), (before.head_seq, before.head_hash))

    def test_local_file_store_on_an_empty_uninitialized_root_stays_empty(self):
        root = tempfile.mkdtemp(prefix="v2s3a_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            for thing in self.things:
                with self.subTest(type=type(thing).__name__):
                    with self.assertRaises(H.PersistenceError) as cm:
                        store.commit(thing)
                    self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
            self.assertEqual(os.listdir(root), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_local_file_store_initialized_with_file_sync_only_keeps_content_and_leaves_nothing(self):
        root = tempfile.mkdtemp(prefix="v2s3a_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            genesis = make_genesis(D[0], self.w.sessions)
            store.initialize(genesis)
            path = os.path.join(root, "snapshot.json")
            with open(path, "rb") as f:
                content = f.read()
            names = sorted(os.listdir(root))
            mtime = os.stat(path).st_mtime_ns
            for thing in self.things:
                with self.assertRaises(H.PersistenceError):
                    store.commit(thing)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), content)
            self.assertEqual(sorted(os.listdir(root)), names)             # no lock, no temporary file left
            self.assertEqual(os.stat(path).st_mtime_ns, mtime)
            self.assertEqual(store.read().head_seq, 0)
            self.assertEqual(store.read().head_hash, genesis.head_hash)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TextFormAndStrictness(unittest.TestCase):
    def test_round_trip_and_strict_decoding(self):
        w = H.world(1)
        done = H.run(w, R.empty_resolutions(), [H.declare(D[2])], list(w.ledger), D[2])
        text = R.encode_resolutions(done.resolutions)
        self.assertEqual(R.decode_resolutions(text), done.resolutions)
        self.assertEqual(R.decode_resolutions(R.encode_resolutions(R.empty_resolutions())), R.empty_resolutions())
        dup = text.replace('"head_resolution_seq":1', '"head_resolution_seq":1,"head_resolution_seq":1', 1)
        for name, bad in {"duplicate": dup, "nan": text.replace('"head_resolution_seq":1', '"head_resolution_seq":NaN', 1),
                          "not_json": "{", "type": 5}.items():
            with self.subTest(name):
                H.expect_rule(self, "json" if isinstance(bad, str) else "type", R.decode_resolutions, bad)
        H.expect_rule(self, "type", R.encode_resolutions, "x")
        H.expect_rule(self, "json_number", R.ResolutionSet.from_dict, {"a": float("nan")})
        H.expect_rule(self, "json_type", R.ResolutionSet.from_dict, {"a": (1, 2)})
        H.expect_rule(self, "json_key", R.ResolutionSet.from_dict, {1: 2})

    def test_bool_is_not_an_integer_and_unknown_things_are_refused(self):
        w = H.world(1)
        snap = w.snap()
        data = R.empty_resolutions().to_dict()
        data["head_resolution_seq"] = False
        H.expect_rule(self, "head", R.validate_resolutions, snap, R.ResolutionSet.from_dict(data))
        data = R.empty_resolutions().to_dict()
        data["records"] = {}
        H.expect_rule(self, "records", R.validate_resolutions, snap, R.ResolutionSet.from_dict(data))
        H.expect_code(self, "snapshot_invalid", R.validate_resolutions, "not a snapshot", R.empty_resolutions())


if __name__ == "__main__":
    unittest.main()
