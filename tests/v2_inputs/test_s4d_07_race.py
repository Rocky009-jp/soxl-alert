"""S4D-13: two runs that pin the same target day end on the same bytes. A loser reads the winner's pin; a push of unknown
result is judged by reading the ref again; a remote that refuses the ref is a returned failure; independent processes
(2 to 4 at once, ten rounds of each) pin one version and send at most one verdict."""
import json
import os
import unittest

import s4d_helpers as H

I = H.I
D = "2026-07-28"
START = "2026-07-27"


class Pair(H.Case):
    def test_the_loser_of_a_race_uses_the_winners_version(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        other = rig.another()
        now = H.jst_morning(D)
        seen = {}

        def before(symbol):
            if symbol == "SOXL" and "other" not in seen:
                seen["other"] = I.load_inputs(other.git, H.Provider(D, scale=1.002), now, H.REFS, H.C.clock)

        mine = I.load_inputs(rig.clone.git, H.Provider(D, before=before), now, H.REFS, H.C.clock)
        theirs = seen["other"]
        again = I.load_inputs(other.git, H.Provider(D), now, H.REFS, H.C.clock)
        self.see(mine, theirs)
        self.assertIsNone(mine.failure)
        self.assertEqual((theirs.provenance["pinned_by"], mine.provenance["pinned_by"]), ("this", "other"))
        pinned = rig.remote.blob("v2-market", "market.json")
        for inp in (mine, theirs, again):
            self.assertEqual(inp.provenance["market_sha256"], H.blob_sha256(pinned))
        self.assertEqual(again.provenance["pinned_by"], "existing")
        self.assertEqual(mine.series.row(D), theirs.series.row(D))
        self.assertEqual(mine.series.soxx[-1], H.research(D)["SOXX"][D][1] * 1.002)       # the winner's revised value
        self.assertEqual(len(rig.remote.log("v2-market")), 1)
        # one verdict: the loser's morning finds the day claimed
        first = H.N.morning_job(I.guarded_store(rig.clone.hist, mine.failure), rig.clone.outbox, rig.sender, now,
                                mine.series, mine.sessions, mine.raw_observations)
        second = H.N.morning_job(I.guarded_store(other.hist, theirs.failure), other.outbox, rig.sender, now,
                                 theirs.series, theirs.sessions, theirs.raw_observations)
        self.assertEqual((first.run_outcome, first.kind, first.delivery), ("DONE", "morning", "SENT"))
        self.assertEqual(second.delivery, "SKIPPED_CLAIMED")
        self.assertEqual(rig.sent_kinds(), ["morning"])

    def test_a_push_of_unknown_result_that_arrived_is_read_again_and_its_version_used(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        git = H.C.Lost(rig.clone.dir, nth=1, deliver=True)
        inp, now = rig.inputs(D, H.Provider(D), git=git)
        self.assertIsNone(inp.failure)
        self.assertEqual(git.names().count("push"), 1)                          # not repeated
        self.assertEqual(inp.provenance["pinned_by"], "other")                  # read again after the unknown answer
        pinned = rig.remote.blob("v2-market", "market.json")
        self.assertEqual(inp.provenance["market_sha256"], H.blob_sha256(pinned))
        self.assertEqual(inp.provenance["market_commit"], rig.remote.sha("v2-market"))
        self.assertEqual(len(rig.remote.log("v2-market")), 1)

    def test_a_push_of_unknown_result_that_arrived_and_a_later_day_followed(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        other = rig.another()
        later = "2026-07-29"

        def after():
            I.load_inputs(other.git, H.Provider(later), H.jst_morning(later), H.REFS, H.C.clock)

        git = H.C.Lost(rig.clone.dir, nth=1, deliver=True, after=after)
        inp, now = rig.inputs(D, H.Provider(D), git=git)
        self.assertIsNone(inp.failure)
        self.assertEqual(inp.provenance["market_through"], later)               # the newer pin reaches this day: used
        self.assertEqual(len(rig.remote.log("v2-market")), 2)

    def test_a_push_that_took_a_long_time_but_arrived(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        rig.remote.hook("post-receive", "[ -e ./slept ] || { touch ./slept; sleep 4; }")
        slow = H.C.Clone(self, rig.remote, git_cls=H.C.Spy, timeout=2)
        inp, now = rig.inputs(D, H.Provider(D), git=slow.git)
        self.see(inp)
        self.assertIsNone(inp.failure)
        self.assertEqual(slow.git.names().count("push"), 1)
        self.assertEqual(inp.provenance["market_sha256"], H.blob_sha256(rig.remote.blob("v2-market", "market.json")))

    def test_a_push_of_unknown_result_that_did_not_arrive_is_a_returned_failure(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        git = H.C.Lost(rig.clone.dir, nth=1, deliver=False)
        report, inp = rig.morning(D, H.Provider(D), git=git)
        self.assertEqual((inp.failure.code, inp.failure.field), ("input_market_pin_failed", "market"))
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery),
                         ("STOPPED", "input_market_pin_failed", "halt", "SENT"))
        self.assertIsNone(rig.remote.sha("v2-market"))
        self.assertEqual(git.names().count("push"), 1)                          # not repeated

    def test_a_remote_that_refuses_the_ref_is_a_pin_failure_and_a_halt_notice(self):
        rig = H.Rig(self, start=START)
        rig.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/v2-market ] && exit 1; done; exit 0')
        provider = H.Provider(D)
        report, inp = rig.morning(D, provider)
        self.see(report, inp)
        self.assertEqual((inp.failure.code, inp.failure.field), ("input_market_pin_failed", "market"))
        self.assertEqual(provider.calls, 4)
        self.assertEqual((report.run_outcome, report.kind, report.delivery), ("STOPPED", "halt", "SENT"))
        self.assertIsNone(rig.remote.sha("v2-market"))
        self.assertEqual(len(rig.remote.log("v2-state")), 1)
        self.assertNoMark()

    def test_a_loser_whose_winner_is_older_than_its_day_fails_and_does_not_repeat(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        other = rig.another()
        earlier = "2026-07-27"
        now = H.jst_morning(D)

        def before(symbol):
            if symbol == "SOXL" and not rig.remote.sha("v2-market"):
                I.load_inputs(other.git, H.Provider(earlier), H.jst_morning(earlier), H.REFS, H.C.clock)

        git = H.C.Spy(rig.clone.dir)
        inp = I.load_inputs(git, H.Provider(D, before=before), now, H.REFS, H.C.clock)
        # this run read no ref, so its commit has no parent and the ref exists now: the push is refused; the pin it reads
        # again is 07-27, older than this day, so the run fails instead of using it, and it does not push again
        self.assertEqual((inp.failure.code, inp.failure.field), ("input_market_pin_failed", "market"))
        self.assertEqual(git.names().count("push"), 1)
        self.assertEqual(len(rig.remote.log("v2-market")), 1)
        self.assertEqual(json.loads(rig.remote.blob("v2-market", "market.json"))["through"], earlier)
        self.assertEqual(inp.provenance.get("pinned_by"), None)


class Processes(H.Case):
    def one_round(self, n, index):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        children, clones = [], [rig.another() for _ in range(n)]
        logs = [os.path.join(clones[k].parent, "sent_%d.jsonl" % k) for k in range(n)]
        go = os.path.join(rig.clone.parent, "go")
        for k, clone in enumerate(clones):
            children.append(H.Child({"clone": clone.dir, "parent": clone.parent, "go": go, "log": logs[k], "i": k + 1,
                                     "day": D, "scale": 1.0 + 0.001 * k}))
        for child in children:
            child.ready()
        H.S.signal(go)
        results = [child.result() for child in children]
        sent = [t for log in logs for t in H.B.read_lines(log)]
        pinned = rig.remote.blob("v2-market", "market.json")
        history = json.loads(rig.remote.blob("v2-state", "history.json").decode("utf-8"))
        applies = [e["d"] for e in history["events"] if e["kind"] == "APPLY"]
        return results, sent, pinned, applies, rig

    def test_two_to_four_processes_ten_rounds_each_pin_one_version_and_send_at_most_one_verdict(self):
        tally = {"rounds": 0, "pinned": 0, "this": 0, "other": 0, "existing": 0, "verdicts": 0, "halts": 0, "stopped": 0}
        codes = {}
        for n in (2, 3, 4):
            for index in range(10):
                results, sent, pinned, applies, rig = self.one_round(n, index)
                tally["rounds"] += 1
                self.assertIsNotNone(pinned, (n, index))
                self.assertEqual({r["failure"] for r in results}, {None}, (n, index, results))
                self.assertEqual({r["sha"] for r in results}, {H.blob_sha256(pinned)}, (n, index))
                self.assertLessEqual([r["pinned_by"] for r in results].count("this"), 1, (n, index))
                self.assertEqual(len(rig.remote.log("v2-market")), 1)
                kinds = [H.B.kind_of(t) for t in sent]
                self.assertLessEqual(kinds.count("morning"), 1, (n, index, results))
                self.assertLessEqual(kinds.count("halt"), n - 1, (n, index, results))
                self.assertEqual(applies, [D], (n, index))                      # the day was applied once
                for r in results:
                    tally[r["pinned_by"]] += 1
                tally["verdicts"] += kinds.count("morning")
                tally["stopped"] += sum(1 for r in results if r["run_outcome"] != "DONE")
                tally["halts"] += kinds.count("halt")
                for r in results:
                    if r["run_outcome"] != "DONE":
                        codes[r["code"]] = codes.get(r["code"], 0) + 1
                tally["pinned"] += 1
        self.assertEqual(tally["rounds"], 30)
        print("S4D-13(d): %s %s" % (json.dumps(tally, sort_keys=True), json.dumps(codes, sort_keys=True)))


if __name__ == "__main__":
    unittest.main()
