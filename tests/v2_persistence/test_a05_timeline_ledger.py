"""A-05: order of days, intermediate sessions (N-01 / Q-01), ledger checks against what was stored, stored sessions."""
import dataclasses
import unittest
from datetime import datetime, timedelta

import p_helpers as h
from v2_core.errors import ConflictError, InputError
from v2_persistence.errors import PersistenceError

D = h.DATES
ERRORS = (PersistenceError, InputError, ConflictError)


def err(case, fn, *a, **k):
    with case.assertRaises(ERRORS) as cm:
        fn(*a, **k)
    return cm.exception


def at(d, hh, mm=0, tz=h.TZ):
    y, m, dd = (int(x) for x in d.split("-"))
    return datetime(y, m, dd, hh, mm, tzinfo=tz).isoformat()


def raw(record_id, target, value, observed_at, role="decision"):
    return {"record_id": record_id, "observation_status": "observed", "observation_role": role,
            "current_fg_value": value, "observed_at_iso8601": observed_at, "target_us_session_date": target}


class Unchanged(object):
    """Snapshot and head are exactly as before after a refused operation."""

    def check(self, w, before):
        after = w.snap()
        self.assertEqual(after, before)
        self.assertEqual((after.head_seq, after.head_hash), (before.head_seq, before.head_hash))


class OrderOfDays(Unchanged, unittest.TestCase):
    def test_boundary_and_past_days_are_refused(self):
        w = h.World(start_idx=2)
        w.apply(D[3], 27.0)
        w.apply(D[5], 40.0)
        before = w.snap()
        applied_rows = list(w.ledger)
        for d, code in ((D[2], "target_not_after_genesis"), (D[0], "target_not_after_genesis"),
                        (D[4], "state_ahead_of_target")):
            w.ledger.append(h.obs("X" + d, d, 30.0))
            e = err(self, w.prepare, d)
            self.assertEqual(e.code, code, d)
            self.check(w, before)
        w.ledger[:] = applied_rows
        self.assertEqual(w.prepare(D[5]).status, "ALREADY_APPLIED")

    def test_invalid_or_unknown_day(self):
        w = h.World()
        before = w.snap()
        for d, code in (("2026-02-30", "invalid_date"), (None, "invalid_date"), ("2026-03-07", "target_not_in_sessions"),
                        (D[-1], "next_session_missing")):
            e = err(self, w.prepare, d)
            self.assertEqual(e.code, code, d)
        w.sessions = h.make_sessions(unconfirmed=(D[1],))
        self.assertEqual(err(self, w.prepare, D[1]).code, "target_unconfirmed")
        self.check(w, before)

    def test_previous_session_missing(self):
        # the first session of a list has no previous session; with a boundary it cannot be a valid D anyway
        w = h.World()
        w.sessions = h.make_sessions(D[1:])
        self.assertEqual(err(self, w.prepare, D[1]).code, "previous_session_missing")        # the core's own code
        w.sessions = h.make_sessions(D[2:])                          # the boundary D0 is not in the list at all
        w.ledger.append(h.obs("R", D[3], 27.0))
        e = err(self, w.prepare, D[3])
        self.assertEqual((e.code, e.field), ("session_context_missing", "sessions"))


class IntermediateSessions(Unchanged, unittest.TestCase):
    """New D: every session strictly between the base boundary B and D needs confirmed=true."""

    def scenario(self, applied_first):
        w = h.World(unconfirmed=(D[3],) if applied_first else (D[2],))
        if applied_first:
            w.apply(D[1], 40.0)
        w.ledger.append(h.obs("R-new", D[5], 27.0))
        return w

    def test_unconfirmed_intermediate_session_stops_before_any_plan(self):
        for applied_first in (False, True):
            w = self.scenario(applied_first)
            before = w.snap()
            bad = D[3] if applied_first else D[2]
            e = err(self, w.prepare, D[5])
            self.assertEqual((e.code, e.field, e.detail), ("intermediate_session_unconfirmed", "sessions", bad))
            self.check(w, before)
            self.assertEqual(before.head_seq, 1 if applied_first else 0)

    def test_it_applies_to_days_without_a_decision_and_when_the_result_would_be_no_commit(self):
        for applied_first in (False, True):
            w = self.scenario(applied_first)
            w.ledger.clear()                                   # no decision at all for D
            e = err(self, w.prepare, D[5])
            self.assertEqual(e.code, "intermediate_session_unconfirmed")

    def test_confirming_the_session_lets_the_same_input_be_prepared_committed_and_rerun(self):
        for applied_first in (False, True):
            w = self.scenario(applied_first)
            err(self, w.prepare, D[5])
            w.sessions = h.make_sessions()                      # the intermediate session is now confirmed
            res = w.prepare(D[5])
            self.assertEqual(res.status, "PREPARED")
            w.store.commit(res.plan)
            self.assertEqual(w.prepare(D[5]).status, "ALREADY_APPLIED")
            start = 1 if applied_first else 0
            self.assertEqual(w.snap().events[-1]["skipped_sessions"], D[start + 1:5])

    def test_the_next_session_may_be_unconfirmed_and_is_not_an_intermediate_session(self):
        w = h.World(unconfirmed=(D[2],))
        w.ledger.append(h.obs("R", D[1], 27.0))
        res = w.prepare(D[1])                                   # next(D1) = D2 is unconfirmed
        self.assertEqual(res.status, "PREPARED")
        w.store.commit(res.plan)
        self.assertEqual(w.prepare(D[1]).status, "ALREADY_APPLIED")

    def test_the_day_itself_must_be_confirmed(self):
        w = h.World(unconfirmed=(D[1],))
        w.ledger.append(h.obs("R", D[1], 27.0))
        self.assertEqual(err(self, w.prepare, D[1]).code, "target_unconfirmed")


class DecisionsInTheMiddle(Unchanged, unittest.TestCase):
    def worlds(self):
        """(name, world, base boundary, a middle session, the target); w.base_rows are the rows already applied."""
        w = h.World()
        w.base_rows = []
        yield "initial", w, D[0], D[2], D[5]
        w2 = h.World()
        w2.apply(D[1], 40.0)
        w2.base_rows = list(w2.ledger)
        yield "applied", w2, D[1], D[3], D[6]

    def test_a_valid_decision_in_the_middle_stops_the_run(self):
        for name, w, base, mid, target in self.worlds():
            w.ledger[:] = w.base_rows + [h.obs("MID", mid, 27.0), h.obs("TGT", target, 27.0)]
            before = w.snap()
            e = err(self, w.prepare, target)
            self.assertEqual((e.code, e.field, e.detail), ("intermediate_session_unprocessed", "observations", mid),
                             name)
            self.check(w, before)

    def test_decision_just_before_close_or_exactly_at_next_open_is_outside_the_window(self):
        for name, w, base, mid, target in self.worlds():
            nxt = D[D.index(mid) + 1]
            for when in (at(mid, 15, 59), at(nxt, 9, 30), at(mid, 9, 31)):
                w.ledger[:] = w.base_rows + [h.obs("TGT", target, 27.0), raw("MID", mid, 20.0, when)]
                before = w.snap()
                e = err(self, w.prepare, target)
                self.assertEqual((e.code, e.field), ("decision_outside_window", "observed_at_iso8601"), (name, when))
                self.check(w, before)
            # exactly at close(S) is inside: it counts as a decision and stops the run differently
            w.ledger[:] = w.base_rows + [h.obs("TGT", target, 27.0), raw("MID", mid, 20.0, at(mid, 16, 0))]
            self.assertEqual(err(self, w.prepare, target).code, "intermediate_session_unprocessed")

    def test_the_whole_span_is_checked_after_a_valid_decision(self):
        for name, w, base, mid, target in self.worlds():
            later = D[D.index(mid) + 1]
            w.ledger[:] = w.base_rows + [h.obs("TGT", target, 27.0), h.obs("MID", mid, 20.0),
                                         raw("LATE", later, 21.0, at(later, 10, 0))]      # bad row after the valid one
            e = err(self, w.prepare, target)
            self.assertEqual(e.code, "decision_outside_window", name)

    def test_wrong_target_conflicting_and_same_id_rows_in_the_middle(self):
        for name, w, base, mid, target in self.worlds():
            tgt = h.obs("TGT", target, 27.0)
            cases = (
                ("target_mismatch", [raw("W", D[D.index(mid) + 3], 20.0, at(mid, 20))]),
                ("decision_conflict", [h.obs("A", mid, 20.0), h.obs("B", mid, 21.0)]),
                ("record_id_conflict", [h.obs("A", mid, 20.0), h.obs("A", mid, 21.0)]),
            )
            for code, rows in cases:
                w.ledger[:] = w.base_rows + [tgt] + rows
                e = err(self, w.prepare, target)
                self.assertEqual(e.code, code, (name, code))
                w.ledger[:] = w.base_rows + [tgt] + list(reversed(rows))                      # the order of rows picks no winner
                self.assertEqual(err(self, w.prepare, target).code, code, (name, code, "reversed"))

    def test_recorded_gap_with_a_clean_ledger_commits(self):
        for name, w, base, mid, target in self.worlds():
            w.ledger[:] = w.base_rows + [h.obs("TGT", target, 27.0)]
            res = w.prepare(target)
            self.assertEqual(res.status, "PREPARED", name)


class StreakAndGap(unittest.TestCase):
    def test_f_and_g_30_or_more_after_a_normal_gap_starts_a_new_streak_of_one(self):
        w = h.World()
        w.apply(D[1], 40.0)
        w.apply(D[2], 41.0)
        w.apply(D[5], 35.0)                                        # D3, D4 skipped
        ev = w.snap().events[3]
        self.assertTrue(ev["transition_result"]["gap"])
        self.assertEqual(ev["state_after"]["streak"], 1)
        self.assertEqual(ev["skipped_sessions"], [D[3], D[4]])

    def test_first_run_after_a_delay_has_no_core_gap_but_records_the_skipped_sessions(self):
        w = h.World()
        w.apply(D[4], 35.0)
        ev = w.snap().events[1]
        self.assertFalse(ev["transition_result"]["gap"])
        self.assertEqual(ev["skipped_sessions"], [D[1], D[2], D[3]])


class LedgerAgainstStoredDays(Unchanged, unittest.TestCase):
    """The single-event table of the request (3.2) for the latest D (re-run) and for a new, later D."""

    def setUp(self):
        self.w = h.World()
        self.w.apply(D[1], 27.0)           # R-D1
        self.w.apply(D[4], 28.0)           # R-D4; D2 and D3 skipped
        self.before = self.w.snap()
        self.orig1 = self.w.ledger[0]
        self.orig4 = self.w.ledger[1]

    def both(self, code, field="observations"):
        """The refusal is the same for the latest D (re-run) and for a newer D, and nothing is stored."""
        if not any(r["record_id"] == "NEW" for r in self.w.ledger):
            self.w.ledger.append(h.obs("NEW", D[5], 29.0))
        for d in (D[4], D[5]):
            e = err(self, self.w.prepare, d)
            self.assertEqual((e.code, e.field), (code, field), d)
            self.check(self.w, self.before)

    def test_applied_decision_removed(self):
        for removed in (0, 1):
            self.w.ledger[:] = [r for i, r in enumerate((self.orig1, self.orig4)) if i != removed]
            self.both("ledger_mismatch")

    def test_applied_decision_replaced_by_other_content_without_the_old_row(self):
        self.w.ledger[:] = [dict(self.orig1, current_fg_value=27.5), self.orig4]
        self.both("ledger_mismatch")
        self.w.ledger[:] = [self.orig1, dict(self.orig4, record_id="R-OTHER")]
        self.both("ledger_mismatch")

    def test_old_and_new_rows_with_the_same_record_id(self):
        self.w.ledger[:] = [self.orig1, self.orig4, dict(self.orig1, current_fg_value=27.5)]
        self.both("record_id_conflict", "record_id")

    def test_original_kept_and_another_decision_added_for_the_same_day(self):
        self.w.ledger[:] = [self.orig1, self.orig4, h.obs("ADD", D[4], 33.0)]
        self.both("decision_conflict", "observation_role")
        self.w.ledger[:] = [self.orig1, self.orig4, h.obs("ADD", D[1], 33.0)]
        self.both("decision_conflict", "observation_role")

    def test_a_decision_for_the_day_outside_its_window(self):
        self.w.ledger[:] = [self.orig1, self.orig4, raw("OUT", D[1], 22.0, at(D[1], 12, 0))]
        self.both("decision_outside_window", "observed_at_iso8601")

    def test_a_decision_for_another_day_inside_the_window(self):
        self.w.ledger[:] = [self.orig1, self.orig4, raw("WRONG", D[9], 22.0, at(D[4], 20, 0))]
        self.both("target_mismatch", "target_us_session_date")

    def test_a_late_decision_for_a_recorded_gap(self):
        for skipped in (D[2], D[3]):
            self.w.ledger[:] = [self.orig1, self.orig4, h.obs("LATE", skipped, 31.0)]
            self.both("late_observation")
            self.assertEqual(err(self, self.w.prepare, D[5]).detail, skipped)

    def test_a_new_decision_in_the_new_span_stops_a_later_new_day(self):
        self.w.ledger[:] = [self.orig1, self.orig4, h.obs("MID", D[5], 31.0), h.obs("TGT", D[7], 31.0)]
        before = self.w.snap()
        e = err(self, self.w.prepare, D[7])
        self.assertEqual((e.code, e.field, e.detail), ("intermediate_session_unprocessed", "observations", D[5]))
        self.check(self.w, before)

    def test_row_order_never_selects_a_winner(self):
        rows = [self.orig1, self.orig4, h.obs("ADD", D[4], 33.0)]
        for order in (rows, list(reversed(rows)), [rows[1], rows[2], rows[0]]):
            self.w.ledger[:] = order
            self.assertEqual(err(self, self.w.prepare, D[4]).code, "decision_conflict")
        self.w.ledger[:] = [self.orig4, self.orig1]                     # same rows, other order: still the same day
        self.assertEqual(self.w.prepare(D[4]).status, "ALREADY_APPLIED")

    def test_unrelated_syntax_errors_in_the_ledger_stop_with_the_core_code(self):
        for bad, code in ((dict(self.orig1, record_id="http://x"), "record_id_invalid"),
                          (dict(self.orig1, observation_role="other"), "role_unknown"),
                          (dict(self.orig1, current_fg_value=True), "fg_value_invalid"),
                          ("not a row", "observation_invalid")):
            self.w.ledger[:] = [self.orig1, self.orig4, bad]
            e = err(self, self.w.prepare, D[4])
            self.assertEqual(e.code, code)
            self.check(self.w, self.before)

    def test_old_rows_before_the_boundary_are_still_syntax_checked(self):
        w = h.World(start_idx=3)
        w.ledger.append(dict(h.obs("OLD", D[0], 30.0), record_id="bad id"))
        w.ledger.append(h.obs("R", D[4], 27.0))
        self.assertEqual(err(self, w.prepare, D[4]).code, "record_id_invalid")


class StoredSessionRanges(Unchanged, unittest.TestCase):
    def setUp(self):
        self.w = h.World()
        self.w.apply(D[1], 27.0)
        self.w.apply(D[5], 40.0)                  # D2..D4 skipped
        self.w.ledger.append(h.obs("NEW", D[7], 41.0))
        self.before = self.w.snap()

    def test_missing_sessions_in_a_saved_range(self):
        for gone in (D[0], D[2], D[3], D[6]):
            self.w.sessions = h.make_sessions([d for d in D if d != gone])
            e = err(self, self.w.prepare, D[7])
            self.assertEqual((e.code, e.field), ("session_context_missing", "sessions"), gone)
            self.check(self.w, self.before)

    def test_sessions_that_stop_before_the_saved_range(self):
        self.w.sessions = h.make_sessions(D[:6])
        self.assertEqual(err(self, self.w.prepare, D[5]).code, "next_session_missing")
        self.w.sessions = h.make_sessions(D[:7])
        self.assertEqual(err(self, self.w.prepare, D[7]).code, "target_not_in_sessions")

    def test_changed_times_in_the_range_of_an_older_day(self):
        def shift(field):
            return lambda s: dataclasses.replace(s, **{field: getattr(s, field) + timedelta(minutes=10)})
        # the boundary day belongs only to the first saved day's range
        self.w.sessions = h.make_sessions(overrides={D[0]: shift("open_at")})
        e = err(self, self.w.prepare, D[7])
        self.assertEqual((e.code, e.field, e.detail), ("session_context_mismatch", "sessions", D[1]))
        # a skipped session inside the second range
        self.w.sessions = h.make_sessions(overrides={D[3]: shift("close_at")})
        e = err(self, self.w.prepare, D[7])
        self.assertEqual((e.code, e.detail), ("session_context_mismatch", D[5]))
        # unconfirmed in a saved range counts, too
        self.w.sessions = h.make_sessions(unconfirmed=(D[2],))
        self.assertEqual(err(self, self.w.prepare, D[7]).code, "session_context_mismatch")
        self.check(self.w, self.before)

    def test_the_same_revision_stops_the_latest_day_too_and_before_ledger_selection(self):
        shift = lambda s: dataclasses.replace(s, close_at=s.close_at + timedelta(minutes=10))
        self.w.sessions = h.make_sessions(overrides={D[5]: shift})
        self.w.ledger[:] = [self.w.ledger[0], self.w.ledger[1], h.obs("ADD", D[5], 12.0)]     # a ledger conflict, too
        e = err(self, self.w.prepare, D[5])
        self.assertEqual(e.code, "session_context_mismatch")        # the session check comes first

    def test_next_day_close_at_and_confirmed_are_excluded_per_stored_day(self):
        w = h.World()
        w.apply(D[1], 27.0)
        w.apply(D[2], 40.0)                                         # D2 is next(D1) and a day in its own right
        w.ledger.append(h.obs("NEW", D[3], 41.0))
        before = w.snap()
        # D2's close_at is outside D1's comparison but inside D2's: the stop names D2
        w.sessions = h.make_sessions(overrides={D[2]: lambda s: dataclasses.replace(
            s, close_at=s.close_at + timedelta(minutes=30))})
        e = err(self, w.prepare, D[3])
        self.assertEqual((e.code, e.detail), ("session_context_mismatch", D[2]))
        # D3 is next(D2): its close_at / confirmed are free, while D3 as the new target must be confirmed
        w.sessions = h.make_sessions(overrides={D[3]: lambda s: dataclasses.replace(
            s, close_at=s.close_at + timedelta(minutes=30))})
        self.assertEqual(w.prepare(D[3]).status, "PREPARED")
        self.check(w, before)


if __name__ == "__main__":
    unittest.main()
