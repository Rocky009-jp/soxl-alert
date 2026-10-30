"""B2-03: the effective view, the v2 reference names and the facts built from a checked history."""
import unittest

import ho_helpers as T
import v2_history as V
import v2_history_ops as O
from v2_history_ops.chain import Chain
from v2_history.view import project_segment
from v2_persistence.recompute import validate_snapshot

H, D, P, RH = T.H, T.D, T.P, T.RH

VIEW_KEYS = {"history_digest", "head_seq", "head_hash", "state_digest", "migrated", "migration_seq", "effective_seqs",
             "superseded_seqs", "current_boundary", "processing_after", "latest_apply_d", "segments", "applies",
             "resolutions", "requests"}


def chain_of(history):
    return Chain(history, V.validate_history(history))


class ViewKeys(unittest.TestCase):
    def test_all_keys_and_shapes_for_a_restored_history(self):
        h = H.example_r().history()
        v = O.read_effective(h)
        d = v.to_dict()
        self.assertEqual(set(d), VIEW_KEYS)
        check = V.validate_history(h)
        self.assertEqual((d["history_digest"], d["head_seq"], d["head_hash"], d["state_digest"]),
                         (check.history_digest, check.head_seq, check.head_hash, check.state_digest))
        self.assertEqual((d["effective_seqs"], d["superseded_seqs"]), (list(check.effective_seqs),
                                                                       list(check.superseded_seqs)))
        self.assertEqual(d["current_boundary"], {"kind": "GENESIS", "seq": 0, "after": D[0]})
        self.assertEqual((d["processing_after"], d["latest_apply_d"]), (check.processing_after, check.latest_apply_d))
        self.assertFalse(d["migrated"])
        self.assertIsNone(d["migration_seq"])
        seg = d["segments"][0]
        self.assertEqual(set(seg), {"kind", "seq", "after", "apply_seqs", "declare_seqs", "resolution_seqs"})
        for a in d["applies"]:
            self.assertEqual(set(a), {"seq", "event_hash", "d", "segment_seq", "record_id", "fingerprint",
                                      "skipped"})
        for r in d["requests"]:
            self.assertEqual(set(r), {"request_id", "record_kind", "request_hash", "seqs", "effective", "source"})
        # no ledger row, F&G value, stored decision or session context anywhere in the view
        text = T.cj(d)
        for forbidden in ("current_fg_value", "observed_at_iso8601", "session_context", "open_at", "confirmed_inputs"):
            self.assertNotIn(forbidden, text)

    def test_resolution_keys(self):
        hb, _ = H.example_m()
        d = O.read_effective(hb.history()).to_dict()
        for r in d["resolutions"]:
            self.assertEqual(set(r), {"seq", "event_hash", "kind", "variant", "d", "request_id", "command_index",
                                      "command_count", "source", "applied_ref", "missing_ref",
                                      "record_fingerprints", "segment_seq"})

    def test_example_v_segments(self):
        b = H.HB()
        b.apply(D[1], 27.0)                      # 1
        b.declare(D[2], "q1")                    # 2
        b.restart(D[3], "q2")                    # 3
        b.apply(D[4], 29.0)                      # 4
        d = O.read_effective(b.history()).to_dict()
        self.assertEqual([(s["kind"], s["seq"], s["after"]) for s in d["segments"]],
                         [("GENESIS", 0, D[0]), ("RESTART_UNKNOWN", 3, D[3])])
        self.assertEqual(d["segments"][0]["apply_seqs"], [1])
        self.assertEqual(d["segments"][0]["declare_seqs"], [2])
        self.assertEqual(d["segments"][0]["resolution_seqs"], [2])
        self.assertEqual(d["segments"][1]["apply_seqs"], [4])
        self.assertEqual({a["seq"]: a["segment_seq"] for a in d["applies"]}, {1: 0, 4: 3})
        self.assertEqual(d["current_boundary"], {"kind": "RESTART_UNKNOWN", "seq": 3, "after": D[3]})
        self.assertEqual({r["seq"]: r["segment_seq"] for r in d["resolutions"]}, {2: 0})


class RetiredRecords(unittest.TestCase):
    def test_example_r_retired_resolutions_are_not_applied(self):
        b = H.example_r()
        d = O.read_effective(b.history()).to_dict()
        # after RESTORE#3: effective chain 0, 1, 2, 18, 19..22; the ACK of q2 (#5, replayed as #9) is retired
        self.assertEqual(d["effective_seqs"], [0, 1, 2, 18, 19, 20, 21, 22])
        self.assertEqual([a["seq"] for a in d["applies"]], [1, 2, 19, 20, 21, 22])
        self.assertEqual(d["resolutions"], [])
        self.assertEqual(d["segments"][0]["resolution_seqs"], [])
        by_id = {}
        for r in d["requests"]:
            by_id.setdefault(r["request_id"], []).append(r)
        # requests cover the whole physical history, retired records included
        self.assertEqual(sorted(by_id), ["q1", "q2", "q3", "q4", "q5", "q6"])
        self.assertEqual([(r["source"], r["effective"], r["seqs"]) for r in by_id["q2"]],
                         [("NATIVE", False, [5]), ("REPLAYED", False, [9])])
        self.assertEqual([(r["record_kind"], r["effective"]) for r in by_id["q4"]], [("RECOVERY_RESTORE", False)])
        self.assertEqual([(r["record_kind"], r["effective"]) for r in by_id["q6"]], [("RECOVERY_RESTORE", True)])
        self.assertEqual([(r["record_kind"], r["effective"]) for r in by_id["q1"]], [("RESTART_UNKNOWN", False)])

    def test_example_r_after_restore_2_keeps_the_replayed_ack(self):
        b = H.example_r()
        h = T.H.history_of(b.events[:18])                    # physical prefix up to and including #17
        d = O.read_effective(h).to_dict()
        self.assertEqual(d["effective_seqs"], [0, 1, 2, 7, 8, 9, 14, 15, 16, 17])
        self.assertEqual([(r["seq"], r["source"], r["request_id"]) for r in d["resolutions"]], [(9, "REPLAYED", "q2")])
        r9 = d["resolutions"][0]
        # the reference of the replayed record is mapped to the effective APPLY (#8), not the retired #4
        self.assertEqual(r9["applied_ref"]["seq"], 8)

    def test_example_rb_replayed_declaration(self):
        b = H.example_rb()
        d = O.read_effective(b.history()).to_dict()
        self.assertEqual(d["effective_seqs"], [0, 1, 6, 7, 8, 9])
        res = d["resolutions"]
        self.assertEqual([(r["seq"], r["kind"], r["source"], r["d"]) for r in res], [(8, "DECLARE_MISSING", "REPLAYED", D[3])])
        self.assertEqual([a["seq"] for a in d["applies"]], [1, 7, 9])
        self.assertEqual([a["skipped"] for a in d["applies"]], [[], [], [D[3]]])


class Sources(unittest.TestCase):
    def test_migrated_native_and_replayed(self):
        hb, (w, snap, rs, ledger, cd) = H.example_m()
        d = O.read_effective(hb.history()).to_dict()
        self.assertEqual({r["source"] for r in d["resolutions"]}, {"MIGRATED"})
        self.assertTrue(d["migrated"])
        self.assertEqual(d["migration_seq"], 7)
        mig = [r for r in d["requests"] if r["record_kind"] == "SCHEMA_MIGRATION"]
        self.assertEqual([(r["request_id"], r["source"]) for r in mig], [("mig-1", "NATIVE")])
        # a native request after the migration
        extra = P.obs("B2", D[2], 40.0, hour=21)
        ledger2 = ledger + [extra]
        h = hb.history()
        _, res = T.run_plan(h, [T.ack_cmd(h, "ADDED", D[2], [T.fp(extra)], 3)], w.sessions, ledger2, cd, "n1")
        h2 = T.extend(h, res)
        d2 = O.read_effective(h2).to_dict()
        self.assertEqual([r["source"] for r in d2["resolutions"]], ["MIGRATED", "MIGRATED", "MIGRATED", "NATIVE"])

    def test_origin_wins_over_replay_of(self):
        # a restore point is never before the migration, so a migrated record is never replayed in a real history;
        # the rule is still fixed: a record that carries an origin keeps its S3-A request namespace
        from v2_history_ops.chain import source_of
        self.assertEqual(source_of({"origin": {"x": 1}, "replay_of": {"seq": 1}}), "MIGRATED")
        self.assertEqual(source_of({"origin": None, "replay_of": {"seq": 1}}), "REPLAYED")
        self.assertEqual(source_of({"origin": None, "replay_of": None}), "NATIVE")
        self.assertEqual(source_of({"kind": "RECOVERY_RESTORE"}), "NATIVE")


class FactsMatchTheS1Checker(unittest.TestCase):
    def test_v2_seq_is_used_not_the_temporary_s1_seq(self):
        hb, (w, snap, rs, ledger, cd) = H.example_m()
        facts = chain_of(hb.history()).facts
        self.assertEqual(sorted(facts.by_seq), [1, 3, 5])                  # v2 seqs
        self.assertEqual([ap.seq for ap in validate_snapshot(snap).applies], [1, 2, 3])   # v1 seqs differ
        for ap in facts.applies:
            self.assertEqual(ap.event_hash, hb.events[ap.seq]["event_hash"])
        self.assertEqual([x["seq"] for x in chain_of(hb.history()).facts.declares], [4])

    def test_fingerprints_record_ids_and_skipped_equal_the_s1_values(self):
        for name, hb in (("m", H.example_m()[0]), ("r", H.example_r()), ("rb", H.example_rb()),
                         ("u", H.example_u())):
            with self.subTest(name):
                ch = chain_of(hb.history())
                for seg, validated in zip(ch.segments, ch.projected):
                    self.assertEqual(len(seg.applies), len(validated.applies))
                    for rec, applied in zip(seg.applies, validated.applies):
                        fa = ch.facts.by_seq[rec["seq"]]
                        self.assertEqual((fa.fingerprint, fa.record_id, list(fa.skipped), fa.d),
                                         (applied.fingerprint, applied.record_id, list(applied.skipped), applied.d))
                        self.assertEqual(fa.context, applied.context)

    def test_current_snapshot_equals_the_segment_projection(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        b.declare(D[2], "q1")
        b.restart(D[3], "q2")
        b.apply(D[4], 29.0)
        b.apply(D[6], 31.0)
        h = b.history()
        ch = chain_of(h)
        snap = ch.current_snapshot()
        got = validate_snapshot(snap)
        want = project_segment(ch.segments[-1])
        self.assertEqual([(a.d, a.fingerprint, a.skipped) for a in got.applies],
                         [(a.d, a.fingerprint, a.skipped) for a in want.applies])
        self.assertEqual((got.start_after, got.boundary_session), (D[3], b.events[3]["boundary_session"]))
        # the input hash of every re-attached APPLY equals the one the v2 record carries
        for rec, ev in zip(ch.segments[-1].applies, snap.events[1:]):
            self.assertEqual(ev["input_hash"], rec["input_hash"])
            self.assertNotEqual(ev["seq"], rec["seq"])                 # temporary numbers differ from v2 seqs
        # only the current segment is in the snapshot
        self.assertEqual(len(snap.events), 3)


class ReadChecksTheHistory(unittest.TestCase):
    def test_every_call_validates(self):
        for bad in (None, "x", {"a": 1}):
            e = T.outcome(O.read_effective, bad)
            self.assertEqual(e[:3], ("err", "history_invalid", "history"))
        h = H.example_r().history()
        broken = H.mutated(H.example_r().events, lambda ev: ev[2].update(d="2026-03-30"))
        e = T.outcome(O.read_effective, broken)
        self.assertEqual(e[0], "err")
        self.assertEqual(e[1], "history_invalid")
        # a good history still reads (nothing is cached between the calls)
        self.assertEqual(O.read_effective(h), O.read_effective(h))


class ImmutableAndQuiet(unittest.TestCase):
    def test_accessors_return_copies_and_values_are_frozen(self):
        v = O.read_effective(H.example_r().history())
        a = v.applies
        a[0]["seq"] = 999
        a.append({})
        self.assertNotEqual(v.applies[0]["seq"], 999)
        self.assertEqual(len(v.applies), 6)
        for name in ("segments", "resolutions", "requests", "effective_seqs", "superseded_seqs", "current_boundary"):
            before = T.cj(getattr(v, name))
            x = getattr(v, name)
            if isinstance(x, list) and x:
                x.append("junk")
            elif isinstance(x, dict):
                x["junk"] = 1
            self.assertEqual(T.cj(getattr(v, name)), before)
        with self.assertRaises(AttributeError):
            v.head_seq = 1
        with self.assertRaises(AttributeError):
            del v.head_seq
        with self.assertRaises(TypeError):
            O.EffectiveView()
        self.assertEqual(repr(v), "EffectiveView(head_seq=22, effective=8, segments=1, applies=6, resolutions=0)")


if __name__ == "__main__":
    unittest.main()
