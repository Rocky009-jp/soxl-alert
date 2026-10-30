"""H-13: nothing the caller holds is shared with what is returned; nothing printed or raised carries raw rows, F&G
values, URLs, free text or paths."""
import unittest

import h_helpers as H
from h_helpers import D, V

SECRET_ID = "SecretRow-77"
SECRET_VALUE = "77.77"
URL = "https://example.invalid/secret-token-path"
PATH = "/secret/dedicated-path"


def world_with_secrets():
    w = H.P.World()
    w.apply(D[1], 77.77, SECRET_ID)
    w.apply(D[2], 28.0, "R2")
    return w, w.snap(), H.R.empty_resolutions(), list(w.ledger), D[2]


def shown(*things):
    return "\n".join("%s\n%r" % (t, t) for t in things)


class Immutability(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = H.example_m_world()

    def test_prepare_and_confirm_leave_every_input_untouched(self):
        sessions_before = [(s.date, s.open_at, s.close_at, s.confirmed) for s in self.w.sessions.sessions]
        before = (H.cj(self.snap.to_dict()), H.cj(self.rs.to_dict()), H.cj(self.ledger))
        plan = V.prepare_migration_plan(self.snap, self.rs, self.w.sessions, self.ledger, self.check_d, "mig-1", H.WHEN)
        V.confirm_migration_plan(plan, plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)
        self.assertEqual(before, (H.cj(self.snap.to_dict()), H.cj(self.rs.to_dict()), H.cj(self.ledger)))
        self.assertEqual(sessions_before, [(s.date, s.open_at, s.close_at, s.confirmed)
                                           for s in self.w.sessions.sessions])

    def test_changing_what_was_returned_never_changes_the_plan_or_the_history(self):
        plan = V.prepare_migration_plan(self.snap, self.rs, self.w.sessions, self.ledger, self.check_d, "mig-1", H.WHEN)
        text = plan.to_dict()
        digest = plan.plan_hash
        text["basis"]["candidate_history"]["events"][0]["kind"] = "X"
        plan.basis["candidate_history"]["events"].clear()
        plan.to_dict()["basis"]["check_d"] = "x"
        self.assertEqual(plan.plan_hash, digest)
        res = V.confirm_migration_plan(plan, plan.plan_hash, self.snap, self.rs, self.w.sessions, self.ledger)
        events = res.history.events
        events[0]["kind"] = "X"
        events.clear()
        res.history.to_dict()["events"].clear()
        res.history.current_state["streak"] = 99
        self.assertEqual(V.validate_history(res.history).record_count, 8)
        self.assertEqual(res.history, V.History.from_dict(plan.basis["candidate_history"]))

    def test_migrated_sources_return_independent_values(self):
        h = H.migrate(self.w, self.snap, self.rs, self.ledger, self.check_d)
        a, b = V.migrated_sources(h)
        a.events.clear()
        b.records.clear()
        a2, b2 = V.migrated_sources(h)
        self.assertEqual(a2, self.snap)
        self.assertEqual(b2, self.rs)
        self.assertIsNot(a2, a)

    def test_validate_history_does_not_change_the_history_and_returns_independent_checks(self):
        h = H.example_r().history()
        digest = h.digest
        c1, c2 = V.validate_history(h), V.validate_history(h)
        self.assertEqual(c1, c2)
        self.assertIsNot(c1, c2)
        self.assertEqual(h.digest, digest)
        self.assertTrue(all(isinstance(x, (int, str, tuple, bool, type(None), V.Boundary))
                            for x in vars_of(c1)))

    def test_a_failed_validation_leaves_no_state_behind(self):
        ev = H.example_u().events
        ev[2]["d"] = D[9]
        bad = H.history_of(ev)
        for _ in range(2):
            H.expect_rule(self, "event_hash", bad)
        V.validate_history(H.example_u().history())

    def test_validation_results_are_not_reused_between_calls(self):
        # the same History object is judged again each time: a patched checker is consulted every call
        from unittest import mock
        import v2_history.view as vm
        real = vm.validate_snapshot
        h = H.example_u().history()
        with mock.patch.object(vm, "validate_snapshot", side_effect=real) as m:
            V.validate_history(h)
            first = m.call_count
            V.validate_history(h)
        self.assertEqual(m.call_count, 2 * first)


def vars_of(chk):
    return [getattr(chk, f) for f in chk.__dataclass_fields__]


class Privacy(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.check_d = world_with_secrets()
        self.plan = V.prepare_migration_plan(self.snap, self.rs, self.w.sessions, self.ledger, self.check_d,
                                             "mig-1", H.WHEN)
        self.res = V.confirm_migration_plan(self.plan, self.plan.plan_hash, self.snap, self.rs, self.w.sessions,
                                            self.ledger)

    def assertClean(self, text):
        for needle in (SECRET_ID, SECRET_VALUE, URL, PATH, "abc"):
            self.assertNotIn(needle, text)

    def test_displays_hold_no_row_value_or_free_text(self):
        chk = V.validate_history(self.res.history)
        self.assertClean(shown(self.plan, self.res, self.res.history, chk, self.plan.summary(),
                               self.plan.plan_hash))
        s = self.plan.summary()
        self.assertEqual(sorted(s), sorted(["status", "request_id", "check_d", "source_head_seq", "candidate_records",
                                            "state_unchanged", "committed", "plan_hash"]))
        self.assertEqual(s["candidate_records"], len(self.res.history.events))
        self.assertIs(s["committed"], False)

    def test_a_forged_plan_shows_nothing_it_carries(self):
        basis = self.plan.basis
        basis["request_id"] = URL
        basis["check_d"] = SECRET_VALUE
        forged = V.MigrationPlan.from_dict({"basis": basis, "plan_hash": PATH})
        self.assertEqual(repr(forged), "MigrationPlan(?)")
        e = H.expect_error(self, "history_invalid", "plan_shape", forged.summary)
        self.assertClean(shown(forged, e) + str(e.field) + str(e.rule) + str(e.detail))

    def test_errors_never_echo_the_stored_text(self):
        cases = {
            "variant": lambda ev: ev[3].update(variant=URL),
            "request_id": lambda ev: ev[3].update(request_id=URL),
            "reason": lambda ev: ev[3].update(reason_code=URL + SECRET_ID),
            "kind": lambda ev: ev[3].update(kind=URL),
            "fingerprints": lambda ev: ev[3].update(record_fingerprints=[URL]),
            "state": lambda ev: ev[3].update(state_after={"note": URL}),
            "d": lambda ev: ev[2].update(d=URL),
            "row": lambda ev: ev[2]["confirmed_inputs"]["row"].update(soxx=SECRET_VALUE),
            "decision": lambda ev: ev[2]["confirmed_inputs"]["decision"].update(record_id=URL),
            "extra_key": lambda ev: ev[2].update({URL: 1}),
        }
        base = H.example_u().events
        b = H.HB()
        b.apply(D[1], 27.0)
        b.apply(D[2], 28.0)
        b.ack("ADDED", D[2], [H.fp(H.P.obs("X1", D[2], 41.0, hour=21))], "qa", applied=2)
        for name, fn in cases.items():
            with self.subTest(name):
                ev = H.deep(b.events)
                fn(ev)
                with self.assertRaises(H.PersistenceError) as cm:
                    V.validate_history(H.rebuild(ev))
                e = cm.exception
                self.assertClean("%s %r %s %s %s %s" % (e, e, e.code, e.field, e.rule, e.detail))
                self.assertIsNone(e.__cause__)
                self.assertTrue(e.__suppress_context__ or e.__context__ is None)

    def test_decode_errors_never_echo_the_text(self):
        for text in ('{"a":"%s"' % URL, '{"%s":1,"%s":2}' % (URL, URL), '{"a":NaN,"b":"%s"}' % PATH):
            with self.subTest(text[:12]):
                with self.assertRaises(H.PersistenceError) as cm:
                    V.decode_history(text)
                e = cm.exception
                self.assertClean("%s %r %s %s %s" % (e, e, e.field, e.rule, e.detail))
                self.assertIsNone(e.__cause__)
                self.assertTrue(e.__suppress_context__ or e.__context__ is None)

    def test_migration_refusals_do_not_echo_the_ledger(self):
        rows = self.ledger + [dict(self.ledger[0], current_fg_value="abc" + URL)]
        with self.assertRaises(Exception) as cm:
            V.prepare_migration_plan(self.snap, self.rs, self.w.sessions, rows, self.check_d, "mig-1", H.WHEN)
        e = cm.exception
        self.assertClean("%s %r" % (e, e))
        with self.assertRaises(H.PersistenceError) as cm:
            V.prepare_migration_plan(self.snap, self.rs, self.w.sessions, self.ledger, self.check_d, URL, H.WHEN)
        self.assertClean("%s %r %s %s" % (cm.exception, cm.exception, cm.exception.field, cm.exception.rule))

    def test_the_candidate_itself_does_carry_the_stored_decision_but_only_as_data(self):
        # the stored history legitimately contains the decision row; only displays and errors must not show it
        self.assertIn(SECRET_ID, V.encode_history(self.res.history))


if __name__ == "__main__":
    unittest.main()
