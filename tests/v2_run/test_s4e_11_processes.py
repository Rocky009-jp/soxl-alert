"""S4E-14: independent processes (2 to 4 at once, ten rounds of each) run `morning --mode live` against one remote with a fake
Discord: the judgment of the day is posted at most once, one version of the market data is pinned, and the day is applied once.
This is the insurance for the case that the concurrency group of the workflow does not hold (the losers stop with
publication_stale or find the key claimed)."""
import json
import os
import unittest

import s4e_helpers as H

D = H.D
DAY, START = "2026-07-28", "2026-07-27"


class Processes(H.D.Case):
    def one_round(self, n):
        work, net = H.Work(self), H.Net(DAY)
        self.assertEqual(work.init(net, "live", start=START).code, 0)
        work.sync_ledger(START, DAY)
        clones = [H.C.Clone(self, work.remote) for _ in range(n)]
        go = os.path.join(clones[0].parent, "go")
        logs = [os.path.join(c.parent, "posted_%d.jsonl" % k) for k, c in enumerate(clones)]
        children = [H.Child({"workdir": c.dir, "go": go, "log": logs[k], "i": k + 1, "day": DAY, "mode": "live"})
                    for k, c in enumerate(clones)]
        for child in children:
            child.ready()
        H.D.S.signal(go)
        results = [child.result() for child in children]
        posted = [t for log in logs for t in H.B.read_lines(log)]
        return work, results, posted

    def test_two_to_four_processes_ten_rounds_each(self):
        tally = {"rounds": 0, "morning_posts": 0, "halt_posts": 0, "stopped": 0, "skipped": 0, "done_sent": 0}
        codes = {}
        for n in (2, 3, 4):
            for index in range(10):
                work, results, posted = self.one_round(n)
                tally["rounds"] += 1
                kinds = [H.B.kind_of(t) for t in posted]
                self.assertLessEqual(kinds.count("morning"), 1, (n, index, results))               # the judgment: at most once
                self.assertLessEqual(len(posted), n, (n, index))
                self.assertEqual(kinds.count("error"), 0, (n, index, results))
                for r in results:
                    self.assertIn(r["delivery"], ("SENT", "SKIPPED_CLAIMED", "SKIPPED_JUDGMENT_EXISTS"), (n, index, r))
                    self.assertEqual(r["exit"], 0, (n, index, r))
                    if r["run_outcome"] != "DONE":
                        codes[r["code"]] = codes.get(r["code"], 0) + 1
                shas = {r["provenance.market_sha256"] for r in results if r["provenance.market_sha256"]}
                self.assertEqual(len(shas), 1, (n, index, results))                                # one version of the data
                pinned = work.remote.blob("v2-market", "market.json")
                self.assertEqual(shas, {H.D.blob_sha256(pinned)}, (n, index))
                self.assertEqual(len(work.remote.log("v2-market")), 1, (n, index))
                history = work.history("v2-state")
                applies = [e["d"] for e in history["events"] if e["kind"] == "APPLY"]
                self.assertEqual(applies, [DAY], (n, index))                                       # the day was applied once
                self.assertEqual(len(history["events"]), 2)
                tally["morning_posts"] += kinds.count("morning")
                tally["halt_posts"] += kinds.count("halt")
                tally["stopped"] += sum(1 for r in results if r["run_outcome"] == "STOPPED")
                tally["skipped"] += sum(1 for r in results if r["delivery"].startswith("SKIPPED"))
                tally["done_sent"] += sum(1 for r in results if r["run_outcome"] == "DONE" and r["delivery"] == "SENT")
        self.assertEqual(tally["rounds"], 30)
        self.assertEqual(tally["done_sent"], tally["morning_posts"])
        print("S4E-14: %s %s" % (json.dumps(tally, sort_keys=True), json.dumps(codes, sort_keys=True)))


if __name__ == "__main__":
    unittest.main()
