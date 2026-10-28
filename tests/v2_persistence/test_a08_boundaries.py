"""A-08: no communication / clock / file / notification / credential path in the new code, error table of the design
(section 9), delegation to evaluate_day, no conversion of core errors into NO_SIGNAL.

The static scan looks at imports and calls in v2_persistence/*.py; the runtime check runs a full scenario with
builtins.open and the time functions disabled. Both are limited checks, reported as such in the result document.
"""
import ast
import builtins
import dataclasses
import os
import time
import unittest
from datetime import timedelta
from unittest import mock

import p_helpers as h
from v2_core import engine as core_engine
from v2_core.errors import ConflictError, CoreError, InputError
from v2_persistence import runner
from v2_persistence.codec import Snapshot
from v2_persistence.errors import PersistenceError
from v2_persistence.recompute import validate_snapshot
from v2_persistence.store import MemoryStore, reconcile

D = h.DATES
PACKAGE = os.path.join(h.ROOT, "v2_persistence")

ALLOWED_IMPORTS = {"copy", "hashlib", "json", "math", "threading", "dataclasses", "typing", "datetime"}
FORBIDDEN_NAMES = {"socket", "ssl", "http", "urllib", "requests", "smtplib", "ftplib", "asyncio", "subprocess",
                   "os", "sys", "pathlib", "shutil", "tempfile", "glob", "io", "time", "sched", "random", "secrets",
                   "getpass", "keyring", "multiprocessing", "sqlite3", "pickle", "logging", "webbrowser", "email"}
FORBIDDEN_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "print"}
FORBIDDEN_ATTRS = {"now", "utcnow", "today", "fromtimestamp", "environ", "getenv", "system", "popen"}


def package_files():
    return sorted(os.path.join(PACKAGE, f) for f in os.listdir(PACKAGE) if f.endswith(".py"))


def parse(path):
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), path)


class StaticScan(unittest.TestCase):
    def test_package_files_are_the_documented_set(self):
        names = [os.path.basename(p) for p in package_files()]
        self.assertEqual(names, ["__init__.py", "codec.py", "errors.py", "events.py", "plan.py", "recompute.py",
                                 "runner.py", "store.py"])

    def test_imports_are_standard_library_or_v2_core_or_relative(self):
        for path in package_files():
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                for root in roots:
                    self.assertNotIn(root, FORBIDDEN_NAMES, (path, root))
                    self.assertTrue(root in ALLOWED_IMPORTS or root == "v2_core", (path, root))

    def test_only_timezone_is_taken_from_datetime_and_nothing_reads_a_clock(self):
        for path in package_files():
            tree = parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                    self.assertEqual([a.name for a in node.names], ["timezone"], path)
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name):
                        self.assertNotIn(fn.id, FORBIDDEN_CALLS, (path, fn.id))
                    if isinstance(fn, ast.Attribute):
                        self.assertNotIn(fn.attr, FORBIDDEN_ATTRS, (path, fn.attr))
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, FORBIDDEN_ATTRS, (path, node.attr))

    def test_no_url_credential_or_path_words_in_identifiers_or_string_values(self):
        for path in package_files():
            tree = parse(path)
            docstrings = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body \
                        and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    docstrings.add(id(node.body[0].value))
            words = ("http", "webhook", "token", "password", "secret", "credential", "discord", "/home/", "c:\\",
                     "notify", "outbox")
            for node in ast.walk(tree):
                texts = []
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    texts.append(node.value)
                if isinstance(node, ast.Name):
                    texts.append(node.id)
                if isinstance(node, ast.Attribute):
                    texts.append(node.attr)
                if isinstance(node, ast.FunctionDef):
                    texts.append(node.name)
                for t in texts:
                    for word in words:
                        self.assertNotIn(word, t.lower(), (path, getattr(node, "lineno", 0), word))

    def test_no_second_copy_of_the_rule_thresholds_or_conditions(self):
        for path in package_files():
            tree = parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                    self.assertNotIn(node.value, (25, 30, 55, 25.0, 30.0, 55.0), (path, node.lineno))
                if isinstance(node, ast.FunctionDef):
                    self.assertFalse(node.name.startswith("market_side"), (path, node.name))
                    self.assertNotIn(node.name, ("tri_and", "from_bool", "apply_transition", "evaluate_day"))
                if isinstance(node, ast.ImportFrom) and node.module in ("v2_core.tri", "v2_core.indicators"):
                    self.fail((path, node.module))

    def test_new_package_does_not_write_into_v2_core_modules(self):
        for path in package_files():
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                            self.assertNotIn(target.value.id, ("engine", "transition", "state", "observations"))


class RuntimeIsolation(unittest.TestCase):
    def test_full_scenario_without_file_access_or_clock(self):
        def no_open(*a, **k):
            raise AssertionError("file access attempted")

        def no_clock(*a, **k):
            raise AssertionError("clock read attempted")
        w = h.World()
        with mock.patch.object(builtins, "open", no_open), mock.patch.object(time, "time", no_clock), \
                mock.patch.object(time, "monotonic", no_clock), mock.patch.object(time, "sleep", no_clock):
            w.apply(D[1], 27.0)
            w.apply(D[4], 40.0)
            w.prepare(D[4])
            plan = w.apply(D[5], 41.0).plan
            reconcile(plan, w.store.read())
            from v2_persistence.codec import decode_snapshot, encode_snapshot
            validate_snapshot(decode_snapshot(encode_snapshot(w.snap())))
        self.assertEqual(w.snap().head_seq, 3)


class TestProcessHasNoNetwork(unittest.TestCase):
    def test_sockets_cannot_be_created_in_the_test_process(self):
        import socket
        with self.assertRaises(RuntimeError):
            socket.socket()
        with self.assertRaises(RuntimeError):
            socket.create_connection(("127.0.0.1", 9))


class DelegationAndCoreErrors(unittest.TestCase):
    def test_prepare_day_calls_evaluate_day_once_per_run(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        calls = []
        real = core_engine.evaluate_day

        def spy(*a, **k):
            calls.append(a[1])
            return real(*a, **k)
        with mock.patch.object(runner, "evaluate_day", spy):
            w.prepare(D[1])
            w.prepare(D[1])
        self.assertEqual(calls, [D[1], D[1]])

    def test_core_errors_are_raised_as_they_are_never_turned_into_no_signal_or_no_commit(self):
        w = h.World()
        base = h.obs("R1", D[1], 27.0)
        for bad, expected in ((dict(base, record_id="a b"), InputError), (dict(base, observation_role="x"), InputError),
                              (dict(base, observation_status="x"), InputError)):
            w.ledger[:] = [bad]
            with self.assertRaises(expected):
                w.prepare(D[1])
        w.ledger[:] = [h.obs("A", D[1], 27.0), h.obs("B", D[1], 28.0)]
        with self.assertRaises(ConflictError) as cm:
            w.prepare(D[1])
        self.assertEqual(cm.exception.code, "decision_conflict")
        self.assertEqual(w.snap().head_seq, 0)

    def test_evaluate_day_error_after_the_ledger_checks_keeps_its_code(self):
        w = h.World()
        w.ledger.append(h.obs("R1", D[1], 27.0))
        series = h.make_series()
        series.rows[D[1]] = series.rows[D[1]].__class__(D[1], 110.0, 100.0, 50.0, -1.0, 49.0)
        series.rows.pop(D[0])
        series.dates = sorted(series.rows)
        w.series = series
        with self.assertRaises(CoreError) as cm:
            w.prepare(D[1])
        self.assertEqual(cm.exception.code, "session_series_mismatch")


class ErrorTable(unittest.TestCase):
    """Every row of the design's error table (section 9) that a call can produce, with its code and field."""

    def case(self, label, make, code, field, cls=CoreError):
        with self.assertRaises(cls, msg=label) as cm:
            make()
        self.assertEqual((cm.exception.code, cm.exception.field), (code, field), label)

    def applied(self, upto=(1, 4)):
        w = h.World()
        for i in upto:
            w.apply(D[i], 27.0 + i)
        return w

    def test_table(self):
        sessions = h.make_sessions()
        w = self.applied()
        base_rows = list(w.ledger)

        def with_rows(*extra):
            w.ledger[:] = base_rows + list(extra)
            return w

        self.case("unsupported version", lambda: validate_snapshot(Snapshot.from_dict(dict(w.snap().to_dict(), schema_version=2))),
                  "unsupported_schema", "schema_version")
        self.case("unsupported core_sha", lambda: validate_snapshot(Snapshot.from_dict(dict(w.snap().to_dict(), core_sha="0" * 40))),
                  "unsupported_schema", "core_sha")
        self.case("unsupported event", lambda: validate_snapshot(h.tampered(w.snap(), lambda e: e[1].__setitem__("kind", "ACK"), False)),
                  "unsupported_event", "kind")
        self.case("snapshot invalid", lambda: validate_snapshot(h.tampered(w.snap(), lambda e: e[1].__setitem__("seq", 9))),
                  "snapshot_invalid", "snapshot")
        self.case("invalid start_after", lambda: runner.make_genesis("2026-02-30", sessions), "invalid_date", "start_after")
        self.case("boundary missing", lambda: runner.make_genesis("2026-03-07", sessions), "genesis_boundary_missing", "start_after")
        self.case("boundary unconfirmed", lambda: runner.make_genesis(D[1], h.make_sessions(unconfirmed=(D[1],))),
                  "genesis_boundary_unconfirmed", "start_after")
        self.case("target before genesis", lambda: w.prepare(D[0]), "target_not_after_genesis", "target_session_date")
        self.case("state ahead", lambda: w.prepare(D[2]), "state_ahead_of_target", "state")
        self.case("target not in sessions", lambda: w.prepare("2026-03-07"), "target_not_in_sessions", "sessions")
        self.case("target unconfirmed", lambda: h.prepare_day(w.snap(), D[5], w.series, h.make_sessions(unconfirmed=(D[5],)), w.ledger),
                  "target_unconfirmed", "sessions")
        self.case("next missing", lambda: h.prepare_day(w.snap(), D[-1], w.series, w.sessions, w.ledger),
                  "next_session_missing", "sessions")
        self.case("previous missing", lambda: h.prepare_day(h.World().snap(), D[1], w.series, h.make_sessions(D[1:]), []),
                  "previous_session_missing", "sessions")
        self.case("context missing", lambda: h.prepare_day(w.snap(), D[6], w.series, h.make_sessions([d for d in D if d != D[2]]), w.ledger),
                  "session_context_missing", "sessions")
        self.case("intermediate unconfirmed",
                  lambda: h.prepare_day(w.snap(), D[7], w.series, h.make_sessions(unconfirmed=(D[6],)), with_rows(h.obs("N", D[7], 30.0)).ledger),
                  "intermediate_session_unconfirmed", "sessions")
        shifted = h.make_sessions(overrides={D[1]: lambda s: dataclasses.replace(s, close_at=s.close_at + timedelta(minutes=5))})
        self.case("context mismatch", lambda: h.prepare_day(w.snap(), D[6], w.series, shifted, w.ledger),
                  "session_context_mismatch", "sessions")
        self.case("ledger mismatch", lambda: h.prepare_day(w.snap(), D[6], w.series, w.sessions, base_rows[1:]),
                  "ledger_mismatch", "observations")
        self.case("late observation", lambda: w.prepare(D[6]) if with_rows(h.obs("L", D[2], 31.0)) else None,
                  "late_observation", "observations")
        self.case("intermediate unprocessed", lambda: w.prepare(D[7]) if with_rows(h.obs("M", D[6], 31.0), h.obs("T", D[7], 30.0)) else None,
                  "intermediate_session_unprocessed", "observations")
        self.case("core code kept (conflict)", lambda: w.prepare(D[5]) if with_rows(h.obs("A", D[5], 31.0), h.obs("B", D[5], 32.0)) else None,
                  "decision_conflict", "observation_role")
        self.case("core code kept (record id)", lambda: w.prepare(D[5]) if with_rows(h.obs("A", D[5], 31.0), h.obs("A", D[5], 32.0)) else None,
                  "record_id_conflict", "record_id")
        base = list(base_rows)
        w.ledger[:] = base
        self.case("recompute mismatch", lambda: h.prepare_day(w.snap(), D[4], h.make_series(per_date={D[4]: dict(soxx=111.0)}), w.sessions, base),
                  "recompute_mismatch", "confirmed_inputs")
        self.case("store uninitialized", MemoryStore().read, "store_uninitialized", "store")
        self.case("already initialized", lambda: w.store.initialize(h.make_genesis(D[0], sessions)), "already_initialized", "store")
        head = h.World()
        plan_a = h.prepare_day(head.snap(), D[1], head.series, head.sessions, [h.obs("R1", D[1], 27.0)]).plan
        plan_b = h.prepare_day(head.snap(), D[1], head.series, head.sessions, [h.obs("R1", D[1], 27.5)]).plan
        head.store.commit(plan_a)
        self.case("cas conflict", lambda: head.store.commit(plan_b), "cas_conflict", "head")
        self.case("concurrent conflict", lambda: reconcile(plan_b, head.store.read()), "concurrent_conflict", "events")
        self.assertEqual(reconcile(h.prepare_day(h.World().snap(), D[2], head.series, head.sessions, [h.obs("R2", D[2], 28.0)]).plan,
                                   head.store.read()).status, "REPLAN_REQUIRED")

    def test_priority_session_check_before_ledger_selection_and_snapshot_before_everything(self):
        w = self.applied()
        shifted = h.make_sessions(overrides={D[1]: lambda s: dataclasses.replace(
            s, open_at=s.open_at.replace(hour=8))})
        w.ledger.append(h.obs("ADD", D[4], 9.0))                      # a ledger conflict, too
        with self.assertRaises(PersistenceError) as cm:
            h.prepare_day(w.snap(), D[4], w.series, shifted, w.ledger)
        self.assertEqual(cm.exception.code, "session_context_mismatch")
        broken = h.tampered(w.snap(), lambda e: e[1].__setitem__("seq", 9))
        with self.assertRaises(PersistenceError) as cm:
            h.prepare_day(broken, "2026-02-30", w.series, shifted, w.ledger)       # snapshot error wins over a bad D
        self.assertEqual(cm.exception.code, "snapshot_invalid")

    def test_applied_days_are_checked_before_skipped_sessions_before_the_new_span(self):
        w = self.applied()                                            # D1, D4 applied; D2, D3 skipped
        # one row of each kind: a changed applied decision, a late row for a skipped day, a decision in the new span
        late = h.obs("L", D[2], 31.0)
        mid = h.obs("M", D[6], 31.0)
        first, second = w.ledger
        w.ledger[:] = [dict(first, current_fg_value=1.0), second, late, mid, h.obs("T", D[7], 30.0)]
        self.assertEqual(self._code(w, D[7]), "ledger_mismatch")
        w.ledger[:] = [first, second, late, mid, h.obs("T", D[7], 30.0)]
        self.assertEqual(self._code(w, D[7]), "late_observation")
        w.ledger[:] = [first, second, mid, h.obs("T", D[7], 30.0)]
        self.assertEqual(self._code(w, D[7]), "intermediate_session_unprocessed")

    @staticmethod
    def _code(w, d):
        try:
            w.prepare(d)
        except CoreError as e:
            return e.code
        return None


if __name__ == "__main__":
    unittest.main()
