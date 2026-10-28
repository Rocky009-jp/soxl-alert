"""B-10: no network / notification / credential / clock / recovery path in the runtime; errors carry codes only;
every worker inherits the network block."""
import ast
import json
import os
import re
import subprocess
import sys
import traceback
import unittest

import l_helpers as H
from v2_persistence.local import LocalFileStore, LocalStoreError

PKG = os.path.join(H.ROOT, "v2_persistence", "local")
ALLOWED_IMPORTS = {"os", "stat", "secrets", "sys", "dataclasses", "typing"}
FORBIDDEN_NAMES = {"socket", "ssl", "http", "urllib", "requests", "smtplib", "ftplib", "subprocess", "multiprocessing",
                   "threading", "datetime", "time", "random", "environ", "getenv", "putenv", "sleep", "shutil",
                   "tempfile", "glob", "webbrowser", "asyncio", "sched", "signal"}


def sources():
    for n in sorted(os.listdir(PKG)):
        if n.endswith(".py"):
            with open(os.path.join(PKG, n), encoding="utf-8") as f:
                yield n, f.read()


class StaticBoundary(unittest.TestCase):
    def test_only_stdlib_and_the_existing_packages_are_imported(self):
        for name, src in sources():
            for node in ast.walk(ast.parse(src)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                                     # relative: stays inside v2_persistence
                        continue
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertTrue(m in ALLOWED_IMPORTS, "%s imports %s" % (name, m))

    def test_no_network_clock_environment_or_process_names_are_used(self):
        for name, src in sources():
            names = set()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
            self.assertEqual(names & FORBIDDEN_NAMES, set(), name)

    def test_no_recovery_or_unlock_or_retry_api(self):
        import v2_persistence.local as pkg
        public = set(pkg.__all__) | set(dir(LocalFileStore))
        for word in ("unlock", "force", "recover", "restore", "repair", "retry", "ack", "notify", "send", "fetch",
                     "download", "cron", "schedule", "today", "now"):
            self.assertFalse([n for n in public if not n.startswith("_") and word in n.lower()], word)

    def test_only_the_three_managed_names_exist(self):
        src = dict(sources())["store.py"]
        literals = set(re.findall(r'"([^"\n]*\.(?:json|lock|tmp))"', src))
        self.assertEqual(literals, {"snapshot.json", "write.lock", ".tmp"})

    def test_no_network_namespace_leak_in_this_process(self):
        import socket
        with self.assertRaises(RuntimeError):
            socket.socket()


class WorkersInheritTheBlock(unittest.TestCase):
    def test_worker_processes_cannot_open_sockets(self):
        r = H.run_worker({"mode": "probe"})
        self.assertTrue(r["socket_blocked"])


class ErrorsAreCodesOnly(H.RootCase):
    def setUp(self):
        super().setUp()
        self.sc = H.Scenario()
        H.init_root(self.root, self.sc, advance=1)
        d = self.sc.day(2)
        self.sc.observe(d, 50)
        self.plan = self.sc.prepare(LocalFileStore(self.root).read(), d).plan

    def test_injected_os_errors_leave_no_trace_in_public_errors(self):
        points = [("create_exclusive", "lock"), ("write", "lock"), ("listdir", None), ("read_file", "snapshot"),
                  ("lstat", "snapshot"), ("create_exclusive", "tmp"), ("write", "tmp"), ("flush", "tmp"),
                  ("fsync_file", "tmp"), ("close", "tmp"), ("replace", None), ("fsync_dir", None),
                  ("unlink", "lock"), ("probe_dir_sync", None)]
        raised = 0
        for op, kind in points:
            with self.subTest(op=op, kind=kind):
                for after in (False, True):
                    ops = H.FaultOps().fail(op, kind, after=after)
                    # leftovers from an earlier subTest may stop the call; clear them test-side
                    for n in os.listdir(self.root):
                        if n != H.SNAP:
                            os.unlink(os.path.join(self.root, n))
                    try:
                        LocalFileStore(self.root, writable=True, _ops=ops).commit(self.plan)
                    except LocalStoreError as e:
                        raised += 1
                        text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                        for needle in (H.SECRET, "injected failure", self.root, "Errno"):
                            self.assertNotIn(needle, text)
                            self.assertNotIn(needle, str(e) + repr(e) + repr(e.args))
                        self.assertIsNone(e.__cause__)
                        self.assertIsNone(e.__context__)
                        self.assertIn(e.phase, __import__("v2_persistence.local.errors", fromlist=["PHASES"]).PHASES)
                        self.assertEqual(str(e), "%s:%s" % (e.code, e.field))
                    # commit may legitimately succeed when the injected op is never reached in this order
                    if H.SNAP in os.listdir(self.root):
                        H.put(self.root, H.SNAP, H.raw(self.root))

        self.assertGreaterEqual(raised, 20)

    def test_errors_never_contain_paths_for_ordinary_refusals(self):
        H.put(self.root, ".snapshot.x.tmp", b"")
        with self.assertRaises(LocalStoreError) as cm:
            LocalFileStore(self.root).read()
        self.assertNotIn(self.root, str(cm.exception) + repr(cm.exception.args))

    def test_result_values_carry_the_documented_fields(self):
        res = LocalFileStore(self.root, writable=True).commit(self.plan)
        self.assertEqual(sorted(vars(res)), ["committed", "persistence_level", "snapshot", "status"])
        self.assertNotIn(self.root, repr(res))


if __name__ == "__main__":
    unittest.main()
