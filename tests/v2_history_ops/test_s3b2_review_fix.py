"""Review fixes of S3-B-2 (R-01, R-02, R-03). Regressions for the three findings of the receipt review; the values
that must not change (plan_hash, batch_hash, projection digests) are pinned from the code before the fix."""
import copy
import unittest

import ho_helpers as T
import v2_history_ops as O
from v2_history_ops.chain import Chain
from v2_recovery.facts import FixedApply, FixedFacts, LedgerContext
from v2_recovery.project import resolve_core

H, D, P, V = T.H, T.D, T.P, T.V
HEX = "0" * 64

# Values taken from the code at 132a339 (before the fix); the fix must not change them.
PINS = {
    "R_q7_plan_hash": "5741403a64f2006bdeaa10a67787ca8cee26f35abf5e312ae14a5792e72d5e80",
    "R_q7_batch_hash": "896bdba375680869b30c0a6ddc9af936ccfaa640c0f8eb5eabcfc5bb2961c921",
    "R_q7_ledger_eff": "365422df87e8cd70d92796342f39b309448d53d8f51c5bc0962bea3cc3bc86e4",
    "R_D7_batch_hash": "17f0c7278dba66081e7ac1d686ac4cd31a9ca89e144dabc7e869ab61f64b8a6b",
    "V_D4_batch_hash": "0eaa9bb911220513aa3e461bc21d4a2bc98553984b5b6c538102a21cba8a36c9",
    "V_proj_eff": "49decc848584179023c5bdc3fbf9ebab2889060687a5d60db2d975147c156358",
    "V_proj_ledger": "47457f21a029c829bb0853d22c2dc1ffd5015453148e317474b634361eccd2df",
    "M_plan_hash": "01ed084c8c8f6cf89f7c776557b6945183b8c939009c0f9e142d8debf301a5f1",
    "M_batch_hash": "fae1046e33666b9e30ae71b3f3e75c741660b344adb563dcce99f9e86d2e6fdd",
}


class R01BatchHashAccessor(unittest.TestCase):
    def test_a_dict_or_list_hash_is_returned_as_an_independent_copy(self):
        for label, raw, edit in (("dict", {"items": []}, lambda x: x["items"].append("changed")),
                                 ("list", [], lambda x: x.append("changed"))):
            with self.subTest(label):
                batch = O.HistoryAppendBatch.from_dict({"body": {}, "batch_hash": raw})
                before, h = batch.to_dict(), hash(batch)
                got = batch.batch_hash
                edit(got)
                self.assertEqual(batch.to_dict(), before)                    # the stored text-backed value is unchanged
                self.assertEqual(batch.batch_hash, raw)
                self.assertIsNot(batch.batch_hash, batch.batch_hash)
                self.assertEqual(hash(batch), h)
                self.assertEqual(batch, O.HistoryAppendBatch.from_dict({"body": {}, "batch_hash": copy.deepcopy(raw)}))
                self.assertEqual(batch.to_dict(), before)

    def test_the_unverified_batch_is_still_refused_with_a_fixed_error(self):
        w = World()
        for raw in ({"items": []}, []):
            batch = O.HistoryAppendBatch.from_dict({"body": w.dbatch.body, "batch_hash": raw})
            e = T.refusal(O.check_append_batch, w.h, batch)
            self.assertEqual((e.code, e.field, e.rule), ("batch_invalid", "batch", "batch_hash"))
        # from_dict keeps accepting what it accepted: a dict / list hash is not refused at the reading gate
        self.assertEqual(O.HistoryAppendBatch.from_dict({"body": {}, "batch_hash": {"x": 1}}).batch_hash, {"x": 1})

    def test_a_normal_hash_is_the_same_string_and_the_rule_is_unchanged(self):
        w = World()
        self.assertEqual(w.dbatch.batch_hash, O.HistoryAppendBatch.from_dict(w.dbatch.to_dict()).batch_hash)
        from v2_history_ops.values import digest_of
        self.assertEqual(w.dbatch.batch_hash, digest_of(w.dbatch.body))
        self.assertIsInstance(w.dbatch.batch_hash, str)


class World:
    def __init__(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.b, self.h, self.w = b, b.history(), b.w
        day = O.prepare_history_day(self.h, D[2], self.w.series, self.w.sessions,
                                    list(self.w.ledger) + [P.obs("R2", D[2], 31.0)])
        self.dbatch = day.batch


def facts_of(history):
    return Chain(history, V.validate_history(history)).facts


def parts_of(facts):
    applies = [{"seq": a.seq, "event_hash": a.event_hash, "d": a.d, "decision": a.decision_cols(),
                "context": a.context, "skipped": list(a.skipped)} for a in facts.applies]
    return applies, facts.declares, facts.boundaries, facts.boundary_day, facts.head_seq


class R02FixedApply(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.facts = facts_of(self.w.h)
        self.ap = self.facts.applies[0]

    def test_no_attribute_can_be_assigned_or_deleted(self):
        snapshot = (self.ap.seq, self.ap.event_hash, self.ap.d, self.ap.skipped, self.ap.record_id,
                    self.ap.fingerprint, self.ap.context)
        for name in ("seq", "event_hash", "d", "skipped", "record_id", "fingerprint", "context", "stored_sessions",
                     "_seq", "_context", "_sessions", "other"):
            with self.subTest(name):
                with self.assertRaises(AttributeError):
                    setattr(self.ap, name, 99)
                with self.assertRaises(AttributeError):
                    delattr(self.ap, name)
        self.assertEqual(snapshot, (self.ap.seq, self.ap.event_hash, self.ap.d, self.ap.skipped, self.ap.record_id,
                                    self.ap.fingerprint, self.ap.context))
        self.assertFalse(hasattr(self.ap, "__dict__"))

    def test_structured_accessors_return_independent_copies(self):
        ctx = self.ap.context
        ctx[0]["confirmed"] = False
        ctx.append("x")
        self.assertEqual(len(self.ap.context), 3)
        self.assertTrue(self.ap.context[0]["confirmed"])
        self.assertIsNot(self.ap.context, self.ap.context)
        ss = self.ap.stored_sessions
        n = len(ss.sessions)
        ss.sessions.clear()
        self.assertEqual(len(self.ap.stored_sessions.sessions), n)
        self.assertIsNot(self.ap.stored_sessions, self.ap.stored_sessions)
        dec = self.ap.decision_cols()
        dec["record_id"] = "changed"
        self.assertNotEqual(self.ap.decision_cols()["record_id"], "changed")
        self.assertIsInstance(self.ap.skipped, tuple)

    def test_the_input_parts_are_copied(self):
        applies, declares, boundaries, day, head = parts_of(self.facts)
        facts = FixedFacts.from_parts(applies, declares, boundaries, day, head)
        before = parts_of(facts)
        applies[0]["context"][0]["confirmed"] = False
        applies[0]["decision"]["record_id"] = "changed"
        applies[0]["skipped"].append("2026-01-01")
        applies.clear()
        boundaries[0]["session"]["confirmed"] = False
        self.assertEqual(parts_of(facts), before)
        self.assertIsInstance(FixedApply(parts_of(self.facts)[0][0]), FixedApply)


class R02FixedFacts(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        b.apply(D[3], 31.0)
        self.h, self.w = b.history(), b.w
        self.facts = facts_of(self.h)

    def test_no_attribute_can_be_assigned_or_deleted(self):
        for name in ("applies", "by_seq", "apply_days", "fixed_fps", "declares", "boundaries", "boundary_day",
                     "head_seq", "latest_day", "_applies", "_by_seq", "other"):
            with self.subTest(name):
                with self.assertRaises(AttributeError):
                    setattr(self.facts, name, None)
                with self.assertRaises(AttributeError):
                    delattr(self.facts, name)
        self.assertFalse(hasattr(self.facts, "__dict__"))

    def test_the_containers_cannot_be_changed(self):
        f = self.facts
        n = len(f.applies)
        self.assertGreaterEqual(n, 2)
        self.assertIsInstance(f.applies, tuple)
        for action in (lambda: f.applies.clear(), lambda: f.applies.append(1), lambda: f.by_seq.clear(),
                       lambda: f.by_seq.pop(1), lambda: f.apply_days.add("x"), lambda: f.apply_days.clear(),
                       lambda: f.fixed_fps.add("x"), lambda: f.fixed_fps.clear()):
            with self.assertRaises((AttributeError, TypeError)):
                action()
        with self.assertRaises(TypeError):
            f.by_seq[99] = f.applies[0]
        with self.assertRaises(TypeError):
            del f.by_seq[1]
        self.assertEqual((len(f.applies), sorted(f.by_seq), len(f.apply_days), len(f.fixed_fps)),
                         (n, [a.seq for a in f.applies], n, n))
        self.assertIs(f.by_seq[f.applies[0].seq], f.applies[0])               # the immutable APPLY itself is shared

    def test_declarations_and_boundaries_are_copies(self):
        f = self.facts
        before = copy.deepcopy((f.declares, f.boundaries))
        f.declares[0]["context"][0]["confirmed"] = False
        f.declares.clear()
        f.boundaries[0]["session"]["confirmed"] = False
        f.boundaries.clear()
        self.assertEqual((f.declares, f.boundaries), before)
        self.assertEqual((len(f.declares), len(f.boundaries)), (1, 1))
        self.assertIsNot(f.declares, f.declares)
        self.assertIsNot(f.boundaries, f.boundaries)

    def test_latest_apply_day_and_decision_cols_still_work(self):
        f = self.facts
        self.assertEqual(f.latest_apply_day(f.head_seq), D[3])
        self.assertEqual(f.latest_apply_day(1), D[1])
        self.assertEqual(f.decision_cols(1), f.by_seq[1].decision_cols())


class R02ContextAndProjection(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.h, self.w = b.history(), b.w
        self.b = b

    def test_the_review_scenario_stays_a_mismatch_whatever_is_tried_on_the_facts(self):
        f = facts_of(self.h)
        ctx = LedgerContext.from_facts(f, self.w.sessions, [], D[2])             # the stored decision is missing
        first = T.outcome(resolve_core, ctx, [], self.h.digest, "resolutions")
        self.assertEqual(first[:3], ("err", "ledger_mismatch", "observations"))
        for action in (lambda: f.applies.clear(), lambda: f.by_seq.clear(), lambda: f.apply_days.clear(),
                       lambda: f.fixed_fps.clear(), lambda: setattr(f, "applies", ()),
                       lambda: setattr(f.applies[0], "seq", 99), lambda: f.applies[0].context.clear(),
                       lambda: f.applies[0].stored_sessions.sessions.clear()):
            try:
                action()
            except (AttributeError, TypeError):
                pass
            again = T.outcome(resolve_core, ctx, [], self.h.digest, "resolutions")
            self.assertEqual(again[:3], first[:3])

    def test_outside_copies_do_not_change_the_checked_facts_or_the_result(self):
        applies, declares, boundaries, day, head = parts_of(facts_of(self.h))
        facts = FixedFacts.from_parts(applies, declares, boundaries, day, head)
        ok = T.outcome(resolve_core, LedgerContext.from_facts(facts, self.w.sessions, self.w.ledger, D[2]), [],
                       self.h.digest, "resolutions")
        applies[0]["decision"]["current_fg_value"] = 1.0
        applies[0]["context"].clear()
        applies.clear()
        again = T.outcome(resolve_core, LedgerContext.from_facts(facts, self.w.sessions, self.w.ledger, D[2]), [],
                          self.h.digest, "resolutions")
        self.assertEqual(ok[0], "ok")
        self.assertEqual(again[1].effective_digest, ok[1].effective_digest)
        self.assertEqual(again[1].excluded_fingerprints, ok[1].excluded_fingerprints)

    def test_evidence_does_not_depend_on_what_the_caller_holds(self):
        x = P.obs("x", D[1], 22.0)
        led = list(self.w.ledger) + [x]
        cmds = [T.ack_cmd(self.h, "ADDED", D[1], [T.fp(x)], 1)]
        plan = T.plan_for(self.h, cmds, self.w.sessions, led, D[2], "q1")
        f = facts_of(self.h)
        for action in (lambda: f.by_seq.clear(), lambda: f.applies.clear()):
            try:
                action()
            except (AttributeError, TypeError):
                pass
        again = T.plan_for(self.h, cmds, self.w.sessions, led, D[2], "q1")
        self.assertEqual(again.plan_hash, plan.plan_hash)


class PinnedValuesDoNotChange(unittest.TestCase):
    def test_hashes_and_digests_equal_those_before_the_fix(self):
        got = {}
        b = H.example_r()
        h, w = b.history(), b.w
        z3 = P.obs("B3", D[3], 41.0, hour=21)
        led = list(w.ledger) + [z3]
        plan, res = T.run_plan(h, [T.ack_cmd(h, "ADDED", D[3], [T.fp(z3)], 19)], w.sessions, led, D[6], "q7")
        got["R_q7_plan_hash"], got["R_q7_batch_hash"] = plan.plan_hash, res.batch.batch_hash
        got["R_q7_ledger_eff"] = res.ledger.effective_digest
        day = T.day(T.extend(h, res), D[7], w, led + [P.obs("R7", D[7], 31.0)])
        got["R_D7_batch_hash"] = day.batch.batch_hash
        b = T.example_v()
        h, w = b.history(), b.w
        got["V_D4_batch_hash"] = T.day(h, D[4], w, list(w.ledger) + [P.obs("R4", D[4], 31.0)]).batch.batch_hash
        proj = O.project_history_ledger(h, w.sessions, w.ledger, D[4])
        got["V_proj_eff"], got["V_proj_ledger"] = proj.effective_digest, proj.ledger_digest
        hb, (w, _snap, _rs, ledger, cd) = H.example_m()
        h = hb.history()
        ch = P.obs("R2", D[2], 33.0)
        led = [x for x in ledger if x["record_id"] != "R2"] + [ch]
        plan, res = T.run_plan(h, [T.ack_cmd(h, "CHANGED", D[2], [T.fp(ch)], 3)], w.sessions, led, D[5], "q4")
        got["M_plan_hash"], got["M_batch_hash"] = plan.plan_hash, res.batch.batch_hash
        self.assertEqual(got, PINS)


class R03RetiredTrailingDeclaration(unittest.TestCase):
    """The counterexample of the review: a valid history whose DROPped last declaration must not be compared with the
    sessions. A change of only that declaration's own day (its close_at) is outside every range in effect."""

    def build(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")                       # 2, retired by the restore below
        b.restore(1, {2: "DROP"}, "q2")             # 3
        b.restart(D[4], "q3")                       # 4
        return b

    def sessions(self):
        return P.make_sessions(overrides={D[2]: lambda s: s.__class__(
            s.date, s.open_at, s.close_at.replace(hour=15), s.confirmed)})

    def test_the_history_is_valid_and_the_projection_succeeds(self):
        b = self.build()
        h = b.history()
        check = V.validate_history(h)
        self.assertEqual(list(check.effective_seqs), [0, 1, 3, 4])
        self.assertEqual(list(check.superseded_seqs), [2])
        self.assertEqual([r["kind"] for r in b.events], ["GENESIS", "APPLY", "DECLARE_MISSING", "RECOVERY_RESTORE",
                                                           "RESTART_UNKNOWN"])
        self.assertEqual(O.read_effective(h).resolutions, [])               # no declaration in effect
        got = O.project_history_ledger(h, self.sessions(), b.w.ledger, D[5])
        self.assertEqual(got.excluded_fingerprints, [])
        # the same sessions, unchanged, also pass; the changed close_at of D2 is harmless (next(D1) is compared by
        # its date and open_at only)
        self.assertEqual(O.project_history_ledger(h, b.w.sessions, b.w.ledger, D[5]).effective_digest,
                         got.effective_digest)

    def test_the_facts_hold_no_retired_declaration(self):
        b = self.build()
        facts = facts_of(b.history())
        self.assertEqual(facts.declares, [])
        self.assertEqual([a.seq for a in facts.applies], [1])

    def test_the_real_declaration_is_still_compared(self):
        """Control: a declaration in effect is compared (the change would stop the projection)."""
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        h = b.history()
        facts = facts_of(h)
        self.assertEqual([d["d"] for d in facts.declares], [D[2]])
        e = T.refusal(O.project_history_ledger, h, self.sessions(), b.w.ledger, D[3])
        self.assertEqual((e.code, e.field), ("session_context_mismatch", "sessions"))


if __name__ == "__main__":
    unittest.main()
