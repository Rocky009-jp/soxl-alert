"""S4A-10 (input errors), S4A-11 (store stops, real C-3) and S4A-17 (the start after a re-initialisation)."""
import os
import unittest

import s4a_helpers as S
import v2_daily_run as R
from v2_core.display import render_message

D, P, O, H, C2 = S.D, S.P, S.O, S.H, S.C2


class InputErrors(S.RootCase):
    def stopped(self, report, code, saved, through=None):
        """saved: the days this run saved; through: the index of the last day the file holds (default: the last saved)."""
        self.assertEqual((report.outcome, report.exit_code, report.code), ("STOPPED", 1, code))
        self.assertEqual([c.d for c in report.consumed], [D[i] for i in saved])
        self.assertIsNone(report.target_status)
        through = (max(saved) if saved else 0) if through is None else through
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, through, ledger=self.good))
        for forbidden in ("b*", "分岐", "市場側"):
            self.assertNotIn(forbidden, report.message)
        self.assertIn(code, report.message)

    def test_a_changed_value_of_a_saved_decision_stops_the_run_at_once_and_writes_nothing(self):
        S.decide(self.w, [1, 2])
        store = self.store()
        S.run(store, self.w, S.now_at(D[3]))
        self.good = list(self.w.ledger)
        before = S.state_of(self.root)
        tampered = [P.obs("R1", D[1], 35.0), self.w.ledger[1], P.obs("R3", D[3], 22.0)]
        report = S.run(store, self.w, S.now_at(D[4]), ledger=tampered)
        self.stopped(report, "ledger_mismatch", [], through=2)
        self.assertEqual(S.state_of(self.root), before)

    def test_a_decision_outside_its_window_stops_at_that_day_and_the_days_before_are_saved(self):
        S.decide(self.w, [1, 2])
        self.w.ledger.append(P.obs("R3", D[3], 22.0, hour=10))              # before D3 closed
        self.good = [r for r in self.w.ledger if r["record_id"] != "R3"]
        report = S.run(self.store(), self.w, S.now_at(D[4]))
        self.stopped(report, "decision_outside_window", [1, 2])

    def test_a_missing_market_row_stops_at_that_day(self):
        S.decide(self.w, [1, 2, 3])
        self.good = list(self.w.ledger)
        series = P.make_series(dates=[d for d in D if d != D[3]])
        report = S.run(self.store(), self.w, S.now_at(D[3]), series=series)
        self.stopped(report, "target_row_missing", [1, 2])

    def test_sessions_that_do_not_match_a_saved_day_stop_before_anything_new_is_written(self):
        S.decide(self.w, [1, 2])
        store = self.store()
        S.run(store, self.w, S.now_at(D[3]))
        self.good = list(self.w.ledger)
        S.decide(self.w, [3])
        without_d2 = P.make_sessions(dates=[d for d in D if d != D[2]])       # D2's saved context is no longer there
        report = S.run(store, self.w, S.now_at(D[4]), sessions=without_d2)
        self.assertEqual((report.outcome, report.consumed), ("STOPPED", ()))
        self.assertEqual(report.code, "session_context_missing")
        self.assertEqual(S.raw(self.root), S.expected_bytes(self.w, 2, ledger=self.good))

    def test_the_bytes_after_the_stop_are_those_after_the_last_success(self):
        S.decide(self.w, [1, 2, 3, 4])
        self.w.ledger[2] = P.obs("R3", D[3], 22.0, hour=10)                    # D3 is wrong; D4 is fine
        self.good = [r for r in self.w.ledger if r["record_id"] != "R3"]
        report = S.run(self.store(), self.w, S.now_at(D[5]))
        self.stopped(report, "decision_outside_window", [1, 2])
        self.assertEqual(S.applies_of(self.root), [D[1], D[2]])


class StoreStops(S.RootCase):
    def setUp(self):
        super().setUp()
        S.decide(self.w, [1, 2])

    def stopped(self, report, code):
        self.assertEqual((report.outcome, report.exit_code, report.code), ("STOPPED", 1, code))
        self.assertEqual(report.consumed, ())
        self.assertIn(code, report.message)
        self.assertNotIn(self.root, report.message)
        self.assertNotIn(self.root, repr(report))

    def test_a_leftover_lock_is_store_busy_and_nothing_changes(self):
        store = self.store()
        S.put(self.root, S.LOCK, b"left over")
        before = S.state_of(self.root)
        self.stopped(S.run(store, self.w, S.now_at(D[3])), "store_busy")
        self.assertEqual(S.state_of(self.root), before)

    def test_an_uninitialised_root_is_store_uninitialized_and_nothing_changes(self):
        store = self.store(initialize=False)
        self.stopped(S.run(store, self.w, S.now_at(D[3])), "store_uninitialized")
        self.assertEqual(os.listdir(self.root), [])

    def test_a_read_only_store_stops_at_the_first_publication_and_not_before(self):
        self.store()
        read_only = self.store(writable=False, initialize=False)
        before = S.state_of(self.root)
        self.stopped(S.run(read_only, self.w, S.now_at(D[3])), "store_read_only")
        self.assertEqual(S.state_of(self.root), before)
        other = P.World(0)                                                      # nothing to save: a read-only store is fine
        done = S.run(read_only, other, S.now_at(D[3]))
        self.assertEqual((done.outcome, done.consumed), ("DONE", ()))

    def test_a_v1_snapshot_file_is_store_layout_unsupported_alone_or_next_to_the_history(self):
        store = self.store()
        S.put(self.root, S.V1, b"{}")
        before = S.state_of(self.root)
        self.stopped(S.run(store, self.w, S.now_at(D[3])), "store_layout_unsupported")
        self.assertEqual(S.state_of(self.root), before)
        os.unlink(os.path.join(self.root, S.HIST))
        before = S.state_of(self.root)
        self.stopped(S.run(store, self.w, S.now_at(D[3])), "store_layout_unsupported")
        self.assertEqual(S.state_of(self.root), before)

    def test_a_leftover_temporary_file_is_store_artifact_present_and_nothing_changes(self):
        store = self.store()
        S.put(self.root, ".history." + "0" * 32 + ".tmp", b"partial")
        before = S.state_of(self.root)
        self.stopped(S.run(store, self.w, S.now_at(D[3])), "store_artifact_present")
        self.assertEqual(S.state_of(self.root), before)

    def test_the_runtime_does_not_load_the_maintenance_or_the_local_store_packages(self):
        loaded = S.probe_imports()
        self.assertIn("v2_daily_run", loaded)
        for name in loaded:
            self.assertFalse(name.startswith("v2_history_maintain"), name)
            self.assertFalse(name.startswith("v2_history_local"), name)


class AfterReinitialisation(unittest.TestCase):
    """S4A-17: the start is the effective boundary (processing_after), not the last APPLY of the whole history."""

    def setUp(self):
        import shutil
        self.root = S.make_root()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.b = H.HB()
        self.b.apply(D[1], 27.0)
        self.b.apply(D[2], 28.0)
        self.b.restart(D[3], "q1")                                              # RESTART_UNKNOWN, resume_after = D3
        self.w = self.b.w

    def place(self):
        S.put(self.root, S.HIST, C2.file_bytes(self.b.history()))
        from v2_history_local import HistoryFileStore
        return HistoryFileStore(self.root, writable=True, durability=S.DURABILITY)

    def first_apply_after(self, history, d):
        res = O.prepare_history_day(history, d, self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual(res.status, "PREPARED")
        return res

    def test_the_target_after_a_restart_is_saved_as_the_first_apply_of_the_new_segment(self):
        view = O.read_effective(self.b.history())
        self.assertEqual((view.processing_after, view.latest_apply_d), (D[3], D[2]))
        S.decide(self.w, [4])
        history = self.b.history()
        res = self.first_apply_after(history, D[4])
        expected = O.check_append_batch(history, res.batch)
        report = S.run(self.place(), self.w, S.now_at(D[4]))
        self.assertEqual((report.outcome, report.code), ("DONE", None))
        self.assertEqual([(c.d, c.gap, c.skipped_sessions) for c in report.consumed], [(D[4], False, ())])
        self.assertEqual(report.target_status, "PREPARED")
        self.assertEqual(S.raw(self.root), C2.file_bytes(expected))
        self.assertEqual(report.message, render_message(res.core_result))
        self.assertEqual(O.read_effective(expected).processing_after, D[4])

    def test_the_morning_before_the_first_decision_after_the_restart_waits_and_does_not_stop(self):
        before = S.raw(self.root) if os.path.exists(os.path.join(self.root, S.HIST)) else None
        store = self.place()
        data = S.raw(self.root)
        report = S.run(store, self.w, S.now_at(D[4]))                             # D4 closed, no decision yet
        self.assertEqual((report.outcome, report.target_status, report.consumed), ("DONE", "NO_COMMIT", ()))
        self.assertEqual(S.raw(self.root), data)
        self.assertIsNone(before)

    def test_an_acknowledgement_and_a_declaration_after_the_restart_do_not_move_the_start(self):
        S.decide(self.w, [5])
        self.b.declare(D[4], "q2")                                               # D4 declared missing
        self.assertEqual(O.read_effective(self.b.history()).processing_after, D[3])
        store = self.place()
        report = S.run(store, self.w, S.now_at(D[5]))
        self.assertEqual((report.outcome, report.code), ("DONE", None))
        self.assertEqual([c.d for c in report.consumed], [D[5]])
        self.assertEqual(S.applies_of(self.root)[-1], D[5])
        self.assertEqual(S.applies_of(self.root), [D[1], D[2], D[5]])
        view = O.read_effective(store.read())
        self.assertEqual(view.processing_after, D[5])
        self.assertEqual(view.latest_apply_d, D[5])


if __name__ == "__main__":
    unittest.main()
