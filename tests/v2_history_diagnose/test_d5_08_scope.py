"""D5-17 scope audit of the new runtime (AST) and the change boundary against the B-5a code start ac21980, read
directly from Git (section 3.4 of the request): the three corrected old range tests are pinned line by line, every other
change is a new file at an allowed path, and everything else is blob-identical to the code start."""
import ast
import os
import re
import subprocess
import unittest

import d5_helpers as X

ROOT = X.ROOT
PKG = os.path.join(ROOT, "v2_history_diagnose")
TESTS = os.path.join(ROOT, "tests", "v2_history_diagnose")
START = "ac219801d290ebb59b720f37a086103b6e1251c9"
RESULT_DOC = "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"

ALLOWED_STDLIB = {"copy", "hashlib"}
ALLOWED_NAMES = {
    "v2_history": {"History", "validate_history", "decode_history", "KINDS"},
    "v2_history.values": {"history_dict"},
    "v2_history.common": {"is_int", "is_hex64", "is_date"},
    "v2_persistence.codec": {"CORE_SHA", "Snapshot", "canonical_json", "sha256_text", "encode_snapshot"},
    "v2_persistence.events": {"snapshot_dict"},
    "v2_persistence.recompute": {"validate_snapshot"},
    "v2_persistence.errors": {"PersistenceError"},
    "v2_core.errors": {"CoreError"},
    "v2_recovery.common": {"valid_request_id"},
}
FORBIDDEN_IMPORTS = {"os", "sys", "socket", "subprocess", "threading", "multiprocessing", "time", "random", "secrets",
                     "pathlib", "io", "shutil", "tempfile", "urllib", "http", "asyncio", "logging", "signal", "ssl",
                     "ctypes", "sqlite3", "glob", "fcntl", "msvcrt", "uuid", "webbrowser", "smtplib", "datetime", "json",
                     "re", "tests"}
# the old machinery and the helpers that must not be borrowed
NEVER_USED = {"Ctx", "SnapshotView", "validate_set", "make_records", "resolve_observations", "Chain", "ledger_of",
              "_Walk", "_Frozen", "HistoryAppendBatch", "check_append_batch", "prepare_history_day", "prepare_day",
              "AppendPlan", "make_apply_event", "MemoryStore", "LocalFileStore", "decode_snapshot", "encode_history"}
FORBIDDEN_CALLS = {"open", "input", "eval", "exec", "compile", "__import__", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "time", "monotonic", "sleep", "urandom", "getenv", "environ", "system",
                   "popen", "fsync", "replace", "rename", "unlink", "remove", "mkdir", "makedirs", "random", "seed",
                   "Thread", "Lock", "start", "run", "Popen"}
# B-5b (the adoption record and plan), CONSUME, S3-C and every kind of store, publication or notification. "diagnos"
# and "prefix" are the words of B-5a itself and are not banned.
LATER_STAGE_WORDS = ("adopt", "prefix_adoption", "prepare_prefix", "confirm_prefix", "consume", "unlock", "outbox",
                     "webhook", "discord", "snapshot.json", "notify", "sheet", "publish", "durab", "cas_", "fsync",
                     "localfile", "memorystore", "journal", "reinit", "restore", "restart", "ledger", "sessions",
                     "series", "plan")
PUBLIC = ["diagnose_history_bytes", "HistoryDiagnosis", "VALID", "PREFIX_ONLY", "NO_VALID_PREFIX", "UNREADABLE"]
FILES = ["__init__.py", "describe.py", "diagnose.py", "failure.py", "values.py"]
TEST_FILES_OK = ("test_d5_", )
TEST_HELPERS_OK = ("d5_helpers.py", "d5_sensitivity.py")
SCOPE_TESTS = ("tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py",
               "tests/v2_history_restore/test_r4_09_scope.py")
# paths that must be identical (blob by blob) to the code start
UNCHANGED_ROOTS = ("v2_core", "v2_persistence", "v2_recovery", "v2_history", "v2_history_ops", "v2_history_restart",
                   "v2_history_restore", "main.py", "requirements.txt", ".github", "research", "docs/STATUS.md",
                   "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "CLAUDE.md", "README.md")
UNCHANGED_DOCS = ("docs/implementation/V2_RECOVERY_S3B2_RESULT.md", "docs/implementation/V2_RECOVERY_S3B3_RESULT.md",
                  "docs/implementation/V2_RECOVERY_S3B4_RESULT.md")

# --- pinned against the code start ac21980: the removed lines, added lines and hunk headers of each corrected test ---
PINNED = {'tests/v2_history_ops/test_b17_scope.py': (['                  "SCHEMA_MIGRATION"}',
                                             '                                        "v2_history_restore/", '
                                             '"tests/v2_history_restore/"))',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))',
                                             '                if path != "v2_recovery/commands.py":',
                                             '                       ":(exclude)tests/v2_history_restart", '
                                             '":(exclude)tests/v2_history_restore")'],
                                            ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
                                             '        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
                                             '"v2_history/view.py", "v2_history/restore.py",',
                                             '               "tests/v2_history/test_h02_values_codec.py", '
                                             '"tests/v2_history/test_h14_scope_and_stop.py")',
                                             '                                        "v2_history_restore/", '
                                             '"tests/v2_history_restore/",',
                                             '                                        "v2_history_diagnose/", '
                                             '"tests/v2_history_diagnose/",',
                                             '                                        "v2_history_adopt/", '
                                             '"tests/v2_history_adopt/"))',
                                             '                       or path in b5b',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))',
                                             '                if path != "v2_recovery/commands.py" and path not in '
                                             'b5b:',
                                             '                             and path != '
                                             '"v2_history_diagnose/__init__.py"',
                                             '                             and path not in '
                                             '("v2_history_adopt/__init__.py", "v2_history/__init__.py")',
                                             '                       ":(exclude)tests/v2_history_restart", '
                                             '":(exclude)tests/v2_history_restore",',
                                             '                       ":(exclude)tests/v2_history_diagnose", '
                                             '":(exclude)tests/v2_history_adopt",',
                                             '                       '
                                             '":(exclude)tests/v2_history/test_h02_values_codec.py",',
                                             '                       '
                                             '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")'],
                                            ['@@ -39 +39',
                                             '@@ -182,0 +183,2',
                                             '@@ -186 +188,4',
                                             '@@ -190 +195,3',
                                             '@@ -193 +200',
                                             '@@ -202,0 +210,2',
                                             '@@ -219 +228,4']),
 'tests/v2_history_restart/test_r3_07_scope.py': (['            if path == "tests/v2_history_ops/test_b17_scope.py":',
                                                   '                                       "v2_history_restore/", '
                                                   '"tests/v2_history_restore/")) or path in (',
                                                   '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md")',
                                                   '                         {"v2_history_restart/__init__.py", '
                                                   '"v2_history_restore/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")',
                                                   '                       ":(exclude)tests/v2_history_restore")',
                                                   '        self.assertEqual(out.stdout.split(), '
                                                   '["tests/v2_history_ops/test_b17_scope.py"])',
                                                   '        # point 1 touches two separate lines of the allowed list, '
                                                   'so git shows four hunks for the three points',
                                                   '        self.assertEqual(sum(1 for l in lines if '
                                                   'l.startswith("@@")), 4)',
                                                   "            '                                        "
                                                   '"v2_history_restore/", "tests/v2_history_restore/"))\',',
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history_restart", '
                                                   '":(exclude)tests/v2_history_restore")\'])'],
                                                  ['        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
                                                   '"v2_history/view.py", "v2_history/restore.py",',
                                                   '               "v2_history_ops/chain.py", '
                                                   '"tests/v2_history/test_h02_values_codec.py",',
                                                   '               "tests/v2_history/test_h14_scope_and_stop.py")',
                                                   '            if path == "tests/v2_history_ops/test_b17_scope.py" or '
                                                   'path in b5b:',
                                                   '                                       "v2_history_restore/", '
                                                   '"tests/v2_history_restore/",',
                                                   '                                       "v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/",',
                                                   '                                       "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/")) or path in (',
                                                   '                "docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",',
                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
                                                   '                         {"v2_history_restart/__init__.py", '
                                                   '"v2_history_restore/__init__.py",',
                                                   '                          "v2_history_diagnose/__init__.py", '
                                                   '"v2_history_adopt/__init__.py",',
                                                   '                          "v2_history/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
                                                   '":(exclude)v2_history/__init__.py",',
                                                   '                       ":(exclude)v2_history/values.py", '
                                                   '":(exclude)v2_history/view.py",',
                                                   '                       ":(exclude)v2_history/restore.py", '
                                                   '":(exclude)v2_history_ops/chain.py")',
                                                   '                       ":(exclude)tests/v2_history_restore", '
                                                   '":(exclude)tests/v2_history_diagnose",',
                                                   '                       ":(exclude)tests/v2_history_adopt")',
                                                   '        self.assertEqual(out.stdout.split(), '
                                                   '["tests/v2_history/test_h02_values_codec.py",',
                                                   '                                              '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py",',
                                                   '                                              '
                                                   '"tests/v2_history_ops/test_b17_scope.py"])',
                                                   '        # four hunks for the three points of B-3; B-5b adds the '
                                                   'kind constant and its edits of the two methods',
                                                   '        self.assertEqual(sum(1 for l in lines if '
                                                   'l.startswith("@@")), 7)',
                                                   '            \'                  "SCHEMA_MIGRATION"}\',',
                                                   "            '                if path != "
                                                   '"v2_recovery/commands.py":\',',
                                                   '            \'                  "SCHEMA_MIGRATION", '
                                                   '"RECOVERY_PREFIX_ADOPTION"}\',',
                                                   '            \'        b5b = ("v2_history/__init__.py", '
                                                   '"v2_history/values.py", "v2_history/view.py", '
                                                   '"v2_history/restore.py",\',',
                                                   "            '               "
                                                   '"tests/v2_history/test_h02_values_codec.py", '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                   "            '                                        "
                                                   '"v2_history_restore/", "tests/v2_history_restore/",\',',
                                                   "            '                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
                                                   "            '                                        "
                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\',',
                                                   "            '                       or path in b5b',",
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
                                                   '            \'                if path != "v2_recovery/commands.py" '
                                                   "and path not in b5b:',",
                                                   "            '                             and path != "
                                                   '"v2_history_diagnose/__init__.py"\',',
                                                   "            '                             and path not in "
                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history_restart", '
                                                   '":(exclude)tests/v2_history_restore",\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt",\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\'])'],
                                                  ['@@ -188,0 +189,3',
                                                   '@@ -190 +193',
                                                   '@@ -194,2 +197,5',
                                                   '@@ -201 +207,3',
                                                   '@@ -207 +215,3',
                                                   '@@ -210,2 +220,5',
                                                   '@@ -218,2 +231,2',
                                                   '@@ -220,0 +234',
                                                   '@@ -222,0 +237',
                                                   '@@ -226,0 +242,3',
                                                   '@@ -229 +247,4',
                                                   '@@ -232 +253,4',
                                                   '@@ -234,0 +259,2',
                                                   '@@ -237 +263,4']),
 'tests/v2_history_restore/test_r4_09_scope.py': (['                  "SCHEMA_MIGRATION"}',
                                                   "B17_REMOVED = ['                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/"))\',',
                                                   "B17_ADDED = ['                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/",\',',
                                                   ' \'                                        "v2_history_restore/", '
                                                   '"tests/v2_history_restore/"))\',',
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))\',',
                                                   ' \'                       ":(exclude)tests/v2_history_restart", '
                                                   '":(exclude)tests/v2_history_restore")\']',
                                                   "B17_HUNKS = ['@@ -185 +185,2', '@@ -188 +189,2', '@@ -199,0 +202', "
                                                   "'@@ -216 +219']",
                                                   "R307_REMOVED = ['            allowed = "
                                                   'path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/")) or path in (\',',
                                                   "R307_ADDED = ['            allowed = "
                                                   'path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/",\',',
                                                   ' \'                                       "v2_history_restore/", '
                                                   '"tests/v2_history_restore/")) or path in (\',',
                                                   " '                "
                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", \'',
                                                   ' \'"docs/implementation/V2_RECOVERY_S3B4_RESULT.md")\',',
                                                   ' \'                         {"v2_history_restart/__init__.py", '
                                                   '"v2_history_restore/__init__.py"})\',',
                                                   ' \'                       ":(exclude)tests/v2_history_restore")\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_restore/", "tests/v2_history_restore/"))\\\',\',',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md"))\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history_restart", \'',
                                                   ' \'":(exclude)tests/v2_history_restore")\\\'])\']',
                                                   "R307_HUNKS = ['@@ -193,2 +193,3',",
                                                   " '@@ -199 +200,2',",
                                                   " '@@ -207 +209,2',",
                                                   " '@@ -225 +228,2',",
                                                   " '@@ -227 +231,2',",
                                                   " '@@ -228,0 +234',",
                                                   " '@@ -231 +237']",
                                                   '                    if v in KIND_CONSTANTS:',
                                                   '        self.assertEqual(modified, '
                                                   'sorted(SCOPE_TESTS))                            # the only files '
                                                   'that are modified',
                                                   '            if path in SCOPE_TESTS:',
                                                   '            self.assertTrue(allowed_path(path), "unexpected '
                                                   'change: %s %s" % (status, path))',
                                                   '        self.assertEqual({p for p in paths if '
                                                   'p.endswith("__init__.py")}, {"v2_history_restore/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md")',
                                                   '        out = self.git("diff", "--name-only", START, "HEAD", "--", '
                                                   '"tests", ":(exclude)tests/v2_history_restore")',
                                                   '        self.assertEqual(sorted(out.stdout.split()), '
                                                   'sorted(SCOPE_TESTS))'],
                                                  ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
                                                   'B17_REMOVED = [\'                  "SCHEMA_MIGRATION"}\',',
                                                   ' \'                                        "v2_history_restart/", '
                                                   '"tests/v2_history_restart/"))\',',
                                                   ' \'                if path != "v2_recovery/commands.py":\',',
                                                   'B17_ADDED = [\'                  "SCHEMA_MIGRATION", '
                                                   '"RECOVERY_PREFIX_ADOPTION"}\',',
                                                   ' \'        b5b = ("v2_history/__init__.py", '
                                                   '"v2_history/values.py", "v2_history/view.py", '
                                                   '"v2_history/restore.py",\',',
                                                   ' \'               "tests/v2_history/test_h02_values_codec.py", '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                   ' \'                                        "v2_history_restart/", '
                                                   '"tests/v2_history_restart/",\',',
                                                   ' \'                                        "v2_history_restore/", '
                                                   '"tests/v2_history_restore/",\',',
                                                   ' \'                                        "v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/",\',',
                                                   ' \'                                        "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/"))\',',
                                                   " '                       or path in b5b',",
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
                                                   ' \'                if path != "v2_recovery/commands.py" and path '
                                                   "not in b5b:',",
                                                   " '                             and path != "
                                                   '"v2_history_diagnose/__init__.py"\',',
                                                   " '                             and path not in "
                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                   ' \'                       ":(exclude)tests/v2_history_restart", '
                                                   '":(exclude)tests/v2_history_restore",\',',
                                                   ' \'                       ":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt",\',',
                                                   " '                       "
                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
                                                   " '                       "
                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\']',
                                                   "B17_HUNKS = ['@@ -39 +39',",
                                                   " '@@ -182,0 +183,2',",
                                                   " '@@ -185 +187,5',",
                                                   " '@@ -188 +194,4',",
                                                   " '@@ -191 +200',",
                                                   " '@@ -199,0 +209,3',",
                                                   " '@@ -216 +228,4']",
                                                   "R307_REMOVED = ['            if path == "
                                                   '"tests/v2_history_ops/test_b17_scope.py":\',',
                                                   ' \'            allowed = path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/")) or path in (\',',
                                                   " '                       "
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")\',',
                                                   " '        self.assertEqual(out.stdout.split(), "
                                                   '["tests/v2_history_ops/test_b17_scope.py"])\',',
                                                   " '        # point 1 touches two separate lines of the allowed "
                                                   "list, so git shows four hunks for the three points',",
                                                   " '        self.assertEqual(sum(1 for l in lines if "
                                                   'l.startswith("@@")), 4)\',',
                                                   'R307_ADDED = [\'        b5b = ("v2_history/__init__.py", '
                                                   '"v2_history/values.py", "v2_history/view.py", '
                                                   '"v2_history/restore.py",\',',
                                                   ' \'               "v2_history_ops/chain.py", '
                                                   '"tests/v2_history/test_h02_values_codec.py",\',',
                                                   " '               "
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                   ' \'            if path == "tests/v2_history_ops/test_b17_scope.py" '
                                                   "or path in b5b:',",
                                                   ' \'            allowed = path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/",\',',
                                                   ' \'                                       "v2_history_restore/", '
                                                   '"tests/v2_history_restore/",\',',
                                                   ' \'                                       "v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/",\',',
                                                   ' \'                                       "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/")) or path in (\',',
                                                   " '                "
                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\',',
                                                   " '                "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\',',
                                                   ' \'                         {"v2_history_restart/__init__.py", '
                                                   '"v2_history_restore/__init__.py",\',',
                                                   ' \'                          "v2_history_diagnose/__init__.py", '
                                                   '"v2_history_adopt/__init__.py",\',',
                                                   ' \'                          "v2_history/__init__.py"})\',',
                                                   " '                       "
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
                                                   '":(exclude)v2_history/__init__.py",\',',
                                                   ' \'                       ":(exclude)v2_history/values.py", '
                                                   '":(exclude)v2_history/view.py",\',',
                                                   ' \'                       ":(exclude)v2_history/restore.py", '
                                                   '":(exclude)v2_history_ops/chain.py")\',',
                                                   ' \'                       ":(exclude)tests/v2_history_restore", '
                                                   '":(exclude)tests/v2_history_diagnose",\',',
                                                   ' \'                       ":(exclude)tests/v2_history_adopt")\',',
                                                   " '        self.assertEqual(out.stdout.split(), "
                                                   '["tests/v2_history/test_h02_values_codec.py",\',',
                                                   " '                                              "
                                                   '"tests/v2_history/test_h14_scope_and_stop.py",\',',
                                                   " '                                              "
                                                   '"tests/v2_history_ops/test_b17_scope.py"])\',',
                                                   " '        # four hunks for the three points of B-3; B-5b adds the "
                                                   "kind constant and its edits of the two methods',",
                                                   " '        self.assertEqual(sum(1 for l in lines if "
                                                   'l.startswith("@@")), 7)\',',
                                                   ' \'            \\\'                  "SCHEMA_MIGRATION"}\\\',\',',
                                                   " '            \\'                if path != "
                                                   '"v2_recovery/commands.py":\\\',\',',
                                                   ' \'            \\\'                  "SCHEMA_MIGRATION", '
                                                   '"RECOVERY_PREFIX_ADOPTION"}\\\',\',',
                                                   ' \'            \\\'        b5b = ("v2_history/__init__.py", '
                                                   '"v2_history/values.py", "v2_history/view.py", \'',
                                                   ' \'"v2_history/restore.py",\\\',\',',
                                                   " '            \\'               "
                                                   '"tests/v2_history/test_h02_values_codec.py", \'',
                                                   ' \'"tests/v2_history/test_h14_scope_and_stop.py")\\\',\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_restore/", "tests/v2_history_restore/",\\\',\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\\\',\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\\\',\',',
                                                   ' "            \'                       or path in b5b\',",',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B4_RESULT.md",\\\',\',',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\',\',',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\',\',',
                                                   " '            \\'                if path != "
                                                   '"v2_recovery/commands.py" and path not in b5b:\\\',\',',
                                                   " '            \\'                             and path != "
                                                   '"v2_history_diagnose/__init__.py"\\\',\',',
                                                   " '            \\'                             and path not in "
                                                   '("v2_history_adopt/__init__.py", \'',
                                                   ' \'"v2_history/__init__.py")\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history_restart", '
                                                   '":(exclude)tests/v2_history_restore",\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt",\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\\\'])\']',
                                                   "R307_HUNKS = ['@@ -188,0 +189,3',",
                                                   " '@@ -190 +193',",
                                                   " '@@ -193,2 +196,6',",
                                                   " '@@ -199 +206,4',",
                                                   " '@@ -205 +215,3',",
                                                   " '@@ -207,2 +219,6',",
                                                   " '@@ -215,2 +231,2',",
                                                   " '@@ -217,0 +234',",
                                                   " '@@ -219,0 +237',",
                                                   " '@@ -223,0 +242,3',",
                                                   " '@@ -225 +246,5',",
                                                   " '@@ -227 +252,5',",
                                                   " '@@ -228,0 +258,3',",
                                                   " '@@ -231 +263,4']",
                                                   '                    if v in KIND_CONSTANTS or v == '
                                                   '"restore_before_adoption":      # the B-5b refusal code',
                                                   '        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
                                                   '"v2_history/view.py", "v2_history/restore.py",',
                                                   '               "v2_history_ops/chain.py", '
                                                   '"tests/v2_history/test_h02_values_codec.py",',
                                                   '               "tests/v2_history/test_h14_scope_and_stop.py")',
                                                   '        self.assertEqual(modified, sorted(SCOPE_TESTS + '
                                                   'b5b))                      # the only files that are modified',
                                                   '            if path in SCOPE_TESTS or path in b5b:',
                                                   '            new_b5a = path.startswith(("v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/",',
                                                   '                                       "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/")) or path in (',
                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
                                                   '            self.assertTrue(allowed_path(path) or new_b5a, '
                                                   '"unexpected change: %s %s" % (status, path))',
                                                   '        self.assertEqual({p for p in paths if '
                                                   'p.endswith("__init__.py")},',
                                                   '                         {"v2_history_restore/__init__.py", '
                                                   '"v2_history_diagnose/__init__.py",',
                                                   '                          "v2_history_adopt/__init__.py", '
                                                   '"v2_history/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md",',
                                                   '                       ":(exclude)v2_history/__init__.py", '
                                                   '":(exclude)v2_history/values.py",',
                                                   '                       ":(exclude)v2_history/view.py", '
                                                   '":(exclude)v2_history/restore.py",',
                                                   '                       ":(exclude)v2_history_ops/chain.py")',
                                                   '        out = self.git("diff", "--name-only", START, "HEAD", "--", '
                                                   '"tests", ":(exclude)tests/v2_history_restore",',
                                                   '                       ":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt")',
                                                   '        self.assertEqual(sorted(out.stdout.split()), '
                                                   'sorted(SCOPE_TESTS + ("tests/v2_history/test_h02_values_codec.py",',
                                                   '                                                                           '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")))'],
                                                  ['@@ -38 +38',
                                                   '@@ -79 +79,2',
                                                   '@@ -80,0 +82',
                                                   '@@ -82,2 +84,8',
                                                   '@@ -85 +93,4',
                                                   '@@ -87,3 +98,15',
                                                   '@@ -91,0 +115',
                                                   '@@ -92,0 +117,3',
                                                   '@@ -96,4 +123,10',
                                                   '@@ -101 +134,6',
                                                   '@@ -103 +141,14',
                                                   '@@ -105 +156,4',
                                                   '@@ -107 +161,4',
                                                   '@@ -109,9 +166,21',
                                                   '@@ -195 +264',
                                                   '@@ -346 +415,4',
                                                   '@@ -348 +420',
                                                   '@@ -350 +422,4',
                                                   '@@ -354 +429,3',
                                                   '@@ -378 +455,4',
                                                   '@@ -380,2 +460,4'])}


def allowed_new_path(path):
    """The paths B-5a may add. The scope tests are the only existing files it may modify (see modified_ok)."""
    if path == RESULT_DOC:
        return True
    if path == "v2_history_diagnose/__init__.py":
        return True
    if path.endswith("__init__.py"):
        return False
    parts = path.split("/")
    return ((parts[0] == "v2_history_diagnose" and len(parts) == 2)
            or (parts[:2] == ["tests", "v2_history_diagnose"] and len(parts) == 3))


def modified_ok(path):
    return path in SCOPE_TESTS


def sources():
    for fname in sorted(os.listdir(PKG)):
        if fname.endswith(".py"):
            with open(os.path.join(PKG, fname), encoding="utf-8") as f:
                yield fname, ast.parse(f.read())


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
                        self.assertIn(a.name, ALLOWED_NAMES[mod], "%s imports %s.%s" % (fname, mod, a.name))
                        self.assertFalse(a.name.startswith("_"), "%s imports a private name" % fname)
                        self.assertNotIn(a.name, NEVER_USED, fname)
                    self.assertNotIn(mod.split(".")[0], FORBIDDEN_IMPORTS, fname)
                    self.assertNotRegex(mod, r"^v2_persistence\.(local|store|plan|runner)", fname)
        self.assertGreater(count, 25)

    def test_no_name_of_the_old_machinery_appears_anywhere(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assertNotIn(node.id, NEVER_USED, fname)
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, NEVER_USED, fname)

    def test_no_private_name_of_an_existing_package_is_used(self):
        """A leading underscore is used only on self / cls and on the package's own module-level names."""
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                    base = node.value
                    self.assertTrue(isinstance(base, ast.Name) and base.id in ("self", "cls", "other", "obj"),
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
                    self.assertNotIn(node.id, FORBIDDEN_IMPORTS - {"time", "tests", "json", "re"}, fname)

    def test_hashlib_is_used_in_exactly_one_place_for_the_sha256_of_the_raw_bytes(self):
        uses = []
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "hashlib":
                    uses.append((fname, node.lineno))
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "hashlib":
                    self.assertEqual(node.attr, "sha256", fname)
        # one import statement and one use
        self.assertEqual(sorted({f for f, _l in uses}), ["diagnose.py"])
        calls = []
        for fname, tree in sources():
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "hashlib"):
                    calls.append((fname, node))
        self.assertEqual(len(calls), 1)
        fname, call = calls[0]
        self.assertEqual(len(call.args), 1)
        self.assertIsInstance(call.args[0], ast.Name)
        self.assertEqual(call.args[0].id, "data")
        self.assertEqual(len(call.keywords), 0)

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
                elif isinstance(node, ast.arg):
                    values.append(node.arg)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    values.append(node.value)
                for v in values:
                    checked += 1
                    if v in ("GENESIS", "APPLY", "SCHEMA_MIGRATION", "RECOVERY_RESTORE", "RESTART_UNKNOWN", "KINDS"):
                        continue                                    # record kind names are data
                    for word in LATER_STAGE_WORDS:
                        self.assertNotIn(word, v.lower(), "%s: %s" % (fname, v))
        self.assertGreater(checked, 300)

    def test_no_threshold_ratio_or_market_number_is_written(self):
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                    self.assertIsInstance(node.value, int, fname)
                    # indexes, "- 1", the 96-character identifier limit and the 12-character hash prefix of a repr
                    self.assertIn(node.value, (0, 1, 2, 12, 96), "%s holds the number %r" % (fname, node.value))

    def test_the_public_names_are_exactly_the_documented_ones(self):
        self.assertEqual(sorted(X.G.__all__), sorted(PUBLIC))
        for name in X.G.__all__:
            self.assertTrue(hasattr(X.G, name), name)
        self.assertEqual((X.G.VALID, X.G.PREFIX_ONLY, X.G.NO_VALID_PREFIX, X.G.UNREADABLE),
                         ("VALID", "PREFIX_ONLY", "NO_VALID_PREFIX", "UNREADABLE"))
        import v2_history
        import v2_history_ops
        import v2_history_restart
        import v2_history_restore
        import v2_persistence
        for module in (v2_history, v2_history_ops, v2_history_restart, v2_history_restore, v2_persistence):
            exported = getattr(module, "__all__", [])
            self.assertFalse(any("diagnos" in n.lower() for n in exported), module.__name__)

    def test_the_package_files_and_the_absence_of_dependency_files(self):
        self.assertEqual(sorted(f for f in os.listdir(PKG) if not f.startswith("__pycache__")), FILES)
        for name in ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"):
            self.assertFalse(os.path.exists(os.path.join(PKG, name)))
        for fname, tree in sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(("tests", "ho_helpers", "h_helpers", "d5_helpers")), fname)

    def test_no_adoption_or_store_name_is_exported_or_defined(self):
        defined = {n.name for _f, tree in sources() for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for banned in ("prepare_prefix_adoption", "confirm_prefix_adoption", "RECOVERY_PREFIX_ADOPTION"):
            self.assertNotIn(banned, defined)
        import v2_history
        self.assertEqual(v2_history.KINDS[-1], "RECOVERY_PREFIX_ADOPTION")              # the kind is added by B-5b

    def test_the_new_tests_use_unique_names_and_no_init_file(self):
        self.assertFalse(os.path.exists(os.path.join(TESTS, "__init__.py")))
        names = sorted(f for f in os.listdir(TESTS) if f.endswith(".py"))
        for name in names:
            self.assertTrue(name.startswith(TEST_FILES_OK) or name in TEST_HELPERS_OK, name)
        taken = {}
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "tests")):
            for f in files:
                if f.endswith(".py") and os.path.abspath(dirpath) != os.path.abspath(TESTS):
                    taken.setdefault(f, dirpath)
        for name in names:
            self.assertNotIn(name, taken, "%s already exists in %s" % (name, taken.get(name)))


class PathJudgement(unittest.TestCase):
    def test_the_judgement_accepts_only_the_exact_new_paths(self):
        yes = ["v2_history_diagnose/__init__.py", "v2_history_diagnose/diagnose.py",
               "tests/v2_history_diagnose/test_d5_01_args_stages.py", "tests/v2_history_diagnose/d5_helpers.py",
               "tests/v2_history_diagnose/d5_sensitivity.py", RESULT_DOC]
        no = ["tests/v2_history_diagnose/__init__.py", "v2_history_diagnose2/x.py", "v2_history_diagnoses/x.py",
              "tests/v2_history_diagnose_x/y.py", "v2_history_diagnose/sub/x.py", "v2_history_diagnose/sub/__init__.py",
              "docs/implementation/V2_RECOVERY_S3B5_RESULT.md.bak", "docs/implementation/V2_RECOVERY_S3B4_RESULT.md",
              "docs/implementation/V2_RECOVERY_S3B6_RESULT.md", "v2_history/values.py", "v2_history/__init__.py",
              "v2_history_ops/chain.py", "v2_history_restore/points.py", "v2_history_restart/build.py",
              "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py",
              "tests/v2_history_restore/r4_helpers.py", "tests/v2_history_ops/ho_helpers.py", "docs/STATUS.md",
              "main.py", ".github/workflows/x.yml", "research/x.py", "requirements.txt", "v2_core/state.py",
              "v2_persistence/codec.py", "v2_recovery/common.py", "v2_history_restore/consume.py"]
        for p in yes:
            self.assertTrue(allowed_new_path(p), p)
        for p in no:
            self.assertFalse(allowed_new_path(p), p)
        for p in SCOPE_TESTS:
            self.assertTrue(modified_ok(p))
        for p in ("tests/v2_history/test_h14_scope_and_stop.py", "tests/v2_history_restore/test_r4_01_point_ops.py",
                  "tests/v2_history_ops/test_b02_api1_regression.py", "tests/v2_history_restore/r4_helpers.py"):
            self.assertFalse(modified_ok(p), p)


class FilesChanged(unittest.TestCase):
    """Compared with the code start by git (committed state)."""

    def git(self, *args):
        return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True, timeout=120)

    def setUp(self):
        probe = self.git("cat-file", "-e", START + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")

    def changed(self):
        out = self.git("diff", "--name-status", START, "HEAD")
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)                      # no rename or copy: a plain A or M
        return rows

    def test_modified_files_are_exactly_the_three_scope_tests_and_every_other_change_is_a_new_allowed_file(self):
        rows = self.changed()
        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
               "v2_history_ops/chain.py", "v2_history_restore/points.py",
               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")
        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(SCOPE_TESTS + b5b))
        for status, path in rows:
            if status == "M":
                continue
            self.assertEqual(status, "A", "%s %s" % (status, path))                 # no deletion, no mode change
            new_b5b = path.startswith(("v2_history_adopt/", "tests/v2_history_adopt/")) or \
                path == "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"
            self.assertTrue(allowed_new_path(path) or new_b5b, "unexpected change: %s %s" % (status, path))
        paths = {p for _s, p in rows}
        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
                         {"v2_history_diagnose/__init__.py", "v2_history_adopt/__init__.py", "v2_history/__init__.py"})
        self.assertIn("v2_history_diagnose/diagnose.py", paths)
        self.assertEqual({p for p in paths if p.startswith("v2_history_diagnose/")},
                         {"v2_history_diagnose/" + f for f in FILES})

    def test_everything_else_is_identical_to_the_code_start(self):
        b5b = ("v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py", "v2_history/restore.py",
               "v2_history_ops/chain.py", "v2_history_restore/points.py",
               "tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py")
        out = self.git("diff", "--name-only", START, "HEAD", "--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS,
                       *[":(exclude)%s" % p for p in b5b])
        self.assertEqual(out.stdout.strip(), "")
        out = self.git("diff", "--name-only", START, "HEAD", "--", "tests", ":(exclude)tests/v2_history_diagnose",
                       ":(exclude)tests/v2_history_adopt", *[":(exclude)%s" % p for p in SCOPE_TESTS + b5b])
        self.assertEqual(out.stdout.strip(), "")
        out = self.git("diff", "--name-only", START, "HEAD", "--", "docs", ":(exclude)%s" % RESULT_DOC,
                       ":(exclude)docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")
        self.assertEqual(out.stdout.strip(), "")

    def test_the_b4_runtime_tests_and_result_are_blob_identical_to_the_code_start(self):
        listing = self.git("ls-tree", "-r", START, "--", "v2_history_restore", "tests/v2_history_restore",
                           "docs/implementation/V2_RECOVERY_S3B4_RESULT.md")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        rows = [line.split() for line in listing.stdout.splitlines()]
        self.assertGreater(len(rows), 20)
        corrected = "tests/v2_history_restore/test_r4_09_scope.py"
        seen_corrected = False
        for _mode, kind, blob, path in rows:
            self.assertEqual(kind, "blob")
            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
            if path in (corrected, "v2_history_restore/points.py"):            # points.py: changed by B-5b
                seen_corrected = seen_corrected or path == corrected
                self.assertNotEqual(here.stdout.strip(), blob, path)
                continue
            self.assertEqual(here.stdout.strip(), blob, path)
        self.assertTrue(seen_corrected)

    def test_the_older_runtimes_and_their_results_are_blob_identical_to_the_code_start(self):
        listing = self.git("ls-tree", "-r", START, "--", "v2_core", "v2_persistence", "v2_recovery", "v2_history",
                           "v2_history_ops", "v2_history_restart", "tests/v2_core", "tests/v2_persistence",
                           "tests/v2_persistence_local", "tests/v2_recovery", "tests/v2_history",
                           "tests/v2_history_ops", "tests/v2_history_restart",
                           "docs/implementation/V2_RECOVERY_S3B2_RESULT.md",
                           "docs/implementation/V2_RECOVERY_S3B3_RESULT.md")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        rows = [line.split() for line in listing.stdout.splitlines()]
        self.assertGreater(len(rows), 150)
        corrected = set(SCOPE_TESTS) | {"v2_history/__init__.py", "v2_history/values.py", "v2_history/view.py",
                                        "v2_history/restore.py", "v2_history_ops/chain.py",
                                        "tests/v2_history/test_h02_values_codec.py",
                                        "tests/v2_history/test_h14_scope_and_stop.py"}
        for _mode, kind, blob, path in rows:
            if path in corrected:
                continue
            here = subprocess.run(("git", "-C", ROOT, "hash-object", path), capture_output=True, text=True, timeout=60)
            self.assertEqual(here.stdout.strip(), blob, path)

    def diff_lines(self, path):
        out = self.git("diff", "-U0", START, "HEAD", "--", path)
        lines = out.stdout.splitlines()
        removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
        added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
        hunks = [l.split(" @@")[0] for l in lines if l.startswith("@@")]
        return removed, added, hunks

    def test_the_three_old_range_tests_differ_in_exactly_the_pinned_lines(self):
        for path in SCOPE_TESTS:
            removed, added, hunks = self.diff_lines(path)
            want_removed, want_added, want_hunks = PINNED[path]
            self.assertEqual(removed, want_removed, path)
            self.assertEqual(added, want_added, path)
            self.assertEqual(hunks, want_hunks, path)

    def test_no_assert_is_removed_no_test_is_skipped_and_the_test_functions_are_the_same(self):
        for path in SCOPE_TESTS:
            old = self.git("show", "%s:%s" % (START, path)).stdout
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                new = f.read()
            names = lambda text: [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef)]  # noqa: E731
            self.assertEqual(names(old), names(new), path)
            # counted as calls (B-5b): the pinned text of the r4_09 lists quotes assert calls of the older tests
            asserts = lambda text: sum(1 for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call)  # noqa: E731
                                       and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))
            self.assertEqual(asserts(new), asserts(old), path)
            for word in ("skip", "expectedFailure", "@unittest", "pass\n", "return\n"):
                self.assertEqual(new.count(word), old.count(word), "%s: %r" % (path, word))
            self.assertEqual(new.count("START"), old.count("START"), path)
            self.assertEqual(new.count('"HEAD"'), old.count('"HEAD"'), path)
            for line in old.splitlines():
                if line.startswith("START = "):
                    self.assertIn(line, new.splitlines(), path)             # the code start of the old range is kept

    def lines_changed_in_new(self, path):
        out = self.git("diff", "-U0", START, "HEAD", "--", path)
        result = []
        for line in out.stdout.splitlines():
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                first = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                result.extend(range(first, first + count))
        return result

    def spans(self, path):
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        funcs, assigns = {}, {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                funcs[node.name] = (node.lineno, node.end_lineno)
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                assigns[node.targets[0].id] = (node.lineno, node.end_lineno)
        return funcs, assigns

    def assert_inside(self, path, spans):
        for ln in self.lines_changed_in_new(path):
            self.assertTrue(any(a <= ln <= b for a, b in spans), "%s: line %d is outside the allowed places" % (path, ln))

    def test_each_edit_lies_in_the_allowed_places(self):
        funcs, assigns = self.spans(SCOPE_TESTS[0])
        self.assert_inside(SCOPE_TESTS[0], [funcs["test_only_the_allowed_paths_differ"],
                                             funcs["test_existing_tests_and_fixtures_are_untouched"],
                                             assigns["KIND_CONSTANTS"]])
        funcs, _ = self.spans(SCOPE_TESTS[1])
        self.assert_inside(SCOPE_TESTS[1], [funcs[n] for n in (
            "test_only_the_allowed_paths_differ", "test_no_existing_runtime_old_test_fixture_or_setting_differs",
            "test_the_old_range_test_differs_in_exactly_the_three_allowed_places")])
        funcs, assigns = self.spans(SCOPE_TESTS[2])
        self.assert_inside(SCOPE_TESTS[2], [assigns[n] for n in (
            "B17_REMOVED", "B17_ADDED", "B17_HUNKS", "R307_REMOVED", "R307_ADDED", "R307_HUNKS", "KIND_CONSTANTS")] + [
            funcs["test_only_the_allowed_paths_differ"],
            funcs["test_no_existing_runtime_old_test_fixture_or_setting_differs"],
            funcs["test_nothing_of_the_later_stages"]])

    def test_the_module_functions_of_the_b4_judgement_are_untouched(self):
        old = self.git("show", "%s:%s" % (START, SCOPE_TESTS[2])).stdout
        with open(os.path.join(ROOT, SCOPE_TESTS[2]), encoding="utf-8") as f:
            new = f.read()
        def source_of(text, name):
            tree = ast.parse(text)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    return ast.get_source_segment(text, node)
            return None
        for name in ("allowed_path", "PathJudgement", "sources"):
            self.assertIsNotNone(source_of(old, name), name)
            self.assertEqual(source_of(old, name), source_of(new, name), name)


if __name__ == "__main__":
    unittest.main()
