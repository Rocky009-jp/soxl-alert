"""A5-18 the change boundary of B-5b against the code start c8ba08f (B-5a final), read directly from Git: twelve existing
files change (six runtime files and six tests), each in exactly the pinned lines and only in the allowed places; every
other change is a new file at an allowed path; everything else is blob-identical to the code start (section 7.4 of the
request)."""
import ast
import io
import os
import re
import subprocess
import unittest

import a5_helpers as Z

ROOT = Z.ROOT
START = "c8ba08f15ea28248a9fe7924f32ce136fc16d5e6"
END = "b626c98af5f01bc94e7b41d86aadde9663695eb9"   # the accepted final commit of this range (frozen when the next stage began)
RESULT_DOC = "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"

RUNTIME_M = ("v2_history/__init__.py", "v2_history/restore.py", "v2_history/values.py", "v2_history/view.py",
             "v2_history_ops/chain.py", "v2_history_restore/points.py")
TEST_M = ("tests/v2_history/test_h02_values_codec.py", "tests/v2_history/test_h14_scope_and_stop.py",
          "tests/v2_history_ops/test_b17_scope.py", "tests/v2_history_restart/test_r3_07_scope.py",
          "tests/v2_history_restore/test_r4_09_scope.py", "tests/v2_history_diagnose/test_d5_08_scope.py")
ALL_M = RUNTIME_M + TEST_M
# --- PINNED BEGIN (against the code start c8ba08f: the removed lines, added lines and hunk headers of each file) ---
PINNED_RUNTIME = {'v2_history/__init__.py': (['from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, KINDS, RECOVERY_RESTORE, '
                             'RESTART_UNKNOWN,',
                             '                     SCHEMA_MIGRATION, SCHEMA_VERSION_V2, History, decode_history, '
                             'encode_history)',
                             '           "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", '
                             '"SCHEMA_MIGRATION", "READY",',
                             '           "CONFIRMED_IN_MEMORY"]'],
                            ['from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, KINDS, '
                             'RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,',
                             '                     RESTART_UNKNOWN, SCHEMA_MIGRATION, SCHEMA_VERSION_V2, History, '
                             'decode_history, encode_history)',
                             '           "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", '
                             '"SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION",',
                             '           "READY", "CONFIRMED_IN_MEMORY"]'],
                            ['@@ -13,2 +13,2', '@@ -19,2 +19,2']),
 'v2_history/restore.py': (['CONSUME and RECOVERY_PREFIX_ADOPTION are refused (restore_op_unsupported / '
                            'unsupported_event).',
                            'from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, '
                            'RESTART_UNKNOWN, SCHEMA_MIGRATION'],
                           ['CONSUME is refused (restore_op_unsupported / unsupported_event). '
                            'RECOVERY_PREFIX_ADOPTION cannot be restored',
                            'before (restore_before_adoption).',
                            'from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, '
                            'RECOVERY_RESTORE,',
                            '                     RESTART_UNKNOWN, SCHEMA_MIGRATION)',
                            '    adoptions = [s for s in chain if events[s]["kind"] == RECOVERY_PREFIX_ADOPTION]',
                            '    if adoptions and point < adoptions[-1]:',
                            '        raise _bad("restore_before_adoption")'],
                           ['@@ -5 +5,2', '@@ -11 +12,2', '@@ -100,0 +103,3']),
 'v2_history/values.py': (['KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, '
                           'SCHEMA_MIGRATION)',
                           '# Designed for B-5 and refused here (unsupported_event).',
                           '    SCHEMA_MIGRATION: MIGRATION_KEYS}'],
                          ['KINDS = (GENESIS, APPLY, ACK, DECLARE_MISSING, RESTART_UNKNOWN, RECOVERY_RESTORE, '
                           'SCHEMA_MIGRATION,',
                           '         RECOVERY_PREFIX_ADOPTION)',
                           'ADOPTION_KEYS = frozenset([',
                           '    "kind", "seq", "parent_seq", "parent_hash", "evidence", "request_id", '
                           '"request_hash", "request_basis",',
                           '    "reason_code", "requested_at", "state_after", "event_hash"])',
                           '    SCHEMA_MIGRATION: MIGRATION_KEYS, RECOVERY_PREFIX_ADOPTION: ADOPTION_KEYS}'],
                          ['@@ -24,2 +23,0', '@@ -26,0 +25,2', '@@ -43,0 +44,3', '@@ -47 +50']),
 'v2_history/view.py': (['from .values import ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, '
                         'RESTART_UNKNOWN, SCHEMA_MIGRATION'],
                        ['from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_PREFIX_ADOPTION, '
                         'RECOVERY_RESTORE,',
                         '                     RESTART_UNKNOWN, SCHEMA_MIGRATION)',
                         'REASON_ADOPT = "ADOPT_VERIFIED_PREFIX"',
                         'EVIDENCE_KEYS = frozenset(["raw_sha256", "raw_size", "claimed_schema_version", '
                         '"claimed_head_seq",',
                         '                           "claimed_head_hash", "discarded_from_seq"])',
                         'ADOPTION_BASIS_KEYS = frozenset(["request_id", "evidence", "reason_code", "requested_at"])',
                         '        if kind == RECOVERY_PREFIX_ADOPTION:',
                         '            self.adoption_record(rec, parent_state)',
                         '            return',
                         '    def adoption_record(self, rec, parent_state):',
                         '        """S3-B-5b: a control record that keeps the state and names the raw bytes whose '
                         'verified prefix was adopted."""',
                         '        self.claim_request(rec["request_id"])',
                         '        if not same(rec["state_after"], parent_state):',
                         '            raise _bad("state_after")',
                         '        ev = rec["evidence"]',
                         '        if (not isinstance(ev, dict) or set(ev) != EVIDENCE_KEYS or not '
                         'is_hex64(ev["raw_sha256"])',
                         '                or not is_int(ev["raw_size"]) or ev["raw_size"] < 1',
                         '                or not is_int(ev["claimed_schema_version"]) or '
                         'ev["claimed_schema_version"] != 2',
                         '                or not (ev["claimed_head_seq"] is None or is_int(ev["claimed_head_seq"]))',
                         '                or not (ev["claimed_head_hash"] is None or '
                         'is_hex64(ev["claimed_head_hash"]))',
                         '                or not is_int(ev["discarded_from_seq"]) or ev["discarded_from_seq"] != '
                         'rec["seq"]):',
                         '            raise _bad("adoption_evidence")',
                         '        basis = rec["request_basis"]',
                         '        if not isinstance(basis, dict) or set(basis) != ADOPTION_BASIS_KEYS:',
                         '            raise _bad("request_basis")',
                         '        if basis["request_id"] != rec["request_id"] or not same(basis["evidence"], ev):',
                         '            raise _bad("request_basis")',
                         '        if not is_requested_text(basis["requested_at"]) or basis["requested_at"] != '
                         'rec["requested_at"]:',
                         '            raise _bad("requested_at")',
                         '        if basis["reason_code"] != REASON_ADOPT or rec["reason_code"] != REASON_ADOPT:',
                         '            raise _bad("reason_code")',
                         '        if not is_hex64(rec["request_hash"]) or rec["request_hash"] != '
                         'basis_request_hash(basis):',
                         '            raise _bad("request_hash")',
                         ''],
                        ['@@ -20 +20,2', '@@ -26,0 +28', '@@ -31,0 +34,3', '@@ -324,0 +330,3', '@@ -450,0 +459,25']),
 'v2_history_ops/chain.py': (['from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, '
                              'RECOVERY_RESTORE, RESTART_UNKNOWN,',
                              '                               SCHEMA_MIGRATION)',
                              '                  RECOVERY_RESTORE: RECOVERY_RESTORE, SCHEMA_MIGRATION: '
                              'SCHEMA_MIGRATION}'],
                             ['from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, '
                              'RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE,',
                              '                               RESTART_UNKNOWN, SCHEMA_MIGRATION)',
                              '                  RECOVERY_RESTORE: RECOVERY_RESTORE, SCHEMA_MIGRATION: '
                              'SCHEMA_MIGRATION,',
                              '                  RECOVERY_PREFIX_ADOPTION: RECOVERY_PREFIX_ADOPTION}'],
                             ['@@ -10,2 +10,2', '@@ -22 +22,2']),
 'v2_history_restore/points.py': (['from v2_history.values import ACK, APPLY, DECLARE_MISSING, RECOVERY_RESTORE, '
                                   'RESTART_UNKNOWN'],
                                  ['from v2_history.values import ACK, APPLY, DECLARE_MISSING, '
                                   'RECOVERY_PREFIX_ADOPTION, RECOVERY_RESTORE, RESTART_UNKNOWN',
                                   '    taken = [s for s in effective if events[s]["kind"] == '
                                   'RECOVERY_PREFIX_ADOPTION]',
                                   '    if taken and seq < taken[-1]:',
                                   '        raise restore_invalid("restore_point", "restore_before_adoption")'],
                                  ['@@ -3 +3', '@@ -28,0 +29,3'])}
PINNED_TESTS = {'tests/v2_history/test_h02_values_codec.py': (['        for kind in ("BOGUS", "RECOVERY_PREFIX_ADOPTION", None, '
                                                '7):'],
                                               ['        for kind in ("BOGUS", "CONSUME", None, 7):'],
                                               ['@@ -143 +143']),
 'tests/v2_history/test_h14_scope_and_stop.py': (['            "DECLARE_MISSING", "RESTART_UNKNOWN", '
                                                  '"RECOVERY_RESTORE", "SCHEMA_MIGRATION", "READY",',
                                                  '            "CONFIRMED_IN_MEMORY"]))',
                                                  '        self.assertEqual(len(v2_history.KINDS), 7)',
                                                  '        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", '
                                                  'values.KINDS)'],
                                                 ['            "DECLARE_MISSING", "RESTART_UNKNOWN", '
                                                  '"RECOVERY_RESTORE", "SCHEMA_MIGRATION", '
                                                  '"RECOVERY_PREFIX_ADOPTION",',
                                                  '            "READY", "CONFIRMED_IN_MEMORY"]))',
                                                  '        self.assertEqual(len(v2_history.KINDS), 8)',
                                                  '        self.assertEqual(values.KINDS[-1], '
                                                  '"RECOVERY_PREFIX_ADOPTION")              # added by B-5b'],
                                                 ['@@ -105,2 +105,2', '@@ -110 +110', '@@ -115 +115']),
 'tests/v2_history_ops/test_b17_scope.py': (['                  "SCHEMA_MIGRATION"}',
                                             '                                        "v2_history_diagnose/", '
                                             '"tests/v2_history_diagnose/"))',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))',
                                             '                if path != "v2_recovery/commands.py":',
                                             '                       ":(exclude)tests/v2_history_diagnose")'],
                                            ['                  "SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}',
                                             '        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
                                             '"v2_history/view.py", "v2_history/restore.py",',
                                             '               "tests/v2_history/test_h02_values_codec.py", '
                                             '"tests/v2_history/test_h14_scope_and_stop.py")',
                                             '                                        "v2_history_diagnose/", '
                                             '"tests/v2_history_diagnose/",',
                                             '                                        "v2_history_adopt/", '
                                             '"tests/v2_history_adopt/"))',
                                             '                       or path in b5b',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",',
                                             '                                   '
                                             '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))',
                                             '                if path != "v2_recovery/commands.py" and path not in '
                                             'b5b:',
                                             '                             and path not in '
                                             '("v2_history_adopt/__init__.py", "v2_history/__init__.py")',
                                             '                       ":(exclude)tests/v2_history_diagnose", '
                                             '":(exclude)tests/v2_history_adopt",',
                                             '                       '
                                             '":(exclude)tests/v2_history/test_h02_values_codec.py",',
                                             '                       '
                                             '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")'],
                                            ['@@ -39 +39',
                                             '@@ -182,0 +183,2',
                                             '@@ -187 +189,3',
                                             '@@ -192 +196,2',
                                             '@@ -195 +200',
                                             '@@ -205,0 +211',
                                             '@@ -223 +229,3']),
 'tests/v2_history_restart/test_r3_07_scope.py': (['            if path == "tests/v2_history_ops/test_b17_scope.py":',
                                                   '                                       "v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/")) or path in (',
                                                   '                '
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")',
                                                   '                          "v2_history_diagnose/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")',
                                                   '                       ":(exclude)tests/v2_history_restore", '
                                                   '":(exclude)tests/v2_history_diagnose")',
                                                   '        self.assertEqual(out.stdout.split(), '
                                                   '["tests/v2_history_ops/test_b17_scope.py"])',
                                                   '        # point 1 touches two separate lines of the allowed '
                                                   'list, so git shows four hunks for the three points',
                                                   '        self.assertEqual(sum(1 for l in lines if '
                                                   'l.startswith("@@")), 4)',
                                                   "            '                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history_diagnose")\'])'],
                                                  ['        b5b = ("v2_history/__init__.py", "v2_history/values.py", '
                                                   '"v2_history/view.py", "v2_history/restore.py",',
                                                   '               "v2_history_ops/chain.py", '
                                                   '"tests/v2_history/test_h02_values_codec.py",',
                                                   '               "tests/v2_history/test_h14_scope_and_stop.py")',
                                                   '            if path == "tests/v2_history_ops/test_b17_scope.py" '
                                                   'or path in b5b:',
                                                   '                                       "v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/",',
                                                   '                                       "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/")) or path in (',
                                                   '                '
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
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
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
                                                   "            '                                        "
                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\',',
                                                   "            '                       or path in b5b',",
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
                                                   "            '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
                                                   "            '                if path != "
                                                   '"v2_recovery/commands.py" and path not in b5b:\',',
                                                   "            '                             and path not in "
                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt",\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
                                                   "            '                       "
                                                   '":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\'])'],
                                                  ['@@ -188,0 +189,3',
                                                   '@@ -190 +193',
                                                   '@@ -195 +198,2',
                                                   '@@ -197 +201',
                                                   '@@ -204 +208,2',
                                                   '@@ -210 +215,3',
                                                   '@@ -213,2 +220,5',
                                                   '@@ -221,2 +231,2',
                                                   '@@ -223,0 +234',
                                                   '@@ -225,0 +237',
                                                   '@@ -229,0 +242,3',
                                                   '@@ -233 +248,3',
                                                   '@@ -237 +254,3',
                                                   '@@ -240,0 +260',
                                                   '@@ -244 +264,3']),
 'tests/v2_history_restore/test_r4_09_scope.py': (['                  "SCHEMA_MIGRATION"}',
                                                   "B17_REMOVED = ['                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/"))\',',
                                                   "B17_ADDED = ['                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/",\',',
                                                   " '                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\',',
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
                                                   " '                       "
                                                   '":(exclude)tests/v2_history_diagnose")\']',
                                                   "B17_HUNKS = ['@@ -185 +185,3', '@@ -188 +190,3', '@@ -199,0 "
                                                   "+204,2', '@@ -216 +222,2']",
                                                   "R307_REMOVED = ['            allowed = "
                                                   'path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/")) or path in (\',',
                                                   "R307_ADDED = ['            allowed = "
                                                   'path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/",\',',
                                                   " '                                       "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/")) or path '
                                                   "in (',",
                                                   " '                "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")\',',
                                                   " '                          "
                                                   '"v2_history_diagnose/__init__.py"})\',',
                                                   ' \'                       ":(exclude)tests/v2_history_restore", '
                                                   '":(exclude)tests/v2_history_diagnose")\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/"))\\\',\',',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\\\',\',',
                                                   " '            \\'                       "
                                                   '":(exclude)tests/v2_history_diagnose")\\\'])\']',
                                                   "R307_HUNKS = ['@@ -193,2 +193,5', '@@ -199 +202,3', '@@ -207 "
                                                   "+212,2', '@@ -225 +231,3', '@@ -227 +235,3', '@@ -228,0 +239,2', "
                                                   "'@@ -231 +243,2']",
                                                   '                    if v in KIND_CONSTANTS:',
                                                   '        self.assertEqual(modified, '
                                                   'sorted(SCOPE_TESTS))                            # the only files '
                                                   'that are modified',
                                                   '            if path in SCOPE_TESTS:',
                                                   '            new_b5a = path.startswith(("v2_history_diagnose/", '
                                                   '"tests/v2_history_diagnose/")) or path == \\',
                                                   '                "docs/implementation/V2_RECOVERY_S3B5_RESULT.md"',
                                                   '                         {"v2_history_restore/__init__.py", '
                                                   '"v2_history_diagnose/__init__.py"})',
                                                   '                       '
                                                   '"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md")',
                                                   '                       ":(exclude)tests/v2_history_diagnose")',
                                                   '        self.assertEqual(sorted(out.stdout.split()), '
                                                   'sorted(SCOPE_TESTS))'],
                                                  ['                  "SCHEMA_MIGRATION", '
                                                   '"RECOVERY_PREFIX_ADOPTION"}',
                                                   'B17_REMOVED = [\'                  "SCHEMA_MIGRATION"}\',',
                                                   " '                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/"))\',',
                                                   ' \'                if path != "v2_recovery/commands.py":\',',
                                                   'B17_ADDED = [\'                  "SCHEMA_MIGRATION", '
                                                   '"RECOVERY_PREFIX_ADOPTION"}\',',
                                                   ' \'        b5b = ("v2_history/__init__.py", '
                                                   '"v2_history/values.py", "v2_history/view.py", '
                                                   '"v2_history/restore.py",\',',
                                                   ' \'               "tests/v2_history/test_h02_values_codec.py", '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                   " '                                        "
                                                   '"v2_history_restart/", "tests/v2_history_restart/",\',',
                                                   " '                                        "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
                                                   ' \'                                        "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/"))\',',
                                                   " '                       or path in b5b',",
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
                                                   " '                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
                                                   ' \'                if path != "v2_recovery/commands.py" and path '
                                                   "not in b5b:',",
                                                   " '                             and path not in "
                                                   '("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
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
                                                   " '            if path == "
                                                   '"tests/v2_history_ops/test_b17_scope.py" or path in b5b:\',',
                                                   ' \'            allowed = path.startswith(("v2_history_restart/", '
                                                   '"tests/v2_history_restart/",\',',
                                                   " '                                       "
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\',',
                                                   ' \'                                       "v2_history_adopt/", '
                                                   '"tests/v2_history_adopt/")) or path in (\',',
                                                   " '                "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\',',
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
                                                   " '        # four hunks for the three points of B-3; B-5b adds "
                                                   "the kind constant and its edits of the two methods',",
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
                                                   '"v2_history_diagnose/", "tests/v2_history_diagnose/",\\\',\',',
                                                   " '            \\'                                        "
                                                   '"v2_history_adopt/", "tests/v2_history_adopt/"))\\\',\',',
                                                   ' "            \'                       or path in b5b\',",',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\',\',',
                                                   " '            \\'                                   "
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\',\',',
                                                   " '            \\'                if path != "
                                                   '"v2_recovery/commands.py" and path not in b5b:\\\',\',',
                                                   " '            \\'                             and path not in "
                                                   '("v2_history_adopt/__init__.py", \'',
                                                   ' \'"v2_history/__init__.py")\\\',\',',
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
                                                   '                '
                                                   '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", '
                                                   '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
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
                                                   '                       ":(exclude)tests/v2_history_diagnose", '
                                                   '":(exclude)tests/v2_history_adopt")',
                                                   '        self.assertEqual(sorted(out.stdout.split()), '
                                                   'sorted(SCOPE_TESTS + '
                                                   '("tests/v2_history/test_h02_values_codec.py",',
                                                   '                                                                           '
                                                   '"tests/v2_history/test_h14_scope_and_stop.py")))'],
                                                  ['@@ -38 +38',
                                                   '@@ -79 +79,2',
                                                   '@@ -80,0 +82',
                                                   '@@ -82 +84,4',
                                                   '@@ -84 +89,3',
                                                   '@@ -87 +94,3',
                                                   '@@ -89,0 +99',
                                                   '@@ -91,3 +101,12',
                                                   '@@ -95,0 +115',
                                                   '@@ -96,0 +117,3',
                                                   '@@ -100 +123,5',
                                                   '@@ -102 +129,2',
                                                   '@@ -104 +132',
                                                   '@@ -107 +135,5',
                                                   '@@ -109 +141,14',
                                                   '@@ -112 +157,3',
                                                   '@@ -115 +162,3',
                                                   '@@ -117,0 +167,2',
                                                   '@@ -119,2 +170,17',
                                                   '@@ -198 +264',
                                                   '@@ -349 +415,4',
                                                   '@@ -351 +420',
                                                   '@@ -353,2 +422,3',
                                                   '@@ -360 +430,2',
                                                   '@@ -384 +455,4',
                                                   '@@ -387,2 +461,3']),
 'tests/v2_history_diagnose/test_d5_08_scope.py': (["PINNED = {'tests/v2_history_ops/test_b17_scope.py': "
                                                    "(['                                        "
                                                    '"v2_history_restore/", \'',
                                                    '                                            '
                                                    "['                                        "
                                                    '"v2_history_restore/", \'',
                                                    '                                             '
                                                    '\'"tests/v2_history_diagnose/"))\',',
                                                    '                                             '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\',',
                                                    '                                             '
                                                    "'                       "
                                                    '":(exclude)tests/v2_history_diagnose")\'],',
                                                    "                                            ['@@ -186 +186,2', "
                                                    "'@@ -190 +191,2', '@@ -202,0 +205', '@@ -219 +222,2']),",
                                                    " 'tests/v2_history_restart/test_r3_07_scope.py': "
                                                    "(['                                       "
                                                    '"v2_history_restore/", \'',
                                                    '                                                   '
                                                    "'                '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", \'',
                                                    '                                                  '
                                                    "['                                       "
                                                    '"v2_history_restore/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/")) or path in (\',',
                                                    '                                                   '
                                                    "'                '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", \'',
                                                    '                                                   '
                                                    "'                '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")\',',
                                                    '                                                   '
                                                    "'                          "
                                                    '"v2_history_diagnose/__init__.py"})\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose")\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", '
                                                    '"tests/v2_history_diagnose/"))\\\',\',',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose")\\\'])\'],',
                                                    "                                                  ['@@ -194,2 "
                                                    "+194,4',",
                                                    "                                                   '@@ -201 "
                                                    "+203,2',",
                                                    "                                                   '@@ -210 "
                                                    "+213',",
                                                    "                                                   '@@ -229 "
                                                    "+232,2',",
                                                    "                                                   '@@ -232 "
                                                    "+236,2',",
                                                    "                                                   '@@ -234,0 "
                                                    "+240',",
                                                    "                                                   '@@ -237 "
                                                    "+243,2']),",
                                                    ' \'tests/v2_history_restore/test_r4_09_scope.py\': ([" '
                                                    '\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_restore/", "tests/v2_history_restore/"))\\\',\',',
                                                    '                                                   "B17_HUNKS = '
                                                    '[\'@@ -185 +185,2\', \'@@ -188 +189,2\', \'@@ -199,0 "',
                                                    '                                                   "+202\', '
                                                    '\'@@ -216 +219\']",',
                                                    '                                                   " '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_restore")\\\',\',',
                                                    "                                                   '        out "
                                                    '= self.git("diff", "--name-only", START, "HEAD", \'',
                                                    '                                                   \'"--", '
                                                    '"tests", ":(exclude)tests/v2_history_restore")\'],',
                                                    '                                                  [" '
                                                    '\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_restore/", "tests/v2_history_restore/",\\\',\',',
                                                    '                                                   " '
                                                    '\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", '
                                                    '"tests/v2_history_diagnose/"))\\\',\',',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose")\\\']\',',
                                                    '                                                   "B17_HUNKS = '
                                                    '[\'@@ -185 +185,3\', \'@@ -188 +190,3\', \'@@ -199,0 "',
                                                    '                                                   "+204,2\', '
                                                    '\'@@ -216 +222,2\']",',
                                                    '                                                   " '
                                                    '\'                                       "',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", "tests/v2_history_diagnose/")) or '
                                                    "path '",
                                                    '                                                   "in (\',",',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md")\\\',\',',
                                                    '                                                   " '
                                                    '\'                          "',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/__init__.py"})\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose")\\\',\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", '
                                                    '"tests/v2_history_diagnose/"))\\\\\\\',\\\',\',',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"))\\\\\\\',\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose")\\\\\\\'])\\\']\',',
                                                    '                                                   "R307_HUNKS '
                                                    '= [\'@@ -193,2 +193,5\', \'@@ -199 +202,3\', \'@@ -207 "',
                                                    '                                                   "+212,2\', '
                                                    '\'@@ -225 +231,3\', \'@@ -227 +235,3\', \'@@ -228,0 +239,2\', "',
                                                    '                                                   "\'@@ -231 '
                                                    '+243,2\']",',
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/")) or path == \\\\\',',
                                                    '                                                   '
                                                    "'                "
                                                    '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md"\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/__init__.py"})\',',
                                                    "                                                   '        out "
                                                    '= self.git("diff", "--name-only", START, "HEAD", \'',
                                                    '                                                   \'"--", '
                                                    '"tests", ":(exclude)tests/v2_history_restore",\',',
                                                    '                                                   '
                                                    "'                       "
                                                    '":(exclude)tests/v2_history_diagnose")\'],',
                                                    "                                                  ['@@ -83 "
                                                    "+83,2',",
                                                    "                                                   '@@ -85 "
                                                    "+86,2',",
                                                    "                                                   '@@ -87,2 "
                                                    "+89,4',",
                                                    "                                                   '@@ -97,3 "
                                                    "+101,4',",
                                                    "                                                   '@@ -101 "
                                                    "+106,2',",
                                                    "                                                   '@@ -103 "
                                                    "+109',",
                                                    "                                                   '@@ -105 "
                                                    "+111,2',",
                                                    "                                                   '@@ -107 "
                                                    "+114,2',",
                                                    "                                                   '@@ -109,9 "
                                                    "+117,4',",
                                                    "                                                   '@@ -350 "
                                                    "+353,3',",
                                                    "                                                   '@@ -354 "
                                                    "+359,2',",
                                                    "                                                   '@@ -380 "
                                                    "+386,2'])}",
                                                    '        self.assertNotIn("RECOVERY_PREFIX_ADOPTION", '
                                                    'v2_history.KINDS)',
                                                    '        self.assertEqual(sorted(p for s, p in rows if s == '
                                                    '"M"), sorted(SCOPE_TESTS))',
                                                    '            self.assertTrue(allowed_new_path(path), "unexpected '
                                                    'change: %s %s" % (status, path))',
                                                    '        self.assertEqual({p for p in paths if '
                                                    'p.endswith("__init__.py")}, '
                                                    '{"v2_history_diagnose/__init__.py"})',
                                                    '        out = self.git("diff", "--name-only", START, "HEAD", '
                                                    '"--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS)',
                                                    '                       *[":(exclude)%s" % p for p in '
                                                    'SCOPE_TESTS])',
                                                    '        out = self.git("diff", "--name-only", START, "HEAD", '
                                                    '"--", "docs", ":(exclude)%s" % RESULT_DOC)',
                                                    '            if path == corrected:',
                                                    '                seen_corrected = True',
                                                    '        corrected = set(SCOPE_TESTS)',
                                                    '            '
                                                    'self.assertEqual(len(re.findall(r"self\\.assert\\w*\\(", new)), '
                                                    'len(re.findall(r"self\\.assert\\w*\\(", old)), path)',
                                                    '        funcs, _ = self.spans(SCOPE_TESTS[0])',
                                                    '                                             '
                                                    'funcs["test_existing_tests_and_fixtures_are_untouched"]])',
                                                    '            "B17_REMOVED", "B17_ADDED", "B17_HUNKS", '
                                                    '"R307_REMOVED", "R307_ADDED", "R307_HUNKS")] + [',
                                                    '            '
                                                    'funcs["test_no_existing_runtime_old_test_fixture_or_setting_differs"]])'],
                                                   ["PINNED = {'tests/v2_history_ops/test_b17_scope.py': "
                                                    '([\'                  "SCHEMA_MIGRATION"}\',',
                                                    '                                             '
                                                    "'                                        "
                                                    '"v2_history_restore/", \'',
                                                    "                                             '                "
                                                    'if path != "v2_recovery/commands.py":\',',
                                                    "                                            ['                  "
                                                    '"SCHEMA_MIGRATION", "RECOVERY_PREFIX_ADOPTION"}\',',
                                                    "                                             '        b5b = "
                                                    '("v2_history/__init__.py", "v2_history/values.py", \'',
                                                    '                                             '
                                                    '\'"v2_history/view.py", "v2_history/restore.py",\',',
                                                    "                                             '               "
                                                    '"tests/v2_history/test_h02_values_codec.py", \'',
                                                    '                                             '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                    '                                             '
                                                    "'                                        "
                                                    '"v2_history_restore/", \'',
                                                    '                                             '
                                                    '\'"tests/v2_history_diagnose/",\',',
                                                    '                                             '
                                                    '\'                                        "v2_history_adopt/", '
                                                    "'",
                                                    '                                             '
                                                    '\'"tests/v2_history_adopt/"))\',',
                                                    '                                             '
                                                    "'                       or path in b5b',",
                                                    '                                             '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\',',
                                                    '                                             '
                                                    "'                                   '",
                                                    '                                             '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\',',
                                                    "                                             '                "
                                                    'if path != "v2_recovery/commands.py" and path not in \'',
                                                    "                                             'b5b:',",
                                                    '                                             '
                                                    "'                             and path not in '",
                                                    '                                             '
                                                    '\'("v2_history_adopt/__init__.py", "v2_history/__init__.py")\',',
                                                    '                                             '
                                                    '\'                       ":(exclude)tests/v2_history_diagnose", '
                                                    "'",
                                                    '                                             '
                                                    '\'":(exclude)tests/v2_history_adopt",\',',
                                                    '                                             '
                                                    "'                       '",
                                                    '                                             '
                                                    '\'":(exclude)tests/v2_history/test_h02_values_codec.py",\',',
                                                    '                                             '
                                                    "'                       '",
                                                    '                                             '
                                                    '\'":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\'],',
                                                    "                                            ['@@ -39 +39',",
                                                    "                                             '@@ -182,0 "
                                                    "+183,2',",
                                                    "                                             '@@ -186 +188,4',",
                                                    "                                             '@@ -190 +195,3',",
                                                    "                                             '@@ -193 +200',",
                                                    "                                             '@@ -202,0 "
                                                    "+210,2',",
                                                    "                                             '@@ -219 "
                                                    "+228,4']),",
                                                    " 'tests/v2_history_restart/test_r3_07_scope.py': (['            "
                                                    'if path == "tests/v2_history_ops/test_b17_scope.py":\',',
                                                    '                                                   '
                                                    '\'                                       "v2_history_restore/", '
                                                    "'",
                                                    '                                                   '
                                                    "'                "
                                                    '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", \'',
                                                    '                                                   '
                                                    "'                       '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")\',',
                                                    "                                                   '        "
                                                    "self.assertEqual(out.stdout.split(), '",
                                                    '                                                   '
                                                    '\'["tests/v2_history_ops/test_b17_scope.py"])\',',
                                                    "                                                   '        # "
                                                    "point 1 touches two separate lines of the allowed list, '",
                                                    "                                                   'so git "
                                                    "shows four hunks for the three points',",
                                                    "                                                   '        "
                                                    "self.assertEqual(sum(1 for l in lines if '",
                                                    '                                                   '
                                                    '\'l.startswith("@@")), 4)\',',
                                                    "                                                  ['        b5b "
                                                    '= ("v2_history/__init__.py", "v2_history/values.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/view.py", "v2_history/restore.py",\',',
                                                    '                                                   '
                                                    '\'               "v2_history_ops/chain.py", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h02_values_codec.py",\',',
                                                    '                                                   '
                                                    "'               "
                                                    '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                    "                                                   '            "
                                                    'if path == "tests/v2_history_ops/test_b17_scope.py" or \'',
                                                    "                                                   'path in "
                                                    "b5b:',",
                                                    '                                                   '
                                                    '\'                                       "v2_history_restore/", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/",\',',
                                                    '                                                   '
                                                    '\'                                       "v2_history_adopt/", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history_adopt/")) or path in (\',',
                                                    '                                                   '
                                                    "'                "
                                                    '"docs/implementation/V2_RECOVERY_S3B3_RESULT.md", \'',
                                                    '                                                   '
                                                    "'                "
                                                    '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\',',
                                                    '                                                   '
                                                    '\'                          "v2_history_diagnose/__init__.py", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"v2_history_adopt/__init__.py",\',',
                                                    '                                                   '
                                                    '\'                          "v2_history/__init__.py"})\',',
                                                    '                                                   '
                                                    "'                       '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/__init__.py",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)v2_history/values.py", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/view.py",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)v2_history/restore.py", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history_ops/chain.py")\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)tests/v2_history_adopt")\',',
                                                    "                                                   '        "
                                                    "self.assertEqual(out.stdout.split(), '",
                                                    '                                                   '
                                                    '\'["tests/v2_history/test_h02_values_codec.py",\',',
                                                    '                                                   '
                                                    "'                                              '",
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py",\',',
                                                    '                                                   '
                                                    "'                                              '",
                                                    '                                                   '
                                                    '\'"tests/v2_history_ops/test_b17_scope.py"])\',',
                                                    "                                                   '        # "
                                                    "four hunks for the three points of B-3; B-5b adds the '",
                                                    "                                                   'kind "
                                                    "constant and its edits of the two methods',",
                                                    "                                                   '        "
                                                    "self.assertEqual(sum(1 for l in lines if '",
                                                    '                                                   '
                                                    '\'l.startswith("@@")), 7)\',',
                                                    "                                                   '            "
                                                    '\\\'                  "SCHEMA_MIGRATION"}\\\',\',',
                                                    '                                                   "            '
                                                    '\'                if path != "',
                                                    '                                                   '
                                                    '\'"v2_recovery/commands.py":\\\',\',',
                                                    "                                                   '            "
                                                    '\\\'                  "SCHEMA_MIGRATION", \'',
                                                    '                                                   '
                                                    '\'"RECOVERY_PREFIX_ADOPTION"}\\\',\',',
                                                    "                                                   '            "
                                                    '\\\'        b5b = ("v2_history/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/values.py", "v2_history/view.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/restore.py",\\\',\',',
                                                    '                                                   "            '
                                                    '\'               "',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h02_values_codec.py", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py")\\\',\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", "tests/v2_history_diagnose/",\\\',\',',
                                                    '                                                   "            '
                                                    '\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_adopt/", "tests/v2_history_adopt/"))\\\',\',',
                                                    '                                                   "            '
                                                    '\'                       or path in b5b\',",',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\',\',',
                                                    '                                                   "            '
                                                    '\'                                   "',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\',\',',
                                                    "                                                   '            "
                                                    '\\\'                if path != "v2_recovery/commands.py" \'',
                                                    '                                                   "and path '
                                                    'not in b5b:\',",',
                                                    '                                                   "            '
                                                    '\'                             and path not in "',
                                                    '                                                   '
                                                    '\'("v2_history_adopt/__init__.py", '
                                                    '"v2_history/__init__.py")\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose", \'',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_adopt",\\\',\',',
                                                    '                                                   "            '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h02_values_codec.py",\\\',\',',
                                                    '                                                   "            '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\\\'])\'],',
                                                    "                                                  ['@@ -188,0 "
                                                    "+189,3',",
                                                    "                                                   '@@ -190 "
                                                    "+193',",
                                                    "                                                   '@@ -194,2 "
                                                    "+197,5',",
                                                    "                                                   '@@ -201 "
                                                    "+207,3',",
                                                    "                                                   '@@ -207 "
                                                    "+215,3',",
                                                    "                                                   '@@ -210,2 "
                                                    "+220,5',",
                                                    "                                                   '@@ -218,2 "
                                                    "+231,2',",
                                                    "                                                   '@@ -220,0 "
                                                    "+234',",
                                                    "                                                   '@@ -222,0 "
                                                    "+237',",
                                                    "                                                   '@@ -226,0 "
                                                    "+242,3',",
                                                    "                                                   '@@ -229 "
                                                    "+247,4',",
                                                    "                                                   '@@ -232 "
                                                    "+253,4',",
                                                    "                                                   '@@ -234,0 "
                                                    "+259,2',",
                                                    "                                                   '@@ -237 "
                                                    "+263,4']),",
                                                    " 'tests/v2_history_restore/test_r4_09_scope.py': "
                                                    '([\'                  "SCHEMA_MIGRATION"}\',',
                                                    '                                                   "B17_REMOVED '
                                                    '= [\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_restart/", "tests/v2_history_restart/"))\\\',\',',
                                                    '                                                   "B17_ADDED = '
                                                    '[\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_restart/", "tests/v2_history_restart/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_restore/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restore/"))\\\',\',',
                                                    '                                                   "B17_HUNKS = '
                                                    '[\'@@ -185 +185,2\', \'@@ -188 +189,2\', \'@@ -199,0 +202\', "',
                                                    '                                                   "\'@@ -216 '
                                                    '+219\']",',
                                                    '                                                   '
                                                    '"R307_REMOVED = [\'            allowed = "',
                                                    '                                                   '
                                                    '\'path.startswith(("v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/")) or path in (\\\',\',',
                                                    '                                                   "R307_ADDED '
                                                    '= [\'            allowed = "',
                                                    '                                                   '
                                                    '\'path.startswith(("v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                       "
                                                    '":(exclude)tests/v2_history_restore")\\\',\',',
                                                    '                                                   '
                                                    "'                    if v in KIND_CONSTANTS:',",
                                                    "                                                   '        "
                                                    "self.assertEqual(modified, '",
                                                    '                                                   '
                                                    "'sorted(SCOPE_TESTS))                            # the only "
                                                    "files '",
                                                    "                                                   'that are "
                                                    "modified',",
                                                    "                                                   '            "
                                                    "if path in SCOPE_TESTS:',",
                                                    '                                                   '
                                                    "'                       '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B3_RESULT.md")\',',
                                                    "                                                   '        out "
                                                    '= self.git("diff", "--name-only", START, "HEAD", "--", \'',
                                                    '                                                   \'"tests", '
                                                    '":(exclude)tests/v2_history_restore")\',',
                                                    "                                                   '        "
                                                    "self.assertEqual(sorted(out.stdout.split()), '",
                                                    '                                                   '
                                                    "'sorted(SCOPE_TESTS))'],",
                                                    '                                                  '
                                                    '[\'                  "SCHEMA_MIGRATION", '
                                                    '"RECOVERY_PREFIX_ADOPTION"}\',',
                                                    "                                                   'B17_REMOVED "
                                                    '= [\\\'                  "SCHEMA_MIGRATION"}\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/"))\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                if path != "
                                                    '"v2_recovery/commands.py":\\\',\',',
                                                    "                                                   'B17_ADDED = "
                                                    '[\\\'                  "SCHEMA_MIGRATION", \'',
                                                    '                                                   '
                                                    '\'"RECOVERY_PREFIX_ADOPTION"}\\\',\',',
                                                    "                                                   ' \\'        "
                                                    'b5b = ("v2_history/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/values.py", "v2_history/view.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/restore.py",\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'               "tests/v2_history/test_h02_values_codec.py", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py")\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_restore/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restore/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_diagnose/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                        "
                                                    '"v2_history_adopt/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_adopt/"))\\\',\',',
                                                    '                                                   " '
                                                    '\'                       or path in b5b\',",',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\',\',',
                                                    '                                                   " '
                                                    '\'                                   "',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'                if path != "v2_recovery/commands.py" and '
                                                    "path '",
                                                    '                                                   "not in '
                                                    'b5b:\',",',
                                                    '                                                   " '
                                                    '\'                             and path not in "',
                                                    '                                                   '
                                                    '\'("v2_history_adopt/__init__.py", '
                                                    '"v2_history/__init__.py")\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                       "
                                                    '":(exclude)tests/v2_history_diagnose", \'',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_adopt",\\\',\',',
                                                    '                                                   " '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h02_values_codec.py",\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\\\']\',',
                                                    '                                                   "B17_HUNKS = '
                                                    '[\'@@ -39 +39\',",',
                                                    '                                                   " \'@@ '
                                                    '-182,0 +183,2\',",',
                                                    '                                                   " \'@@ -185 '
                                                    '+187,5\',",',
                                                    '                                                   " \'@@ -188 '
                                                    '+194,4\',",',
                                                    '                                                   " \'@@ -191 '
                                                    '+200\',",',
                                                    '                                                   " \'@@ '
                                                    '-199,0 +209,3\',",',
                                                    '                                                   " \'@@ -216 '
                                                    '+228,4\']",',
                                                    '                                                   '
                                                    '"R307_REMOVED = [\'            if path == "',
                                                    '                                                   '
                                                    '\'"tests/v2_history_ops/test_b17_scope.py":\\\',\',',
                                                    "                                                   ' "
                                                    "\\'            allowed = "
                                                    'path.startswith(("v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/")) or path in (\\\',\',',
                                                    '                                                   " '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md")\\\',\',',
                                                    '                                                   " \'        '
                                                    'self.assertEqual(out.stdout.split(), "',
                                                    '                                                   '
                                                    '\'["tests/v2_history_ops/test_b17_scope.py"])\\\',\',',
                                                    '                                                   " \'        '
                                                    '# point 1 touches two separate lines of the allowed "',
                                                    '                                                   "list, so '
                                                    'git shows four hunks for the three points\',",',
                                                    '                                                   " \'        '
                                                    'self.assertEqual(sum(1 for l in lines if "',
                                                    '                                                   '
                                                    '\'l.startswith("@@")), 4)\\\',\',',
                                                    "                                                   'R307_ADDED "
                                                    '= [\\\'        b5b = ("v2_history/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/values.py", "v2_history/view.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/restore.py",\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'               "v2_history_ops/chain.py", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h02_values_codec.py",\\\',\',',
                                                    '                                                   " '
                                                    '\'               "',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py")\\\',\',',
                                                    "                                                   ' "
                                                    "\\'            if path == "
                                                    '"tests/v2_history_ops/test_b17_scope.py" \'',
                                                    '                                                   "or path in '
                                                    'b5b:\',",',
                                                    "                                                   ' "
                                                    "\\'            allowed = "
                                                    'path.startswith(("v2_history_restart/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_restart/",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                                       "
                                                    '"v2_history_diagnose/", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/",\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'                                       "v2_history_adopt/", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history_adopt/")) or path in (\\\',\',',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                          "
                                                    '"v2_history_diagnose/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history_adopt/__init__.py",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                          "
                                                    '"v2_history/__init__.py"})\\\',\',',
                                                    '                                                   " '
                                                    '\'                       "',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/__init__.py",\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'                       ":(exclude)v2_history/values.py", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/view.py",\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'                       ":(exclude)v2_history/restore.py", '
                                                    "'",
                                                    '                                                   '
                                                    '\'":(exclude)v2_history_ops/chain.py")\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose",\\\',\',',
                                                    "                                                   ' "
                                                    "\\'                       "
                                                    '":(exclude)tests/v2_history_adopt")\\\',\',',
                                                    '                                                   " \'        '
                                                    'self.assertEqual(out.stdout.split(), "',
                                                    '                                                   '
                                                    '\'["tests/v2_history/test_h02_values_codec.py",\\\',\',',
                                                    '                                                   " '
                                                    '\'                                              "',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py",\\\',\',',
                                                    '                                                   " '
                                                    '\'                                              "',
                                                    '                                                   '
                                                    '\'"tests/v2_history_ops/test_b17_scope.py"])\\\',\',',
                                                    '                                                   " \'        '
                                                    '# four hunks for the three points of B-3; B-5b adds the "',
                                                    '                                                   "kind '
                                                    'constant and its edits of the two methods\',",',
                                                    '                                                   " \'        '
                                                    'self.assertEqual(sum(1 for l in lines if "',
                                                    '                                                   '
                                                    '\'l.startswith("@@")), 7)\\\',\',',
                                                    "                                                   ' "
                                                    "\\'            \\\\\\'                  "
                                                    '"SCHEMA_MIGRATION"}\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                if path != "',
                                                    '                                                   '
                                                    '\'"v2_recovery/commands.py":\\\\\\\',\\\',\',',
                                                    "                                                   ' "
                                                    '\\\'            \\\\\\\'                  "SCHEMA_MIGRATION", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"RECOVERY_PREFIX_ADOPTION"}\\\\\\\',\\\',\',',
                                                    "                                                   ' "
                                                    "\\'            \\\\\\'        b5b = "
                                                    '("v2_history/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/values.py", "v2_history/view.py", \\\'\',',
                                                    "                                                   ' "
                                                    '\\\'"v2_history/restore.py",\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'               "',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h02_values_codec.py", \\\'\',',
                                                    "                                                   ' "
                                                    '\\\'"tests/v2_history/test_h14_scope_and_stop.py")\\\\\\\',\\\',\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/", '
                                                    '"tests/v2_history_diagnose/",\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                                        "',
                                                    '                                                   '
                                                    '\'"v2_history_adopt/", '
                                                    '"tests/v2_history_adopt/"))\\\\\\\',\\\',\',',
                                                    "                                                   ' "
                                                    '"            \\\'                       or path in '
                                                    'b5b\\\',",\',',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5_RESULT.md",\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                                   "',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"))\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                if path != "',
                                                    '                                                   '
                                                    '\'"v2_recovery/commands.py" and path not in '
                                                    "b5b:\\\\\\',\\',',",
                                                    '                                                   " '
                                                    "'            \\\\'                             and path not in "
                                                    '"',
                                                    '                                                   '
                                                    '\'("v2_history_adopt/__init__.py", \\\'\',',
                                                    "                                                   ' "
                                                    '\\\'"v2_history/__init__.py")\\\\\\\',\\\',\',',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_diagnose", \'',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_adopt",\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h02_values_codec.py",\\\\\\\',\\\',\',',
                                                    '                                                   " '
                                                    '\'            \\\\\'                       "',
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history/test_h14_scope_and_stop.py")\\\\\\\'])\\\']\',',
                                                    '                                                   "R307_HUNKS '
                                                    '= [\'@@ -188,0 +189,3\',",',
                                                    '                                                   " \'@@ -190 '
                                                    '+193\',",',
                                                    '                                                   " \'@@ '
                                                    '-193,2 +196,6\',",',
                                                    '                                                   " \'@@ -199 '
                                                    '+206,4\',",',
                                                    '                                                   " \'@@ -205 '
                                                    '+215,3\',",',
                                                    '                                                   " \'@@ '
                                                    '-207,2 +219,6\',",',
                                                    '                                                   " \'@@ '
                                                    '-215,2 +231,2\',",',
                                                    '                                                   " \'@@ '
                                                    '-217,0 +234\',",',
                                                    '                                                   " \'@@ '
                                                    '-219,0 +237\',",',
                                                    '                                                   " \'@@ '
                                                    '-223,0 +242,3\',",',
                                                    '                                                   " \'@@ -225 '
                                                    '+246,5\',",',
                                                    '                                                   " \'@@ -227 '
                                                    '+252,5\',",',
                                                    '                                                   " \'@@ '
                                                    '-228,0 +258,3\',",',
                                                    '                                                   " \'@@ -231 '
                                                    '+263,4\']",',
                                                    '                                                   '
                                                    "'                    if v in KIND_CONSTANTS or v == '",
                                                    '                                                   '
                                                    '\'"restore_before_adoption":      # the B-5b refusal code\',',
                                                    "                                                   '        b5b "
                                                    '= ("v2_history/__init__.py", "v2_history/values.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/view.py", "v2_history/restore.py",\',',
                                                    '                                                   '
                                                    '\'               "v2_history_ops/chain.py", \'',
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h02_values_codec.py",\',',
                                                    '                                                   '
                                                    "'               "
                                                    '"tests/v2_history/test_h14_scope_and_stop.py")\',',
                                                    "                                                   '        "
                                                    "self.assertEqual(modified, sorted(SCOPE_TESTS + '",
                                                    '                                                   '
                                                    "'b5b))                      # the only files that are "
                                                    "modified',",
                                                    "                                                   '            "
                                                    "if path in SCOPE_TESTS or path in b5b:',",
                                                    '                                                   '
                                                    '\'"tests/v2_history_diagnose/",\',',
                                                    '                                                   '
                                                    '\'                                       "v2_history_adopt/", '
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history_adopt/")) or path in (\',',
                                                    '                                                   '
                                                    "'                "
                                                    '"docs/implementation/V2_RECOVERY_S3B5_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")\',',
                                                    '                                                   '
                                                    '\'"v2_history_diagnose/__init__.py",\',',
                                                    '                                                   '
                                                    '\'                          "v2_history_adopt/__init__.py", \'',
                                                    '                                                   '
                                                    '\'"v2_history/__init__.py"})\',',
                                                    '                                                   '
                                                    "'                       '",
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B2_RESULT.md", \'',
                                                    '                                                   '
                                                    '\'"docs/implementation/V2_RECOVERY_S3B3_RESULT.md",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)v2_history/__init__.py", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/values.py",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)v2_history/view.py", \'',
                                                    '                                                   '
                                                    '\'":(exclude)v2_history/restore.py",\',',
                                                    '                                                   '
                                                    "'                       "
                                                    '":(exclude)v2_history_ops/chain.py")\',',
                                                    "                                                   '        out "
                                                    '= self.git("diff", "--name-only", START, "HEAD", "--", \'',
                                                    '                                                   \'"tests", '
                                                    '":(exclude)tests/v2_history_restore",\',',
                                                    '                                                   '
                                                    '\'                       ":(exclude)tests/v2_history_diagnose", '
                                                    "'",
                                                    '                                                   '
                                                    '\'":(exclude)tests/v2_history_adopt")\',',
                                                    "                                                   '        "
                                                    "self.assertEqual(sorted(out.stdout.split()), '",
                                                    '                                                   '
                                                    "'sorted(SCOPE_TESTS + "
                                                    '("tests/v2_history/test_h02_values_codec.py",\',',
                                                    '                                                   '
                                                    "'                                                                           "
                                                    "'",
                                                    '                                                   '
                                                    '\'"tests/v2_history/test_h14_scope_and_stop.py")))\'],',
                                                    "                                                  ['@@ -38 "
                                                    "+38',",
                                                    "                                                   '@@ -79 "
                                                    "+79,2',",
                                                    "                                                   '@@ -80,0 "
                                                    "+82',",
                                                    "                                                   '@@ -82,2 "
                                                    "+84,8',",
                                                    "                                                   '@@ -85 "
                                                    "+93,4',",
                                                    "                                                   '@@ -87,3 "
                                                    "+98,15',",
                                                    "                                                   '@@ -91,0 "
                                                    "+115',",
                                                    "                                                   '@@ -92,0 "
                                                    "+117,3',",
                                                    "                                                   '@@ -96,4 "
                                                    "+123,10',",
                                                    "                                                   '@@ -101 "
                                                    "+134,6',",
                                                    "                                                   '@@ -103 "
                                                    "+141,14',",
                                                    "                                                   '@@ -105 "
                                                    "+156,4',",
                                                    "                                                   '@@ -107 "
                                                    "+161,4',",
                                                    "                                                   '@@ -109,9 "
                                                    "+166,21',",
                                                    "                                                   '@@ -195 "
                                                    "+264',",
                                                    "                                                   '@@ -346 "
                                                    "+415,4',",
                                                    "                                                   '@@ -348 "
                                                    "+420',",
                                                    "                                                   '@@ -350 "
                                                    "+422,4',",
                                                    "                                                   '@@ -354 "
                                                    "+429,3',",
                                                    "                                                   '@@ -378 "
                                                    "+455,4',",
                                                    "                                                   '@@ -380,2 "
                                                    "+460,4'])}",
                                                    '        self.assertEqual(v2_history.KINDS[-1], '
                                                    '"RECOVERY_PREFIX_ADOPTION")              # the kind is added by '
                                                    'B-5b',
                                                    '        b5b = ("v2_history/__init__.py", '
                                                    '"v2_history/values.py", "v2_history/view.py", '
                                                    '"v2_history/restore.py",',
                                                    '               "v2_history_ops/chain.py", '
                                                    '"v2_history_restore/points.py",',
                                                    '               "tests/v2_history/test_h02_values_codec.py", '
                                                    '"tests/v2_history/test_h14_scope_and_stop.py")',
                                                    '        self.assertEqual(sorted(p for s, p in rows if s == '
                                                    '"M"), sorted(SCOPE_TESTS + b5b))',
                                                    '            new_b5b = path.startswith(("v2_history_adopt/", '
                                                    '"tests/v2_history_adopt/")) or \\',
                                                    '                path == '
                                                    '"docs/implementation/V2_RECOVERY_S3B5B_RESULT.md"',
                                                    '            self.assertTrue(allowed_new_path(path) or new_b5b, '
                                                    '"unexpected change: %s %s" % (status, path))',
                                                    '        self.assertEqual({p for p in paths if '
                                                    'p.endswith("__init__.py")},',
                                                    '                         {"v2_history_diagnose/__init__.py", '
                                                    '"v2_history_adopt/__init__.py", "v2_history/__init__.py"})',
                                                    '        b5b = ("v2_history/__init__.py", '
                                                    '"v2_history/values.py", "v2_history/view.py", '
                                                    '"v2_history/restore.py",',
                                                    '               "v2_history_ops/chain.py", '
                                                    '"v2_history_restore/points.py",',
                                                    '               "tests/v2_history/test_h02_values_codec.py", '
                                                    '"tests/v2_history/test_h14_scope_and_stop.py")',
                                                    '        out = self.git("diff", "--name-only", START, "HEAD", '
                                                    '"--", *UNCHANGED_ROOTS, *UNCHANGED_DOCS,',
                                                    '                       *[":(exclude)%s" % p for p in b5b])',
                                                    '                       ":(exclude)tests/v2_history_adopt", '
                                                    '*[":(exclude)%s" % p for p in SCOPE_TESTS + b5b])',
                                                    '        out = self.git("diff", "--name-only", START, "HEAD", '
                                                    '"--", "docs", ":(exclude)%s" % RESULT_DOC,',
                                                    '                       '
                                                    '":(exclude)docs/implementation/V2_RECOVERY_S3B5B_RESULT.md")',
                                                    '            if path in (corrected, '
                                                    '"v2_history_restore/points.py"):            # points.py: '
                                                    'changed by B-5b',
                                                    '                seen_corrected = seen_corrected or path == '
                                                    'corrected',
                                                    '        corrected = set(SCOPE_TESTS) | '
                                                    '{"v2_history/__init__.py", "v2_history/values.py", '
                                                    '"v2_history/view.py",',
                                                    '                                        '
                                                    '"v2_history/restore.py", "v2_history_ops/chain.py",',
                                                    '                                        '
                                                    '"tests/v2_history/test_h02_values_codec.py",',
                                                    '                                        '
                                                    '"tests/v2_history/test_h14_scope_and_stop.py"}',
                                                    '            # counted as calls (B-5b): the pinned text of the '
                                                    'r4_09 lists quotes assert calls of the older tests',
                                                    '            asserts = lambda text: sum(1 for n in '
                                                    'ast.walk(ast.parse(text)) if isinstance(n, ast.Call)  # noqa: '
                                                    'E731',
                                                    '                                       and isinstance(n.func, '
                                                    'ast.Attribute) and n.func.attr.startswith("assert"))',
                                                    '            self.assertEqual(asserts(new), asserts(old), path)',
                                                    '        funcs, assigns = self.spans(SCOPE_TESTS[0])',
                                                    '                                             '
                                                    'funcs["test_existing_tests_and_fixtures_are_untouched"],',
                                                    '                                             '
                                                    'assigns["KIND_CONSTANTS"]])',
                                                    '            "B17_REMOVED", "B17_ADDED", "B17_HUNKS", '
                                                    '"R307_REMOVED", "R307_ADDED", "R307_HUNKS", "KIND_CONSTANTS")] '
                                                    '+ [',
                                                    '            '
                                                    'funcs["test_no_existing_runtime_old_test_fixture_or_setting_differs"],',
                                                    '            funcs["test_nothing_of_the_later_stages"]])'],
                                                   ['@@ -62 +62,2',
                                                    '@@ -65,0 +67',
                                                    '@@ -68 +70,6',
                                                    '@@ -71 +78,4',
                                                    '@@ -75 +85,5',
                                                    '@@ -77,0 +92,2',
                                                    '@@ -80,3 +96,15',
                                                    '@@ -84,2 +112',
                                                    '@@ -88,0 +116,2',
                                                    '@@ -89,0 +119,6',
                                                    '@@ -97 +132,8',
                                                    '@@ -100,3 +142,4',
                                                    '@@ -104,2 +147,2',
                                                    '@@ -108 +151,10',
                                                    '@@ -110 +162,23',
                                                    '@@ -114 +188,4',
                                                    '@@ -118 +195,5',
                                                    '@@ -120,0 +202,2',
                                                    '@@ -125,10 +208,27',
                                                    '@@ -139,2 +239,8',
                                                    '@@ -148,2 +254',
                                                    '@@ -163,0 +269,5',
                                                    '@@ -168,6 +278,28',
                                                    '@@ -177 +309,5',
                                                    '@@ -179,0 +316,2',
                                                    '@@ -181,0 +320,4',
                                                    '@@ -183,3 +325,31',
                                                    '@@ -188,3 +358,4',
                                                    '@@ -195 +366,2',
                                                    '@@ -198,2 +370,10',
                                                    '@@ -201 +381,23',
                                                    '@@ -205 +407,4',
                                                    '@@ -209 +414,5',
                                                    '@@ -211,0 +421,3',
                                                    '@@ -216,4 +428,30',
                                                    '@@ -221,2 +459,5',
                                                    '@@ -228,16 +469,40',
                                                    '@@ -412 +677',
                                                    '@@ -474 +739,4',
                                                    '@@ -479 +747,3',
                                                    '@@ -481 +751,2',
                                                    '@@ -487 +758,5',
                                                    '@@ -490 +765',
                                                    '@@ -492 +767,2',
                                                    '@@ -506,2 +782,2',
                                                    '@@ -523 +799,4',
                                                    '@@ -553 +832,4',
                                                    '@@ -590 +872',
                                                    '@@ -592 +874,2',
                                                    '@@ -599 +882',
                                                    '@@ -601 +884,2'])}
# --- PINNED END ---
NEW_FILES = ["__init__.py", "build.py", "confirm.py", "errors.py", "prepare.py", "values.py"]
# paths that must be identical (blob by blob) to the code start, apart from the twelve files above
UNCHANGED_ROOTS = ("v2_core", "v2_persistence", "v2_recovery", "v2_history_restart", "v2_history_diagnose", "main.py",
                   "requirements.txt", ".github", "research", "docs/STATUS.md", "docs/ROADMAP.md",
                   "docs/MODEL_POLICY.md", "CLAUDE.md", "README.md")
# the places a corrected test may change (section 7.2 of the design): module-level names and test functions
FUNC = "func"
NAME = "name"
PLACES = {
    "tests/v2_history/test_h02_values_codec.py": [(FUNC, "test_unknown_kind_and_the_b5_kind")],
    "tests/v2_history/test_h14_scope_and_stop.py": [(FUNC, "test_the_public_surface_is_exactly_the_planned_one"),
                                                    (FUNC, "test_consume_and_the_b5_kind_are_refused")],
    "tests/v2_history_ops/test_b17_scope.py": [(NAME, "KIND_CONSTANTS"), (FUNC, "test_only_the_allowed_paths_differ"),
                                               (FUNC, "test_existing_tests_and_fixtures_are_untouched")],
    "tests/v2_history_restart/test_r3_07_scope.py": [
        (FUNC, "test_only_the_allowed_paths_differ"), (FUNC, "test_no_existing_runtime_old_test_fixture_or_setting_differs"),
        (FUNC, "test_the_old_range_test_differs_in_exactly_the_three_allowed_places")],
    "tests/v2_history_restore/test_r4_09_scope.py": [
        (NAME, "KIND_CONSTANTS"), (FUNC, "test_nothing_of_the_later_stages"), (NAME, "B17_REMOVED"), (NAME, "B17_ADDED"),
        (NAME, "B17_HUNKS"), (NAME, "R307_REMOVED"), (NAME, "R307_ADDED"), (NAME, "R307_HUNKS"),
        (FUNC, "test_only_the_allowed_paths_differ"), (FUNC, "test_no_existing_runtime_old_test_fixture_or_setting_differs")],
    "tests/v2_history_diagnose/test_d5_08_scope.py": [
        (NAME, "PINNED"), (FUNC, "test_no_adoption_or_store_name_is_exported_or_defined"),
        (FUNC, "test_modified_files_are_exactly_the_three_scope_tests_and_every_other_change_is_a_new_allowed_file"),
        (FUNC, "test_everything_else_is_identical_to_the_code_start"),
        (FUNC, "test_the_b4_runtime_tests_and_result_are_blob_identical_to_the_code_start"),
        (FUNC, "test_the_older_runtimes_and_their_results_are_blob_identical_to_the_code_start"),
        (FUNC, "test_no_assert_is_removed_no_test_is_skipped_and_the_test_functions_are_the_same"),
        (FUNC, "test_each_edit_lies_in_the_allowed_places")],
}
# module-level functions and classes of the older range tests that must stay byte for byte as they were
UNTOUCHED = {
    "tests/v2_history_restore/test_r4_09_scope.py": ("allowed_path", "PathJudgement", "sources"),
    "tests/v2_history_diagnose/test_d5_08_scope.py": ("allowed_new_path", "modified_ok", "sources", "PathJudgement"),
}


def allowed_new_path(path):
    """The paths B-5b may add. Twelve existing files may be modified (see modified_ok)."""
    if path == RESULT_DOC:
        return True
    if path == "v2_history_adopt/__init__.py":
        return True
    if path.endswith("__init__.py"):
        return False
    parts = path.split("/")
    return ((parts[0] == "v2_history_adopt" and len(parts) == 2)
            or (parts[:2] == ["tests", "v2_history_adopt"] and len(parts) == 3))


def modified_ok(path):
    return path in ALL_M


def git(*args):
    return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True, timeout=120)


def start_text(path):
    return git("show", "%s:%s" % (START, path)).stdout


def current_text(path):
    with io.StringIO(git_show_at_end(path)) as f:
        return f.read()


def assert_calls(text):
    """The number of calls of self.assert...() found in the AST (a string that only looks like a call is not counted)."""
    return sum(1 for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr.startswith("assert"))


class PathJudgement(unittest.TestCase):
    def test_the_judgement_accepts_only_the_exact_new_paths(self):
        yes = ["v2_history_adopt/__init__.py", "v2_history_adopt/build.py", "tests/v2_history_adopt/test_a5_01_x.py",
               "tests/v2_history_adopt/a5_helpers.py", "tests/v2_history_adopt/a5_sensitivity.py", RESULT_DOC]
        no = ["tests/v2_history_adopt/__init__.py", "v2_history/adopt.py", "v2_history/checker.py",
              "v2_history_adopt2/x.py", "v2_history_adopts/x.py", "tests/v2_history_adopt_x/y.py",
              "v2_history_adopt/sub/x.py", "v2_history_adopt/sub/__init__.py",
              "docs/implementation/V2_RECOVERY_S3B5B_RESULT.md.bak", "docs/implementation/V2_RECOVERY_S3B5_RESULT.md",
              "docs/implementation/V2_RECOVERY_S3B6_RESULT.md", "v2_history/__init__.py", "v2_history_restore/values.py",
              "v2_history_diagnose/describe.py", "v2_history_diagnose/adopt.py", "tests/v2_history/h_helpers.py",
              "tests/v2_history_restore/r4_helpers.py", "tests/v2_history_diagnose/d5_helpers.py",
              "tests/v2_history_ops/ho_helpers.py", "docs/STATUS.md", "main.py", ".github/workflows/x.yml",
              "research/x.py", "requirements.txt", "v2_core/state.py", "v2_persistence/codec.py",
              "v2_recovery/common.py", "v2_history_restart/build.py", "v2_history_restore/consume.py",
              "v2_history/consume.py", "v2_history_adopt_v1/x.py", "tests/v2_history/test_h15_adoption.py"]
        for p in yes:
            self.assertTrue(allowed_new_path(p), p)
        for p in no:
            self.assertFalse(allowed_new_path(p), p)
        for p in ALL_M:
            self.assertTrue(modified_ok(p))
        self.assertEqual(len(ALL_M), 12)
        for p in ("tests/v2_history/test_h01_x.py", "tests/v2_history_restore/test_r4_01_point_ops.py",
                  "tests/v2_history_ops/test_b02_api1_regression.py", "tests/v2_history_restore/r4_helpers.py",
                  "v2_history/common.py", "v2_history/validate.py", "v2_history/migration.py", "v2_history_ops/plan.py",
                  "v2_history_restore/build.py", "v2_history_restore/values.py", "v2_history_diagnose/describe.py",
                  "tests/v2_history_diagnose/d5_helpers.py", "v2_history_adopt/build.py", RESULT_DOC):
            self.assertFalse(modified_ok(p), p)

    def test_the_new_packages_check_is_exact_about_the_view_file_and_the_kind_file(self):
        # the checker lives inside view.py: v2_history gets no new file (its file list is pinned by h14)
        self.assertFalse(allowed_new_path("v2_history/adoption.py"))
        self.assertFalse(allowed_new_path("v2_history/adopt.py"))
        self.assertTrue(modified_ok("v2_history/view.py"))


def git_show_at_end(path):
    """The text of a file at END (the frozen range is read from Git, never from the working tree)."""
    out = subprocess.run(("git", "-C", ROOT, "show", "%s:%s" % (END, path)), capture_output=True, text=True,
                         timeout=60)
    return out.stdout


class FilesChanged(unittest.TestCase):
    """Compared with the code start by git (committed state)."""

    def setUp(self):
        probe = git("cat-file", "-e", START + "^{commit}")
        if probe.returncode == 0:
            probe = git("cat-file", "-e", END + "^{commit}")
        if probe.returncode != 0:
            self.skipTest("the code start commit is not available in this checkout")

    def changed(self):
        out = git("diff", "--name-status", START, END)
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = [line.split("\t") for line in out.stdout.splitlines()]
        for row in rows:
            self.assertEqual(len(row), 2, row)                      # no rename or copy: a plain A or M
        return rows

    def test_modified_files_are_exactly_the_twelve_and_every_other_change_is_a_new_allowed_file(self):
        rows = self.changed()
        self.assertEqual(sorted(p for s, p in rows if s == "M"), sorted(ALL_M))
        for status, path in rows:
            if status == "M":
                continue
            self.assertEqual(status, "A", "%s %s" % (status, path))                 # no deletion, no mode change
            self.assertTrue(allowed_new_path(path), "unexpected change: %s %s" % (status, path))
        paths = {p for _s, p in rows}
        self.assertEqual({p for p in paths if p.endswith("__init__.py")},
                         {"v2_history_adopt/__init__.py", "v2_history/__init__.py"})
        self.assertEqual({p for p in paths if p.startswith("v2_history_adopt/")},
                         {"v2_history_adopt/" + f for f in NEW_FILES})
        self.assertFalse([p for p in paths if "__pycache__" in p or p.endswith((".pyc", ".pyo"))])
        added_tests = {p for s, p in rows if s == "A" and p.startswith("tests/v2_history_adopt/")}
        self.assertIn("tests/v2_history_adopt/a5_helpers.py", added_tests)
        self.assertEqual({p for p in added_tests if not p.endswith(("a5_helpers.py", "a5_sensitivity.py"))} -
                         {p for p in added_tests if os.path.basename(p).startswith("test_a5_")}, set())

    def test_everything_else_is_identical_to_the_code_start(self):
        out = git("diff", "--name-only", START, END, "--", *UNCHANGED_ROOTS)
        self.assertEqual(out.stdout.strip(), "")
        for root, kept in (("v2_history", RUNTIME_M), ("v2_history_ops", RUNTIME_M), ("v2_history_restore", RUNTIME_M)):
            out = git("diff", "--name-only", START, END, "--", root, *[":(exclude)%s" % p for p in kept])
            self.assertEqual(out.stdout.strip(), "", root)
        out = git("diff", "--name-only", START, END, "--", "tests", ":(exclude)tests/v2_history_adopt",
                  *[":(exclude)%s" % p for p in TEST_M])
        self.assertEqual(out.stdout.strip(), "")
        out = git("diff", "--name-only", START, END, "--", "docs", ":(exclude)%s" % RESULT_DOC)
        self.assertEqual(out.stdout.strip(), "")

    def test_the_other_files_of_the_older_stages_are_blob_identical_to_the_code_start(self):
        listing = git("ls-tree", "-r", START, "--", "v2_core", "v2_persistence", "v2_recovery", "v2_history",
                      "v2_history_ops", "v2_history_restart", "v2_history_restore", "v2_history_diagnose", "tests",
                      "docs/implementation", "docs/STATUS.md", "docs/ROADMAP.md", "docs/MODEL_POLICY.md", "main.py")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        rows = [line.split() for line in listing.stdout.splitlines()]
        self.assertGreater(len(rows), 150)
        changed = set(ALL_M)
        compared = 0
        for _mode, kind, blob, path in rows:
            self.assertEqual(kind, "blob")
            here = subprocess.run(("git", "-C", ROOT, "rev-parse", END + ":" + path), capture_output=True, text=True, timeout=60)
            if path in changed:
                self.assertNotEqual(here.stdout.strip(), blob, path)        # exactly these twelve differ
                continue
            compared += 1
            self.assertEqual(here.stdout.strip(), blob, path)
        self.assertGreater(compared, 150)

    def test_the_results_of_the_older_stages_are_not_appended_to(self):
        for name in ("V2_RECOVERY_S3B2_RESULT.md", "V2_RECOVERY_S3B3_RESULT.md", "V2_RECOVERY_S3B4_RESULT.md",
                     "V2_RECOVERY_S3B5_RESULT.md"):
            out = git("diff", "--name-only", START, END, "--", "docs/implementation/" + name)
            self.assertEqual(out.stdout.strip(), "", name)

    def diff_lines(self, path):
        out = git("diff", "-U0", START, END, "--", path)
        lines = out.stdout.splitlines()
        removed = [l[1:] for l in lines if l.startswith("-") and not l.startswith("---")]
        added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
        hunks = [l.split(" @@")[0] for l in lines if l.startswith("@@")]
        return removed, added, hunks

    def test_the_six_runtime_files_differ_in_exactly_the_pinned_lines(self):
        for path in RUNTIME_M:
            removed, added, hunks = self.diff_lines(path)
            want_removed, want_added, want_hunks = PINNED_RUNTIME[path]
            self.assertEqual(removed, want_removed, path)
            self.assertEqual(added, want_added, path)
            self.assertEqual(hunks, want_hunks, path)

    def test_the_six_tests_differ_in_exactly_the_pinned_lines(self):
        for path in TEST_M:
            removed, added, hunks = self.diff_lines(path)
            want_removed, want_added, want_hunks = PINNED_TESTS[path]
            self.assertEqual(removed, want_removed, path)
            self.assertEqual(added, want_added, path)
            self.assertEqual(hunks, want_hunks, path)

    def test_no_assert_is_removed_no_test_is_skipped_and_the_test_functions_are_the_same(self):
        for path in TEST_M:
            old, new = start_text(path), current_text(path)
            names = lambda text: [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef)]  # noqa: E731
            self.assertEqual(names(old), names(new), path)
            self.assertEqual(assert_calls(new), assert_calls(old), path)
            for word in ("skip", "expectedFailure", "@unittest", "pass\n", "return\n"):
                self.assertEqual(new.count(word), old.count(word), "%s: %r" % (path, word))
            self.assertEqual(new.count("START"), old.count("START"), path)
            self.assertEqual(new.count('"HEAD"'), old.count('"HEAD"'), path)
            for line in old.splitlines():
                if line.startswith("START = "):
                    self.assertIn(line, new.splitlines(), path)             # the code start of the old range is kept
            self.assertEqual(len(re.findall(r"^class ", old, re.M)), len(re.findall(r"^class ", new, re.M)), path)

    def lines_changed_in_new(self, path):
        out = git("diff", "-U0", START, END, "--", path)
        result = []
        for line in out.stdout.splitlines():
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                first = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                result.extend(range(first, first + count))
        return result

    def spans(self, path):
        tree = ast.parse(current_text(path))
        funcs, assigns = {}, {}
        counts = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                counts[node.name] = counts.get(node.name, 0) + 1
                funcs[node.name] = (node.lineno, node.end_lineno)
        for kind, name in PLACES[path]:
            if kind == FUNC:
                self.assertEqual(counts.get(name), 1, "%s: %s must be defined exactly once" % (path, name))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                assigns[node.targets[0].id] = (node.lineno, node.end_lineno)
        return funcs, assigns

    def test_each_edit_lies_in_the_allowed_places(self):
        for path in TEST_M:
            funcs, assigns = self.spans(path)
            spans = []
            for kind, name in PLACES[path]:
                table = funcs if kind == FUNC else assigns
                self.assertIn(name, table, "%s: %s" % (path, name))
                spans.append(table[name])
            changed = self.lines_changed_in_new(path)
            self.assertTrue(changed, path)
            for ln in changed:
                self.assertTrue(any(a <= ln <= b for a, b in spans), "%s: line %d is outside the allowed places" % (path, ln))
            # every allowed place is really used (the list is not wider than the change)
            for (kind, name), (a, b) in zip(PLACES[path], spans):
                self.assertTrue(any(a <= ln <= b for ln in changed), "%s: %s is not changed" % (path, name))

    def test_the_path_judgements_of_the_older_range_tests_are_untouched(self):
        def source_of(text, name):
            for node in ast.parse(text).body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                    return ast.get_source_segment(text, node)
            return None
        for path, names in UNTOUCHED.items():
            old, new = start_text(path), current_text(path)
            for name in names:
                self.assertIsNotNone(source_of(old, name), "%s %s" % (path, name))
                self.assertEqual(source_of(old, name), source_of(new, name), "%s %s" % (path, name))

    def test_the_file_list_of_the_b1_package_is_not_widened(self):
        names = sorted(os.path.basename(p) for p in git("ls-tree", "--name-only", END, "v2_history/").stdout.split()
                       if p.endswith(".py"))
        out = git("ls-tree", "--name-only", START, "v2_history/")
        before = sorted(os.path.basename(p) for p in out.stdout.split() if p.endswith(".py"))
        self.assertEqual(names, before)


if __name__ == "__main__":
    unittest.main()
