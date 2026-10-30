"""B2-02: the API-1 edit of v2_recovery (facts.py, commands.check_commands, the v2 reference form of LATE).

Pins that S3-A behaves as before (output hashes taken at the base commit adfdf765, the markers of the S3-A defect
injection script) and that the new facts / context give the same decisions as the S3-A context on the same data.
"""
import importlib.util
import os
import unittest

import ho_helpers as T
import s3a_golden as G
from v2_persistence.errors import PersistenceError
from v2_recovery.commands import check_commands
from v2_recovery.facts import FixedApply, FixedFacts, LedgerContext
from v2_recovery.project import Ctx, resolve_core

H, RH, P, D = T.H, T.RH, T.P, T.D

# produced by tests/v2_history_ops/s3a_golden.py at adfdf765aeca0d01c8f10b596a6fac59d7c1a07e, before any edit
BASE_GOLDEN = {
    "m2_effective_digest": "f5d6c18c4ae228787e8dc8f0d2ae716b4f6def8da8b538791c62ed34f8f1ba00",
    "m2_extra_make_records": "879924bf7835a060449d34d6deb8f7281185322f8a91c68c54dbe4faebac3adf",
    "m2_extra_plan_hash": "c6f7ffbfee84cbf98d92074c598032462a18a762c4fdc3aad3c6a2ad4133d79c",
    "m2_records": "b846a939a462d4f88e6527647f61bb92ba1568f018c6dda1061a2a00165a7b21",
    "m2_resolutions_digest": "b846a939a462d4f88e6527647f61bb92ba1568f018c6dda1061a2a00165a7b21",
    "m_effective_digest": "b0c102d414429bb6db4057e54053ec9bf3df57f2b00a3995a6a6b62959278111",
    "m_extra_make_records": "ad089e0871722c78abe8f42ab55a1dcc52a3a62039f465d90bf03ac09657aa2e",
    "m_extra_plan_hash": "cdee3b6f4eedda48bc856cc64b30874f4cba1bb21af4f6a4366a53c760feee81",
    "m_records": "8560b6e28a41b594cdb913021c7ca7f9b85f4a17ef1e5e950dd1368538d00dfc",
    "m_resolutions_digest": "8560b6e28a41b594cdb913021c7ca7f9b85f4a17ef1e5e950dd1368538d00dfc",
    "w1_declare_make_records": "e6fcd80393202a6e67043e2d78ba6e6ccbaf84576e69b4413982f2aa156f587c",
    "w1_declare_plan_hash": "c036b74eda175752aef9fd98db41cd9d1f5c058d1a12e748ae9cffd976048430",
    "w2_batch_make_records": "95db1d881cfb4d3c6ed2c2a27e4c06d45ed638400b2d08035d20aa75abf65d2e",
    "w2_batch_plan_hash": "60bcaf0e151353387d55ab2654005062ec9aae52f5b93d3bd1a30f6900606dc4"}

ROOT = T.ROOT
NOTHING = object()


def load_mutations():
    path = os.path.join(ROOT, "tests", "v2_recovery", "sensitivity_check.py")
    spec = importlib.util.spec_from_file_location("s3a_sensitivity_readonly", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MUTATIONS


def marker_counts():
    """[(id, file, count)] of every old-string of the S3-A defect injection script in the current v2_recovery."""
    out = []
    for mid, fname, old, _new, _what in load_mutations():
        with open(os.path.join(ROOT, "v2_recovery", fname), encoding="utf-8") as f:
            out.append((mid, fname, f.read().count(old)))
    return out


class S3AUnchanged(unittest.TestCase):
    def test_golden_outputs_equal_the_base_commit(self):
        self.assertEqual(G.compute(), BASE_GOLDEN)

    def test_every_marker_of_the_s3a_injection_script_occurs_exactly_once(self):
        counts = marker_counts()
        self.assertGreaterEqual(len(counts), 55)
        self.assertEqual([c for c in counts if c[2] != 1], [])

    def test_changed_files_are_the_two_allowed_ones(self):
        # the edit made no other module of v2_recovery import facts (it is not re-exported either)
        import v2_recovery
        self.assertNotIn("facts", getattr(v2_recovery, "__all__", []))
        self.assertFalse(hasattr(v2_recovery, "FixedFacts"))
        self.assertFalse(hasattr(v2_recovery, "LedgerContext"))


class FactsShape(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.cd = H.example_m2_world()
        ev = self.snap.events
        g = ev[0]
        self.applies = [{"seq": e["seq"], "event_hash": e["event_hash"], "d": e["d"],
                         "decision": e["confirmed_inputs"]["decision"],
                         "context": e["confirmed_inputs"]["session_context"], "skipped": e["skipped_sessions"]}
                        for e in ev[1:]]
        self.bounds = [{"date": g["start_after"], "session": g["boundary_session"]}]
        self.day = g["start_after"]
        self.head = self.snap.head_seq

    def parts(self, **over):
        args = {"applies": T.deep(self.applies), "declares": [], "boundaries": T.deep(self.bounds),
                "boundary_day": self.day, "head_seq": self.head}
        args.update(over)
        return args

    def build(self, **over):
        return FixedFacts.from_parts(**self.parts(**over))

    def invalid(self, **over):
        with self.assertRaises(PersistenceError) as cm:
            self.build(**over)
        self.assertEqual((cm.exception.code, cm.exception.field), ("facts_invalid", "facts"))
        return cm.exception

    def test_valid_parts_and_attributes(self):
        f = self.build()
        self.assertEqual([a.seq for a in f.applies], [1, 2, 3, 4])
        self.assertEqual(set(f.by_seq), {1, 2, 3, 4})
        self.assertEqual(f.apply_days, {a["d"] for a in self.applies})
        self.assertEqual(f.boundary_day, self.day)
        self.assertEqual(f.head_seq, self.head)
        self.assertEqual(f.latest_day, max(f.apply_days))
        self.assertEqual(len(f.fixed_fps), 4)

    def test_record_id_and_fingerprint_are_computed_from_the_saved_decision(self):
        f = self.build()
        v = {a["seq"]: a for a in self.applies}
        for ap in f.applies:
            row = RH.L.parse_row(v[ap.seq]["decision"])
            self.assertEqual((ap.record_id, ap.fingerprint), (row.obs.record_id, row.fp))

    def test_latest_apply_day(self):
        f = self.build()
        self.assertEqual(f.latest_apply_day(0), self.day)
        self.assertEqual(f.latest_apply_day(1), self.applies[0]["d"])
        self.assertEqual(f.latest_apply_day(99), self.applies[-1]["d"])
        # a later boundary raises the floor (restart): older APPLY days below it do not matter
        late_day = D[30]
        f2 = FixedFacts.from_parts([], [], [{"date": late_day, "session": H.sess(late_day)}], late_day, 0)
        self.assertEqual(f2.latest_apply_day(0), late_day)

    def test_facts_do_not_alias_the_input(self):
        parts = self.parts()
        f = FixedFacts.from_parts(**parts)
        parts["applies"][0]["context"][0]["date"] = "1999-01-01"
        parts["applies"][0]["decision"]["record_id"] = "x"
        parts["bounds"] = None
        self.assertEqual(f.applies[0].context[0]["date"], self.applies[0]["context"][0]["date"])
        out = f.decision_cols(1)
        out["record_id"] = "mutated"
        self.assertNotEqual(f.decision_cols(1)["record_id"], "mutated")

    def test_shape_errors(self):
        a = self.applies
        bad_cases = {
            "duplicate_seq": {"applies": [T.deep(a[0]), T.deep(a[0])]},
            "descending_seq": {"applies": [T.deep(a[1]), T.deep(a[0])]},
            "bool_seq": {"applies": [dict(T.deep(a[0]), seq=True)]},
            "float_seq": {"applies": [dict(T.deep(a[0]), seq=1.0)]},
            "seq_above_head": {"head_seq": 1},
            "bool_head": {"head_seq": True},
            "bad_hash": {"applies": [dict(T.deep(a[0]), event_hash="zz")]},
            "bad_day": {"applies": [dict(T.deep(a[0]), d="2026-13-01")]},
            "non_canonical_session": {"applies": [dict(T.deep(a[0]), context=[dict(e, confirmed=1)
                                                                              for e in T.deep(a[0])["context"]])]},
            "extra_session_key": {"applies": [dict(T.deep(a[0]), context=[dict(e, x=1)
                                                                          for e in T.deep(a[0])["context"]])]},
            "context_before_last_not_d": {"applies": [dict(T.deep(a[0]), d=a[1]["d"])]},
            "decision_unparsable": {"applies": [dict(T.deep(a[0]), decision={"record_id": "x"})]},
            "decision_not_dict": {"applies": [dict(T.deep(a[0]), decision=[1])]},
            "decision_other_day": {"applies": [dict(T.deep(a[0]), decision=T.deep(a[1]["decision"]))]},
            "skipped_not_dates": {"applies": [dict(T.deep(a[0]), skipped=["x"])]},
            "extra_key": {"applies": [dict(T.deep(a[0]), extra=1)]},
            "no_boundaries": {"boundaries": []},
            "boundary_day_mismatch": {"boundary_day": D[9]},
            "boundary_session_other_date": {"boundaries": [{"date": self.day, "session": H.sess(D[9])}]},
            "boundaries_not_a_list": {"boundaries": None},
            "declare_context_other_day": {"declares": [{"seq": 5, "event_hash": "0" * 64, "d": D[9],
                                                       "context": [H.sess(D[1]), H.sess(D[2]), H.sess(D[3])]}]},
            "declare_two_contexts": {"declares": [{"seq": 5, "event_hash": "0" * 64, "d": D[2],
                                                   "context": [H.sess(D[1]), H.sess(D[2])]}]},
        }
        for name, over in bad_cases.items():
            with self.subTest(name):
                e = self.invalid(**over)
                self.assertEqual(e.rule, "shape")

    def test_fixed_apply_requires_a_dict(self):
        with self.assertRaises(PersistenceError) as cm:
            FixedApply(None)
        self.assertEqual(cm.exception.code, "facts_invalid")

    def test_not_publicly_constructible(self):
        with self.assertRaises(TypeError):
            FixedFacts()


class LedgerContextOrder(unittest.TestCase):
    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.cd = H.example_m2_world()
        self.f = T.facts_of_snapshot(self.snap, self.rs.records)

    def make(self, facts=NOTHING, sessions=NOTHING, ledger=NOTHING, check_d=NOTHING):
        return LedgerContext.from_facts(self.f if facts is NOTHING else facts,
                                        self.w.sessions if sessions is NOTHING else sessions,
                                        self.ledger if ledger is NOTHING else ledger,
                                        self.cd if check_d is NOTHING else check_d)

    def err(self, **kw):
        out = T.outcome(self.make, **kw)
        self.assertEqual(out[0], "err", out)
        return out[1:]

    def test_attributes(self):
        c = self.make()
        self.assertIs(c.sv, c.facts)
        self.assertEqual(c.check_d, self.cd)
        self.assertEqual(len(c.rows), len(self.ledger))
        self.assertEqual(set(c.all_by_fp), {r.fp for r in c.rows})
        ref = Ctx(self.snap, self.rs, self.w.sessions, self.ledger, self.cd)
        self.assertEqual((c.ledger_digest, c.sessions_digest), (ref.ledger_digest, ref.sessions_digest))

    def test_another_type_is_facts_invalid(self):
        for bad in (self.snap, None, {"applies": []}, self.f.applies):
            with self.subTest(type(bad).__name__):
                self.assertEqual(self.err(facts=bad), ("facts_invalid", "facts", "type"))

    def test_check_d_rules(self):
        self.assertEqual(self.err(check_d="x")[0], "invalid_date")
        # at or before the boundary
        self.assertEqual(self.err(check_d=self.f.boundary_day), ("target_not_after_boundary", "target_session_date",
                                                                  None))
        self.assertEqual(self.err(check_d=D[0])[:2], ("target_not_after_boundary", "target_session_date"))
        # before the latest APPLY of the facts
        self.assertEqual(self.err(check_d=D[3])[:2], ("state_ahead_of_target", "state"))
        self.assertEqual(self.err(check_d="2030-01-02")[:2], ("target_not_in_sessions", "sessions"))
        self.assertEqual(self.err(check_d=D[len(P.DATES) - 1])[:2], ("next_session_missing", "sessions"))

    def test_unconfirmed_check_d(self):
        sl = P.make_sessions(unconfirmed={D[7]})
        self.assertEqual(self.err(sessions=sl, check_d=D[7])[:2], ("target_unconfirmed", "sessions"))

    def test_boundary_session_must_equal_exactly(self):
        sl = P.make_sessions(overrides={self.f.boundary_day: lambda s: s.__class__(
            s.date, s.open_at, s.close_at.replace(hour=15), s.confirmed)})
        self.assertEqual(self.err(sessions=sl)[:2], ("session_context_mismatch", "sessions"))
        missing = P.make_sessions(dates=P.DATES[1:])
        self.assertEqual(self.err(sessions=missing)[:2], ("session_context_missing", "sessions"))

    def test_apply_and_declaration_ranges_are_compared(self):
        d1 = self.f.applies[0].d
        sl = P.make_sessions(overrides={d1: lambda s: s.__class__(s.date, s.open_at.replace(minute=31), s.close_at,
                                                                  s.confirmed)})
        self.assertEqual(self.err(sessions=sl)[:2], ("session_context_mismatch", "sessions"))
        # the same projection as S3-A: next(D) of the last APPLY is compared by date and open_at only
        nxt = self.w.sessions.next(self.f.applies[-1].d)
        ok = P.make_sessions(overrides={nxt.date: lambda s: s.__class__(s.date, s.open_at, s.close_at.replace(
            hour=15), s.confirmed)})
        self.make(sessions=ok)

    def test_every_row_is_parsed(self):
        out = self.err(ledger=self.ledger + [{"record_id": "x"}])
        self.assertEqual(out[0], "status_unknown")

    def test_order_facts_type_before_sessions_before_check_d(self):
        self.assertEqual(self.err(facts=None, sessions=None)[2], "type")
        out = T.outcome(LedgerContext.from_facts, self.f, "not sessions", self.ledger, "x")
        self.assertEqual(out[1:3], ("sessions_invalid", "sessions"))
        out = T.outcome(LedgerContext.from_facts, self.f, self.w.sessions, self.ledger, D[0])
        self.assertEqual(out[1], "target_not_after_boundary")
        # check_d error comes before the boundary-session and the row errors
        bad_sl = P.make_sessions(dates=P.DATES[1:])
        out = T.outcome(LedgerContext.from_facts, self.f, bad_sl, self.ledger + [{"record_id": "x"}], "2030-01-02")
        self.assertEqual(out[1], "target_not_in_sessions")


class SameDecisionsAsTheS3AContext(unittest.TestCase):
    """The rule functions give the same result for a Ctx (S1 Snapshot + set) and a LedgerContext over the same
    facts, for projection and for the evidence of new commands."""

    def worlds(self):
        w, snap, rs, ledger, cd = H.example_m2_world()
        yield "m2", w, snap, rs, ledger, cd
        w, snap, rs, ledger, cd = H.example_m_world()
        yield "m", w, snap, rs, ledger, cd

    def test_projection_rows_are_equal(self):
        for name, w, snap, rs, ledger, cd in self.worlds():
            with self.subTest(name):
                ctx = Ctx(snap, rs, w.sessions, ledger, cd)
                lc = LedgerContext.from_facts(T.facts_of_snapshot(snap, rs.records), w.sessions, ledger, cd)
                a = resolve_core(ctx, ctx.records, "d", "resolutions")
                b = resolve_core(lc, rs.records, "d", "resolutions")
                self.assertEqual(a, b)
                self.assertEqual((a.excluded_fingerprints, a.supplemented), (b.excluded_fingerprints, b.supplemented))

    def commands(self, snap, ledger, name):
        z9 = RH.fp(P.obs("Z9", D[4], 44.0, hour=21))
        z8 = RH.fp(P.obs("Z8", D[1], 44.0, hour=21))
        l3 = RH.fp(P.obs("L3", D[3], 22.0))
        if name == "m2":
            return {
                "added_ok": [RH.ack(snap, "ADDED", D[4], [z9], seq=3)],
                "added_wrong_apply": [RH.ack(snap, "ADDED", D[4], [z9], seq=2)],
                "added_unknown_row": [RH.ack(snap, "ADDED", D[4], ["0" * 64], seq=3)],
                "changed_same_fp": [RH.ack(snap, "CHANGED", D[1], [RH.ref_of(snap, 1)["fingerprint"]], seq=1)],
                "row_removed_with_fps": [RH.ack(snap, "ROW_REMOVED", D[2], [z9], seq=2)],
                "late_by_apply": [RH.late(D[3], [l3], RH.apply_missing(snap, 3))],
                "late_wrong_apply": [RH.late(D[3], [l3], RH.apply_missing(snap, 2))],
                "late_applied_day": [RH.late(D[4], [z9], RH.apply_missing(snap, 3))],
                "ack_after_check_d": [RH.ack(snap, "ADDED", D[4], [z9], seq=3)],
                "exclude_applied": [RH.ack(snap, "ADDED", D[4], [RH.ref_of(snap, 3)["fingerprint"]], seq=3)],
                "declare_after_check_d": [RH.declare(D[7])],
                "declare_applied": [RH.declare(D[6])],
                "declare_gap": [RH.declare(D[5])],
            }
        return {
            "added_ok": [RH.ack(snap, "ADDED", D[1], [z8], seq=1)],
            "declare_d5": [RH.declare(D[5])],
            "declare_d3": [RH.declare(D[3])],
            "declare_two": [RH.declare(D[5]), RH.declare(D[6])],
            "mixed_batch": [RH.ack(snap, "ADDED", D[1], [z8], seq=1), RH.declare(D[5])],
        }

    def test_evidence_results_are_equal(self):
        seen = {"ok": 0, "err": 0}
        extra = {"m2": P.obs("Z9", D[4], 44.0, hour=21), "m": P.obs("Z8", D[1], 44.0, hour=21)}
        for name, w, snap, rs, ledger, cd in self.worlds():
            ledger = ledger + [extra[name]]
            ctx = Ctx(snap, rs, w.sessions, ledger, cd)
            lc = LedgerContext.from_facts(T.facts_of_snapshot(snap, rs.records), w.sessions, ledger, cd)
            for cname, cmds in self.commands(snap, ledger, name).items():
                with self.subTest("%s/%s" % (name, cname)):
                    cmds = [RH.R.common.normalize_command(c, "commands") for c in cmds]
                    a = T.outcome(check_commands, ctx, ctx.records, cmds)
                    b = T.outcome(check_commands, lc, rs.records, cmds)
                    self.assertEqual(a, b)
                    seen[a[0]] += 1
        self.assertGreater(seen["ok"], 2)
        self.assertGreater(seen["err"], 5)

    def test_declare_frontier_and_context_are_equal(self):
        # a plain world: one APPLY, D2 undecided: DECLARE(D2) then DECLARE(D3) in one request
        w = RH.world(1)
        snap = w.snap()
        rs = RH.R.empty_resolutions()
        ledger = list(w.ledger)
        ctx = Ctx(snap, rs, w.sessions, ledger, D[4])
        lc = LedgerContext.from_facts(T.facts_of_snapshot(snap), w.sessions, ledger, D[4])
        cmds = [RH.R.common.normalize_command(c, "commands") for c in (RH.declare(D[2]), RH.declare(D[3]))]
        a = check_commands(ctx, [], cmds)
        b = check_commands(lc, [], cmds)
        self.assertEqual(a, b)
        self.assertEqual([x[0] for x in a], [D[1], D[2]])      # the second declaration's frontier is the first's day


class LateReferenceForms(unittest.TestCase):
    """_check_late accepts the S3-A reference (resolution_seq / resolution_hash) and the v2 reference (seq /
    event_hash) of a declaration; the APPLY form is shared."""

    def setUp(self):
        self.w, self.snap, self.rs, self.ledger, self.cd = H.example_m2_world()
        self.late_fp = RH.fp(P.obs("L3", D[3], 22.0))
        decl = [r for r in self.rs.records if r["kind"] == "DECLARE_MISSING"][0]
        self.decl = decl
        # a v2 declaration record: seq / event_hash (no resolution_seq)
        self.v2_existing = [{"kind": "DECLARE_MISSING", "variant": None, "d": decl["d"], "seq": 7,
                             "event_hash": "ab" * 32, "record_fingerprints": [], "applied_ref": None,
                             "missing_ref": None, "session_context": decl["session_context"]}]
        self.lc = LedgerContext.from_facts(T.facts_of_snapshot(self.snap, self.rs.records), self.w.sessions,
                                           self.ledger, self.cd)
        self.ctx = Ctx(self.snap, self.rs, self.w.sessions, self.ledger, self.cd)

    def late(self, ref, d=None):
        c = RH.late(d or self.decl["d"], [self.late_fp], ref)
        return [RH.R.common.normalize_command(c, "commands")]

    def v2_cmd(self, ref, d=None):
        """a v2-form command (as v2_history.view.normalize_command(.., 'v2') returns it)"""
        from v2_history.view import normalize_command
        c = RH.late(d or self.decl["d"], [self.late_fp], ref)
        return [normalize_command(c, "v2")]

    def test_s3a_form_accepted_and_refused_as_before(self):
        ok = RH.declare_missing(self.rs, self.decl["resolution_seq"])
        self.assertEqual(T.outcome(check_commands, self.ctx, self.rs.records, self.late(ok))[0], "ok")
        bad_hash = dict(ok, resolution_hash="cd" * 32)
        bad_seq = dict(ok, resolution_seq=ok["resolution_seq"] + 1)
        for ref in (bad_hash, bad_seq):
            out = T.outcome(check_commands, self.ctx, self.rs.records, self.late(ref))
            self.assertEqual(out, ("err", "resolution_invalid", "commands", "late_missing_ref"))
        out = T.outcome(check_commands, self.ctx, self.rs.records, self.late(ok, d=D[5]))
        self.assertEqual(out[3], "late_missing_ref")

    def test_v2_form_accepted_and_refused(self):
        rec = self.v2_existing[0]
        ok = {"kind": "DECLARE_MISSING", "seq": rec["seq"], "event_hash": rec["event_hash"]}
        self.assertEqual(T.outcome(check_commands, self.lc, self.v2_existing, self.v2_cmd(ok))[0], "ok")
        cases = {"hash": dict(ok, event_hash="cd" * 32), "seq": dict(ok, seq=rec["seq"] + 1)}
        for name, ref in cases.items():
            with self.subTest(name):
                out = T.outcome(check_commands, self.lc, self.v2_existing, self.v2_cmd(ref))
                self.assertEqual(out, ("err", "resolution_invalid", "commands", "late_missing_ref"))
        with self.subTest("other day"):
            out = T.outcome(check_commands, self.lc, self.v2_existing, self.v2_cmd(ok, d=D[5]))
            self.assertEqual(out[3], "late_missing_ref")
        with self.subTest("no such declaration"):
            out = T.outcome(check_commands, self.lc, [], self.v2_cmd(ok))
            self.assertEqual(out[3], "late_missing_ref")
        with self.subTest("an ACK is not a declaration"):
            ack_rec = dict(self.v2_existing[0], kind="ACK", variant="ADDED")
            out = T.outcome(check_commands, self.lc, [ack_rec], self.v2_cmd(ok))
            self.assertEqual(out[3], "late_missing_ref")

    def test_apply_form_works_with_both_contexts(self):
        ref = RH.apply_missing(self.snap, 3)
        a = T.outcome(check_commands, self.ctx, self.rs.records, self.late(ref, d=D[3]))
        b = T.outcome(check_commands, self.lc, self.rs.records, self.late(ref, d=D[3]))
        self.assertEqual((a[0], a), (b[0], b))
        self.assertEqual(a[0], "ok")


if __name__ == "__main__":
    unittest.main()
