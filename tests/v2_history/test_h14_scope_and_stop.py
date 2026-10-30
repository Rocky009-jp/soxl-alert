"""H-14: the runtime package has no I/O, clock, network, process, thread, random or environment access, uses only the
listed public names of the existing packages, creates no plan for restoring / restarting / projecting / running a day,
and changes no existing package."""
import ast
import os
import re
import unittest

import h_helpers as H

ROOT = H.ROOT
PKG = os.path.join(ROOT, "v2_history")

ALLOWED_STD = {"copy", "json", "math", "re", "dataclasses", "typing"}
ALLOWED_NAMES = {
    # v2_persistence
    "canonical_json", "sha256_text", "compute_event_hash", "encode_snapshot", "decode_snapshot", "Snapshot",
    "CORE_SHA", "utc_text", "GENESIS_KEYS", "APPLY_KEYS", "SESSION_KEYS", "make_genesis_event", "make_apply_event",
    "snapshot_dict", "snapshot_of", "session_dict", "project_context", "input_hash_of", "validate_snapshot",
    "PersistenceError",
    # v2_recovery
    "validate_resolutions", "resolve_observations", "empty_resolutions", "ResolutionSet", "record_hash_of",
    "request_hash_of", "is_requested_text", "requested_text", "valid_request_id", "set_dict", "ledger_digest",
    "parse_ledger", "sessions_digest", "copy_sessions",
    # v2_core
    "MarketState", "SessionList", "parse_iso_date", "CoreError", "InputError", "ConflictError"}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "print", "breakpoint", "globals", "locals",
                   "setattr", "delattr"}
LATER_STAGE_NAMES = ("prepare_restore_plan", "prepare_restart", "prepare_prefix_adoption", "diagnose_history_bytes",
                     "HistoryReplacement", "HistoryAppendBatch", "prepare_resolved_day", "prepare_day",
                     "prepare_history", "MemoryHistoryStore", "unlock", "outbox", "notify", "CONSUME_", "def consume",
                     "send_", "webhook", "discord")


def sources():
    out = {}
    for name in sorted(os.listdir(PKG)):
        if name.endswith(".py"):
            with open(os.path.join(PKG, name), encoding="utf-8") as f:
                out[name] = f.read()
    return out


class RuntimeIsPure(unittest.TestCase):
    def test_only_python_files_and_no_data_files(self):
        names = sorted(n for n in os.listdir(PKG) if n != "__pycache__")
        self.assertTrue(all(n.endswith(".py") for n in names), names)
        self.assertEqual(names, sorted(["__init__.py", "common.py", "errors.py", "genesis.py", "migrate.py",
                                        "migration.py", "restore.py", "validate.py", "values.py", "view.py"]))

    def test_imports_are_standard_pure_modules_or_listed_existing_names(self):
        for name, text in sources().items():
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name.split(".")[0], ALLOWED_STD, "%s imports %s" % (name, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                                         # a relative import inside v2_history
                        continue
                    top = (node.module or "").split(".")[0]
                    if top in ALLOWED_STD:
                        continue
                    self.assertIn(top, ("v2_core", "v2_persistence", "v2_recovery"), "%s imports %s" % (name, node.module))
                    for a in node.names:
                        self.assertIn(a.name, ALLOWED_NAMES, "%s imports %s.%s" % (name, node.module, a.name))
                        self.assertFalse(a.name.startswith("_"))

    def test_no_io_clock_network_process_thread_random_or_environment(self):
        banned = re.compile(r"\b(os|sys|io|socket|subprocess|threading|multiprocessing|time|datetime|random|secrets|"
                            r"pathlib|shutil|tempfile|urllib|http|ssl|signal|asyncio|logging|environ|getenv|"
                            r"uuid|ctypes|importlib|pickle)\b\s*[.(]")
        for name, text in sources().items():
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, "%s calls %s" % (name, node.func.id))
            code = "\n".join(line.split("#")[0] for line in text.splitlines())
            code = re.sub(r'"""(.|\n)*?"""', "", code)
            self.assertIsNone(banned.search(code), "%s: %s" % (name, banned.search(code)))

    def test_no_private_name_of_an_existing_package_is_used(self):
        pattern = re.compile(r"\b(snapshot|resolutions|history|rset|plan|result)\._(?!text\b|view\b)\w+")
        for name, text in sources().items():
            self.assertIsNone(pattern.search(text), name)
        for name, text in sources().items():
            self.assertNotIn("._internal(", text, name)

    def test_nothing_for_a_later_stage_exists(self):
        for name, text in sources().items():
            for word in LATER_STAGE_NAMES:
                self.assertNotIn(word, text, "%s mentions %s" % (name, word))
        import v2_history
        public = set(v2_history.__all__)
        for word in ("restore", "restart", "consume", "project", "daily", "unlock", "publish", "diagnose"):
            self.assertFalse([n for n in public if word in n.lower() and not n.endswith(("RESTORE", "UNKNOWN"))],
                             word)

    def test_the_public_surface_is_exactly_the_planned_one(self):
        import v2_history
        self.assertEqual(sorted(v2_history.__all__), sorted([
            "History", "encode_history", "decode_history", "validate_history", "make_history_genesis",
            "migrated_sources", "prepare_migration_plan", "confirm_migration_plan", "HistoryCheck", "Boundary",
            "MigrationPlan", "MigrationConfirmResult", "SCHEMA_VERSION_V2", "KINDS", "GENESIS", "APPLY", "ACK",
            "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "READY",
            "CONFIRMED_IN_MEMORY"]))
        for name in v2_history.__all__:
            self.assertTrue(hasattr(v2_history, name))
        self.assertEqual(v2_history.SCHEMA_VERSION_V2, 2)
        self.assertEqual(len(v2_history.KINDS), 7)
        self.assertEqual((v2_history.READY, v2_history.CONFIRMED_IN_MEMORY), ("READY", "CONFIRMED_IN_MEMORY"))

    def test_consume_and_the_b5_kind_are_refused(self):
        import v2_history.values as values
        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", values.KINDS)
        self.assertNotIn("CONSUME", sources()["restore.py"].split("_ALLOWED")[1].split("\n\n")[0])


class ExistingPackagesAreUntouched(unittest.TestCase):
    def test_no_existing_package_mentions_or_depends_on_v2_history(self):
        for pkg in ("v2_core", "v2_persistence", "v2_recovery"):
            for dirpath, _dirs, files in os.walk(os.path.join(ROOT, pkg)):
                for f in files:
                    if f.endswith(".py"):
                        with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                            self.assertNotIn("v2_history", fh.read(), os.path.join(dirpath, f))

    def test_v2_history_does_not_change_the_existing_checkers_behaviour(self):
        # importing v2_history leaves the S1 checker refusing a schema-2 value, as before
        from v2_persistence.codec import Snapshot
        from v2_persistence.recompute import validate_snapshot
        H.expect_field(self, "unsupported_schema", "schema_version", validate_snapshot,
                       Snapshot.from_dict(H.example_u().history().to_dict()))

    def test_the_test_builder_is_not_imported_by_the_runtime(self):
        for name, text in sources().items():
            self.assertNotIn("h_helpers", text)
            self.assertNotIn("tests", text.replace("# tests", ""))


class IoGuard(unittest.TestCase):
    def test_the_checks_and_plans_run_with_the_network_blocked(self):
        import socket
        with self.assertRaises(RuntimeError):
            socket.socket()
        w, snap, rs, ledger, check_d = H.example_m_world()
        h = H.migrate(w, snap, rs, ledger, check_d)
        H.V.validate_history(h)
        H.example_r().check()


if __name__ == "__main__":
    unittest.main()
