"""B4-01 (the change boundary against the code start d82a5ce, read directly from Git) and B4-20 (scope audit of the new
runtime: public dependencies, no I/O, clock, randomness, strategy numbers, B-5 or S3-C, CONSUME only as a refusal)."""
import ast
import os
import subprocess
import unittest

import r4_helpers as R

ROOT = R.ROOT
PKG = os.path.join(ROOT, "v2_history_restore")
TESTS = os.path.join(ROOT, "tests", "v2_history_restore")
START = R.FIXED_START

ALLOWED_STDLIB = {"copy", "json"}
ALLOWED_NAMES = {
    "v2_history": {"History", "validate_history"},
    "v2_history.values": {"history_dict", "check_json"},                       # and the kind-name constants
    "v2_history.common": {"basis_request_hash", "is_int", "is_hex64", "is_date", "same"},
    "v2_history_ops": {"read_effective", "project_history_ledger"},
    "v2_history_ops.errors": {"history_plan_mismatch", "history_plan_stale", "history_request_conflict"},
    "v2_recovery.ledger": {"copy_sessions", "parse_ledger", "ledger_digest", "sessions_digest"},
    "v2_recovery.common": {"requested_text", "is_requested_text", "valid_request_id"},
    "v2_recovery.facts": {"FixedFacts", "LedgerContext"},
    "v2_recovery.commands": {"check_commands"},
    "v2_recovery.project": {"apply_records", "check_versions"},
    "v2_persistence.codec": {"canonical_json", "sha256_text", "compute_event_hash"},
    "v2_persistence.events": {"session_dict", "row_dict", "input_hash_of", "serialize_transition"},
    "v2_persistence.errors": {"PersistenceError"},
    "v2_core.state": {"MarketState"},
    "v2_core.fixture": {"parse_iso_date", "MarketRow"},
    "v2_core.errors": {"CoreError", "InputError", "ConflictError"},
    "v2_core.observations": {"parse_observation", "select_decision"},
    "v2_core.transition": {"apply_transition"},
    "v2_core.engine": {"evaluate_day"},
}
KIND_CONSTANTS = {"ACK", "APPLY", "DECLARE_MISSING", "GENESIS", "RECOVERY_RESTORE", "RESTART_UNKNOWN",
                  "SCHEMA_MIGRATION"}
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "hashlib", "uuid", "webbrowser", "smtplib",
                     "datetime", "tests"}
# the old machinery that must not be borrowed (design 13): private walkers, the S1 view, the S1 plan, the B-2 batch
NEVER_USED = {"Ctx", "SnapshotView", "validate_set", "make_records", "resolve_observations", "Chain", "ledger_of",
              "_Walk", "_Frozen", "HistoryAppendBatch", "check_append_batch", "make_batch", "append_records",
              "prepare_history_day", "prepare_history_resolution_plan", "prepare_day", "AppendPlan", "make_apply_event"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen"}
# later stages: B-5 and S3-C words. "restore" is the name of this stage and is not banned; "consume" is allowed only as
# the refusal below. No store, batch value, durability, outbox, notification or publication.
LATER_STAGE_WORDS = ("unlock", "outbox", "webhook", "discord", "snapshot.json", "notify", "sheet", "historyreplacement",
                     "diagnos", "append_batch", "appendbatch", "adoption", "reinit", "publish", "cas_", "durab", "fsync",
                     "localfile", "memorystore", "journal")
CONSUME_NAMES = {"requires_consume", "restore_requires_consume"}
OWN_CLASSES = {"RestorePlan", "RestoreConfirmResult"}
PUBLIC = ["prepare_restore_plan", "confirm_restore_plan", "RestorePlan", "RestoreConfirmResult", "READY",
          "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
FILES = ["__init__.py", "build.py", "chain.py", "confirm.py", "errors.py", "market.py", "points.py", "prepare.py",
         "records.py", "values.py"]
SCOPE_TESTS = ("tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py")


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


def allowed_path(path):
    """The paths that the new work may add (the two scope tests are the only ones it may modify)."""
    return path.startswith(("v2_history_restore/", "tests/v2_history_restore/")) or path == \
        "docs/implementation/V2_RECOVERY_S3B4_RESULT.md"


# --- generated from the committed diff of the code start (d82a5ce) to the corrected files; pinned as text ---
B17_REMOVED = ['                                        "v2_history_restart/", "tests/v2_history_restart/"))',
 '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))',
 '                       ":(exclude)tests/v2_history_restart")']
B17_ADDED = ['                                        "v2_history_restart/", "tests/v2_history_restart/",',
 '                                        "v2_history_restore/", "tests/v2_history_restore/",',
 '                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))',
 '                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
 '                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
 '                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
 '                             and path != "v2_history_restore/__init__.py"',
 '                             and path != "v2_history_diagnose/__init__.py"',
 '                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",',
 '                       ":(exclude)tests/v2_history_diagnose")']
B17_HUNKS = ['@@ -185 +185,3', '@@ -188 +190,3', '@@ -199,0 +204,2', '@@ -216 +222,2']
R307_REMOVED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/")) or path in (',
 '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",)',
 '        self.assertEqual({p for p in paths if p.endswith("__init__.py")}, {"v2_history_restart/__init__.py"})',
 '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart")',
 '            \'                                        "v2_history_restart/", "tests/v2_history_restart/"))\',',
 '            \'                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md"))\',',
 '            \'                       ":(exclude)tests/v2_history_restart")\'])']
R307_ADDED = ['            allowed = path.startswith(("v2_history_restart/", "tests/v2_history_restart/",',
 '                                       "v2_history_restore/", "tests/v2_history_restore/",',
 '                                       "v2_history_diagnose/", "tests/v2_history_diagnose/")) or path in (',
 '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
 '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md")',
 '        self.assertEqual({p for p in paths if p.endswith("__init__.py")},',
 '                         {"v2_history_restart/__init__.py", "v2_history_restore/__init__.py",',
 '                          "v2_history_diagnose/__init__.py"})',
 '        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restart",',
 '                       ":(exclude)tests/v2_history_restore", ":(exclude)tests/v2_history_diagnose")',
 '            \'                                        "v2_history_restart/", "tests/v2_history_restart/",\',',
 '            \'                                        "v2_history_restore/", "tests/v2_history_restore/",\',',
 '            \'                                        "v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
 '            \'                                   "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",\',',
 '            \'                                   "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
 '            \'                                   "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
 '            \'                             and path != "v2_history_restore/__init__.py"\',',
 '            \'                             and path != "v2_history_diagnose/__init__.py"\',',
 '            \'                       ":(exclude)tests/v2_history_restart", ":(exclude)tests/v2_history_restore",\',',
 '            \'                       ":(exclude)tests/v2_history_diagnose")\'])']
R307_HUNKS = ['@@ -193,2 +193,5', '@@ -199 +202,3', '@@ -207 +212,2', '@@ -225 +231,3', '@@ -227 +235,3', '@@ -228,0 +239,2', '@@ -231 +243,2']


class Runtime(unittest.TestCase):
    def test_only_the_allowed_modules_and_names(self):
        count = 0
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        count += 1
                        self.assertIn(a.name, ALLOWED_STDLIB, "%s imports %s" % (fname, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level:                                              # inside the package
                        count += 1
                        continue
                    mod = node.module
                    self.assertIn(mod, ALLOWED_NAMES, "%s imports from %s" % (fname, mod))
                    for a in node.names:
                        count += 1
                        ok = a.name in ALLOWED_NAMES[mod] or (mod == "v2_history.values" and a.name in KIND_CONSTANTS)
                        self.assertTrue(ok, "%s imports %s.%s" % (fname, mod, a.name))
                        self.assertFalse(a.name.startswith("_"), "%s imports a private name" % fname)
                        self.assertNotIn(a.name, NEVER_USED, fname)
                    self.assertNotIn(mod.split(".")[0], FORBIDDEN_IMPORTS, fname)
                    self.assertNotRegex(mod, r"^v2_persistence\.(local|store|plan)", fname)
        self.assertGreater(count, 60)

    def test_no_name_of_the_old_machinery_appears_anywhere(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, NEVER_USED, fname)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, NEVER_USED, fname)

    def test_no_private_name_of_an_existing_package_is_used(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    base = node.value
                    self.assertTrue(isinstance(base, ast.Name) and (base.id in ("self", "cls", "other", "obj")
                                                                    or base.id in OWN_CLASSES),
                                    "%s uses ._%s of something else" % (fname, node.attr.lstrip("_")))

    def test_no_io_clock_process_thread_random_or_environment(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    f = node.func
                    if isinstance(f, ast.Name):
                        self.assertNotIn(f.id, FORBIDDEN_CALLS, fname)
                    if isinstance(f, ast.Attribute):
                        self.assertNotIn(f.attr, FORBIDDEN_ATTRS, fname)
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, FORBIDDEN_IMPORTS - {"time", "tests"}, fname)

    def test_nothing_of_the_later_stages(self):
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
                    if v in KIND_CONSTANTS:
                        continue
                    for word in LATER_STAGE_WORDS:
                        self.assertNotIn(word, v.lower(), "%s: %s" % (fname, v))
        self.assertGreater(checked, 1000)

    def test_consume_is_only_a_refusal(self):
        found = []
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
                elif isinstance(node, ast.alias):
                    values.append(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    values.append(node.name)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    values.append(node.value)
                for v in values:
                    if "consum" in v.lower():
                        found.append((fname, v))
                        self.assertIn(v, CONSUME_NAMES, "%s: %s" % (fname, v))
        # the one function that raises it and the one place that calls it, and nothing that makes a day of its own
        self.assertEqual(sorted(set(v for _f, v in found)), sorted(CONSUME_NAMES))
        self.assertEqual(sorted(set(f for f, _v in found)), ["build.py", "errors.py"])

    def test_a_new_apply_is_made_only_from_the_day_of_the_record_it_replaces(self):
        sites = []
        for fname, tree in sources():
            for func in ast.walk(tree):
                if not isinstance(func, ast.FunctionDef):
                    continue
                for node in ast.walk(func):
                    if isinstance(node, ast.Dict):
                        keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
                        if "kind" in keys:
                            kind = node.values[keys.index("kind")]
                            if isinstance(kind, ast.Name) and kind.id == "APPLY":
                                sites.append((fname, func.name, node, func))
        self.assertEqual([(f, n) for f, n, _d, _fn in sites], [("records.py", "_reapply")])
        _f, _n, record, func = sites[0]
        keys = [k.value for k in record.keys]
        day = record.values[keys.index("d")]
        self.assertIsInstance(day, ast.Name)
        assigned = [a for a in ast.walk(func) if isinstance(a, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == day.id for t in a.targets)]
        self.assertEqual(len(assigned), 1)
        value = assigned[0].value
        self.assertTrue(isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id == "old"
                        and isinstance(value.slice, ast.Constant) and value.slice.value == "d")

    def test_no_threshold_ratio_or_market_number_is_written(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    self.assertIsInstance(node.value, int, fname)
                    # tuple positions, "+ 1", the number of the keys of a record, the 12-character hash prefix of a repr
                    self.assertIn(node.value, tuple(range(8)) + (12,), "%s holds the number %r" % (fname, node.value))
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("v2_core.state_rules", "v2_core.rules", "v2_core.indicators")), fname)

    def test_the_public_names_are_exactly_the_documented_ones(self):
        self.assertEqual(sorted(R.Z.__all__), sorted(PUBLIC))
        for name in R.Z.__all__:
            self.assertTrue(hasattr(R.Z, name), name)
        self.assertEqual((R.Z.READY, R.Z.CONFIRMED_IN_MEMORY, R.Z.NO_CHANGE), ("READY", "CONFIRMED_IN_MEMORY", "NO_CHANGE"))
        import v2_history
        import v2_history_ops
        import v2_history_restart
        for module in (v2_history, v2_history_ops, v2_history_restart):
            self.assertFalse(any("restore_plan" in n.lower() or "RestorePlan" in n for n in module.__all__))

    def test_the_package_files_and_the_absence_of_dependency_files(self):
        self.assertEqual(sorted(f for f in os.listdir(PKG) if not f.startswith("__pycache__")), FILES)
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(os.path.exists(os.path.join(PKG, name)))
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("tests", "ho_helpers", "h_helpers", "r4_helpers")), fname)

    def test_the_operations_that_may_be_written_are_four_and_everything_else_is_refused(self):
        from v2_history_restore import values
        self.assertEqual(values.OPS, ("REAPPLY", "REPLAY", "DROP", "RETIRE"))
        b = R.ex_restart_between()
        for op, rule in (("CONSUME", "restore_op_unsupported"), ("consume", "restore_op_unsupported"),
                         ("APPLY", "restore_op_unsupported"), ("", "restore_op_unsupported"), (None, "ops_shape"),
                         (1, "ops_shape")):
            ops = R.ops_of(b, 1, {"*": "DROP"})
            ops[0]["op"] = op
            e = R.refusal(R.prep, b, 1, None, R.D[3], "r4-1", ops=ops)
            self.assertEqual((e.code, e.field, e.rule), ("restore_invalid", "ops", rule), op)
        # and no operation of the four makes an APPLY of a day that no record of the history had
        plan = R.prep(b, 1, {2: "DROP", 3: "REAPPLY"}, R.D[3], "r4-1")
        made = [(c["d"], r["d"]) for c, r in zip(plan.basis["changes"][1:], plan.basis["candidate_records"][1:])]
        self.assertEqual(made, [(b.events[3]["d"], b.events[3]["d"])])

    def test_the_new_tests_use_unique_names_and_no_init_file(self):
        self.assertFalse(os.path.exists(os.path.join(TESTS, "__init__.py")))
        names = sorted(f for f in os.listdir(TESTS) if f.endswith(".py"))
        for name in names:
            self.assertTrue(name.startswith("test_r4_") or name in ("r4_helpers.py", "r4_sensitivity.py"), name)
        taken = {}
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
            for f in files:
                if f.endswith(".py") and os.path.abspath(dirpath) != os.path.abspath(TESTS):
                    taken.setdefault(f, dirpath)
        for name in names:
            self.assertNotIn(name, taken, "%s already exists in %s" % (name, taken.get(name)))


class PathJudgement(unittest.TestCase):
    def test_the_judgement_accepts_only_the_exact_new_paths(self):
        yes = ["v2_history_restore/build.py", "tests/v2_history_restore/test_r4_01_point_ops.py",
               "docs/implementation/V2_RECOVERY_S3B4_RESULT.md", "v2_history_restore/__init__.py"]
        no = ["v2_history_restore2/build.py", "v2_history_restores/x.py", "tests/v2_history_restore_x/y.py",
              "v2_history_restart/build.py", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md.bak",
              "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
              "v2_history/validate.py", "main.py", ".github/workflows/x.yml", "tests/v2_history_ops/test_b17_scope.py",
              "docs/STATUS.md", "research/x.py", "requirements.txt"]
        for p in yes:
            self.assertTrue(allowed_path(p), p)
        for p in no:
            self.assertFalse(allowed_path(p), p)


class FilesChanged(unittest.TestCase):
    """Compared with the code start by git (committed state)."""

    def git(self, *args):
        return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True, timeout=60)

    def setUp(self):
        probe = self.git("cat-file", "-e", START + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")

    def test_only_the_allowed_paths_differ(self):
        out = self.git("diff", "--name-status", START, "HEAD")
        self.assertEqual(out.returncode, 0, out.stderr)
        changed = [line.split("\t") for line in out.stdout.splitlines()]
        modified = sorted(p for s, p in changed if s == "M")
        self.assertEqual(modified, sorted(SCOPE_TESTS))                            # the only files that are modified
        for status, path in changed:
            if path in SCOPE_TESTS:
                continue
            new_b5a = path.startswith(("v2_history_diagnose/", "tests/v2_history_diagnose/")) or path == \
                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"
            self.assertTrue(allowed_path(path) or new_b5a, "unexpected change: %s %s" % (status, path))
            self.assertEqual(status, "A", path)                                      # new files only
        paths = {p for _s, p in changed}
        self.assertIn("v2_history_restore/__init__.py", paths)
        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
                         {"v2_history_restore/__init__.py", "v2_history_diagnose/__init__.py"})

    def test_the_b3_runtime_tests_and_result_are_the_same_as_the_code_start(self):
        # read directly: the blob of every file at the code start against the file that is there now
        listing = self.git("ls-tree", "-r", START, "--", "v2_history_restart", "tests/v2_history_restart",
                           "docs/implementation/V2_RECOVERY_S3B3_RESULT.md")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        rows = [line.split() for line in listing.stdout.splitlines()]
        self.assertGreater(len(rows), 12)
        for _mode, kind, blob, path in rows:
            self.assertEqual(kind, "blob")
            if path == "tests/v2_history_restart/test_r3_07_scope.py":
                self.assertNotEqual(self.git("hash-object", path).stdout.strip(), blob)     # the one corrected file
                continue
            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
            self.assertEqual(here.stdout.strip(), blob, path)
        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_history_restart", "tests/v2_history_restart",
                       "docs/implementation/V2_RECOVERY_S3B3_RESULT.md")
        self.assertEqual(out.stdout.split(), ["tests/v2_history_restart/test_r3_07_scope.py"])

    def test_no_existing_runtime_old_test_fixture_or_setting_differs(self):
        out = self.git("diff", "--name-only", START, "HEAD", "--", "v2_core", "v2_persistence", "v2_recovery",
                       "v2_history", "v2_history_ops", "v2_history_restart", "main.py", "requirements.txt", ".github",
                       "research", "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md",
                       "docs/implementation/V2_RECOVERY_S3B2_RESULT.md", "docs/implementation/V2_RECOVERY_S3B3_RESULT.md")
        self.assertEqual(out.stdout.strip(), "")
        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_restore",
                       ":(exclude)tests/v2_history_diagnose")
        self.assertEqual(sorted(out.stdout.split()), sorted(SCOPE_TESTS))

    def diff_lines(self, path):
        out = self.git("diff", "-U0", START, "HEAD", "--", path)
        lines = out.stdout.splitlines()
        removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
        added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
        hunks = [l.split(" @@")[0] for l in lines if l.startswith("@@")]
        return removed, added, hunks

    def test_the_two_old_range_tests_differ_in_exactly_the_pinned_lines(self):
        self.assertEqual(self.diff_lines(SCOPE_TESTS[0]), (B17_REMOVED, B17_ADDED, B17_HUNKS))
        self.assertEqual(self.diff_lines(SCOPE_TESTS[1]), (R307_REMOVED, R307_ADDED, R307_HUNKS))
        # the test functions are neither added nor removed
        for path in SCOPE_TESTS:
            old = self.git("show", "%s:%s" % (START, path)).stdout
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                new = f.read()
            names = lambda text: [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef)]  # noqa: E731
            self.assertEqual(names(old), names(new), path)

    def test_the_r3_07_edits_lie_in_the_three_allowed_methods_only(self):
        with open(os.path.join(ROOT, SCOPE_TESTS[1]), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        spans = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                spans[node.name] = (node.lineno, node.end_lineno)
        allowed = [spans[n] for n in ("test_only_the_allowed_paths_differ",
                                      "test_no_existing_runtime_old_test_fixture_or_setting_differs",
                                      "test_the_old_range_test_differs_in_exactly_the_three_allowed_places")]
        out = self.git("diff", "-U0", START, "HEAD", "--", SCOPE_TESTS[1])
        import re
        for line in out.stdout.splitlines():
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                first = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                for ln in range(first, first + max(count, 1)):
                    self.assertTrue(any(a <= ln <= b for a, b in allowed), "line %d is outside the three methods" % ln)


if __name__ == "__main__":
    unittest.main()
