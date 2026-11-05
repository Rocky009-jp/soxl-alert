"""S4B-17: the static range of the runtime. It brings in only the standard modules datetime, hashlib, json, os, secrets and
stat, v2_core, v2_persistence.local.fsops, v2_daily_run (and its own modules); the OS is reached only through the S2 FileOps
methods that the request lists; there is no socket, process, thread, clock, random (except secrets.token_hex for the claim
id), environment variable or network use, no replace / rename / unlink, and no v2_history* import. The codes it spells
are the codes of the earlier stages."""
import ast
import unittest

import s4b_helpers as H

S = H.S

RUNTIME = tuple("v2_notify/%s.py" % n for n in ("__init__", "compose", "job", "outbox", "values"))
STANDARD = {"datetime", "hashlib", "json", "os", "secrets", "stat"}
ALLOWED_FROM = {
    "v2_core.errors": {"CoreError"},
    "v2_core.sessions": {"SessionList"},
    "v2_persistence.local.fsops": {"FileOps"},
    "v2_persistence.local.store": {"FILE_SYNC_ONLY_MODE", "STRICT"},
    "v2_daily_run": {"DONE", "RunError", "RunReport", "run_morning"},
}
OWN_MODULES = {".compose", ".job", ".outbox", ".values"}
FORBIDDEN_NAMES = {"socket", "subprocess", "urllib", "http", "time", "random", "threading", "environ", "getenv",
                   "putenv", "sys", "io", "shutil", "tempfile", "pathlib", "logging", "asyncio", "multiprocessing",
                   "signal", "ssl", "ctypes", "sqlite3", "glob", "uuid", "requests", "smtplib"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print", "setattr", "globals", "locals",
                   "breakpoint", "exit", "quit"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "putenv",
                   "system", "popen", "random", "randbytes", "token_bytes", "token_urlsafe", "choice", "Thread", "Popen",
                   "run", "replace", "rename", "renames", "unlink", "remove", "rmdir", "removedirs", "makedirs", "mkdir",
                   "chmod", "chown", "truncate", "symlink", "link", "write_text", "write_bytes", "connect", "sendall",
                   "sendto", "urlopen"}
FILE_OPS_ALLOWED = {"create_exclusive", "open_writer", "write", "flush", "fsync_file", "close", "close_fd", "fsync_dir",
                    "probe_dir_sync", "read_file", "listdir", "lstat", "is_windows"}


def trees():
    return {p: ast.parse(S.read_source(p)) for p in RUNTIME}


class Runtime(unittest.TestCase):
    def test_the_package_is_the_five_files_of_the_design(self):
        for path in RUNTIME:
            S.read_source(path)
        self.assertLessEqual(len(RUNTIME), 5)

    def test_the_imports_are_the_list_of_the_design(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name, STANDARD, "%s imports %s" % (path, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        self.assertIn("." * node.level + (node.module or ""), OWN_MODULES, path)
                        continue
                    if node.module in STANDARD:
                        continue
                    self.assertIn(node.module, ALLOWED_FROM, "%s imports from %s" % (path, node.module))
                    self.assertTrue({a.name for a in node.names} <= ALLOWED_FROM[node.module],
                                    "%s imports %s from %s" % (path, [a.name for a in node.names], node.module))
                    self.assertFalse(node.module.startswith("v2_history"), path)

    def test_no_process_network_thread_clock_random_or_environment_use(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, "%s uses .%s" % (path, node.attr))
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_NAMES, "%s uses %s" % (path, node.id))

    def test_the_clock_is_never_read_and_secrets_gives_only_the_claim_id(self):
        uses = []
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("datetime", "secrets"):
                    uses.append((path, node.value.id, node.attr))
        self.assertEqual(sorted(uses), sorted([
            ("v2_notify/compose.py", "datetime", "datetime"),
            ("v2_notify/job.py", "datetime", "datetime"),
            ("v2_notify/job.py", "datetime", "timezone"),
            ("v2_notify/outbox.py", "secrets", "token_hex"),
        ]))
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and ast.unparse(node.func) == "secrets.token_hex":
                    self.assertEqual([ast.unparse(a) for a in node.args], ["16"])

    def test_os_is_used_only_for_path_joins_and_the_absolute_path_check(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertEqual(node.attr, "path", path)
                if isinstance(node, ast.Attribute) and ast.unparse(node.value) == "os.path":
                    self.assertIn(node.attr, ("join", "isabs"), path)

    def test_the_file_system_is_reached_only_through_the_listed_s2_file_operations(self):
        used = set()
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and ast.unparse(node.value) in ("ops", "self._ops"):
                    self.assertIn(node.attr, FILE_OPS_ALLOWED, "%s uses ops.%s" % (path, node.attr))
                    used.add(node.attr)
        self.assertEqual(used, FILE_OPS_ALLOWED)

    def test_the_sender_is_called_only_as_send_with_the_text(self):
        calls = []
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "send":
                    calls.append((path, ast.unparse(node)))
        self.assertEqual(calls, [("v2_notify/job.py", "sender.send(text)")])

    def test_the_store_is_only_handed_to_run_morning(self):
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "store":
                    self.fail("%s touches the store: .%s" % (path, node.attr))

    def test_no_path_text_or_exception_text_goes_into_a_value(self):
        # str(e) / repr(e) of an exception is never taken, and no exception object is stored in a value
        for path, tree in trees().items():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("str", "repr"):
                    self.assertNotIn("e", [ast.unparse(a) for a in node.args], path)
                if isinstance(node, ast.Attribute) and node.attr in ("args", "__traceback__", "__context__", "__cause__"):
                    self.fail("%s reads .%s" % (path, node.attr))

    def test_the_codes_it_spells_are_the_codes_of_the_earlier_stages(self):
        import v2_daily_run.values as RV
        import v2_history_ops as O
        import v2_notify.values as V
        self.assertEqual(V.PUBLISH_UNCERTAIN, RV.PUBLISH_UNCERTAIN)
        self.assertEqual(V.PUBLISH_CONFLICT, RV.PUBLISH_CONFLICT)
        self.assertEqual(O.NO_COMMIT, "NO_COMMIT")
        from v2_notify import compose
        self.assertEqual(compose.NO_COMMIT_STATUS, O.NO_COMMIT)
        for rel, code in (("v2_history_local/store.py", V.STORE_BUSY), ("v2_history_local/store.py", V.PUBLICATION_STALE),
                          ("v2_recovery/facts.py", V.TARGET_NOT_AFTER_BOUNDARY)):
            self.assertIn('"%s"' % code, S.read_source(rel), (rel, code))
        self.assertEqual((V.SENDER_SENT, V.SENDER_NOT_STARTED), ("SENT", "NOT_STARTED"))
        self.assertEqual(V.EXIT_OK, RV.EXIT_OK)
        self.assertEqual(V.EXIT_NOT_OK, RV.EXIT_NOT_OK)
        self.assertEqual(V.date_text("2026-02-29"), "2026-02-29")             # a plausible date text; the calendar is the sessions'

    def test_the_names_of_the_request_are_public(self):
        import v2_notify
        for name in ("morning_job", "resend", "outbox_status", "compose_notice", "compose_error_notice", "LocalOutbox",
                     "Notice", "JobReport", "ResendReport", "NotifyError"):
            self.assertTrue(hasattr(v2_notify, name), name)
        self.assertTrue(issubclass(v2_notify.NotifyError, H.CoreError))


if __name__ == "__main__":
    unittest.main()
