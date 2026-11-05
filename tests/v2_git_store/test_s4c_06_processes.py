"""S4C-14: two to four independent processes, each with its own clone, start at the same moment (when a file appears) and run
against one bare remote, ten rounds for each number of processes. (a) the same morning job: at most one judgment and at
most one no-judgment notice per day; (b) the history has at most one APPLY per day; (c) every no-judgment notice carries the
note for a run at the same time; one healthy run afterwards leaves exactly one judgment; (d) the same resend id at the same
time: at most one send. All outcomes of a race are allowed; only these facts are asserted. (The counts of one longer run are
written into the result document by the race report script.)"""
import json
import tempfile
import unittest

import s4c_helpers as H

S, N, D, B = H.S, H.N, H.D, H.B

DAYS = 4
CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"
ROUNDS = 10
LINE = "【再送】元の通知の送信を確認できなかったため、同じ内容を送ります"


class Race(H.Case):
    def fresh(self):
        self.w = H.world(range(1, DAYS + 1))
        self.remote, self.seed = H.start(self, self.w)

    def run_children(self, specs):
        signal = tempfile.mkdtemp(prefix="v2s4c_sig_")
        self.addCleanup(H.shutil.rmtree, signal, True)
        go = H.os.path.join(signal, "go")
        logs, kids = [], []
        for i, spec in enumerate(specs):
            clone = H.Clone(self, self.remote)
            log = H.os.path.join(signal, "sent%d.log" % i)
            logs.append(log)
            kids.append(H.Child(dict(spec, go=go, log=log, clone=clone.dir, parent=clone.parent, i=spec.get("i", i))))
        try:
            for kid in kids:
                kid.ready()
            S.signal(go)
            results = [kid.result() for kid in kids]
        finally:
            for kid in kids:
                if kid.proc.poll() is None:
                    kid.proc.kill()
                    kid.proc.communicate()
        return results, [t for log in logs for t in B.read_lines(log)]

    def applies(self):
        data = json.loads(self.remote.blob(H.STATE, "history.json").decode("utf-8"))
        return [e["d"] for e in data["events"] if e["kind"] == "APPLY"]

    def check_job_round(self, n, shift):
        self.fresh()
        spec = {"mode": "job", "last": DAYS, "decisions": list(range(1, DAYS + 1))}
        results, texts = self.run_children([dict(spec, i=(i if shift else 0)) for i in range(n)])
        kinds = [B.kind_of(t) for t in texts]
        self.assertLessEqual(kinds.count("morning"), 1, (kinds, results))                  # (a)
        self.assertLessEqual(kinds.count("halt"), 1, (kinds, results))
        self.assertEqual(kinds.count("error"), 0, (kinds, results))
        applied = self.applies()
        self.assertEqual(len(applied), len(set(applied)), applied)                          # (b)
        self.assertEqual(applied, [D[i] for i in range(1, DAYS + 1)][:len(applied)])
        for text in texts:
            if B.kind_of(text) == "halt":
                self.assertIn(CONCURRENT, text)                                              # (c)
        for r in results:
            self.assertIn(r["run_outcome"], ("DONE", "STOPPED"))
            if r["run_outcome"] == "STOPPED":
                self.assertEqual(r["code"], "publication_stale", results)
        # one healthy run afterwards leaves exactly one judgment (the winner's, or its own)
        sender = B.Sender()
        report = H.job(self.seed, self.w, DAYS, sender)
        self.assertEqual(report.run_outcome, "DONE")
        self.assertEqual(kinds.count("morning") + [B.kind_of(t) for t in sender.texts].count("morning"), 1)
        self.assertEqual(self.applies(), [D[i] for i in range(1, DAYS + 1)])
        entries = N.outbox_status(self.seed.outbox, D[DAYS])
        self.assertEqual(entries[0].status, "SENT")
        outcome = (n, tuple(sorted(kinds)), tuple(sorted((r["run_outcome"], r["delivery"]) for r in results)))
        return outcome

    def test_a_b_c_the_morning_job_in_two_to_four_processes(self):
        seen = {}
        for n in (2, 3, 4):
            for _ in range(ROUNDS):
                key = self.check_job_round(n, shift=True)
                seen[key] = seen.get(key, 0) + 1
        for n in (2, 3, 4):
            self.assertTrue(any(k[0] == n and "halt" in k[1] and "morning" in k[1] for k in seen), n)   # the race happens

    def test_a_b_the_same_clock_may_make_the_same_commit_and_the_facts_hold_all_the_same(self):
        for _ in range(ROUNDS):
            self.check_job_round(2, shift=False)

    def test_d_the_same_resend_id_at_the_same_time_sends_at_most_once(self):
        for n in (2, 3, 4):
            for _ in range(ROUNDS // 2):
                self.w = H.world(range(1, DAYS + 1))
                self.remote, self.seed = H.start(self, self.w)
                late = B.Sender(TimeoutError("late"))
                self.assertEqual(H.job(self.seed, self.w, DAYS, late).delivery, "UNKNOWN")
                spec = {"mode": "resend", "last": DAYS, "rid": "same"}
                results, texts = self.run_children([dict(spec) for _ in range(n)])
                self.assertLessEqual(len(texts), 1, results)
                deliveries = sorted(r["delivery"] for r in results)
                self.assertEqual(deliveries.count("SENT"), len(texts))
                for d in deliveries:
                    self.assertIn(d, ("SENT", "SKIPPED_CLAIMED", "CLAIM_FAILED", "REFUSED_ALREADY_SENT"))
                claims = [x for x in self.remote.names(H.OUTBOX) if x.endswith(".resend-same.claim.json")]
                self.assertLessEqual(len(claims), 1)
                self.assertLessEqual(len(texts), len(claims))
                for text in texts:
                    self.assertTrue(text.startswith(LINE + "\n"))

    def test_d_different_ids_at_the_same_time_each_id_sends_at_most_once(self):
        for _ in range(ROUNDS // 2):
            self.w = H.world(range(1, DAYS + 1))
            self.remote, self.seed = H.start(self, self.w)
            late = B.Sender(TimeoutError("late"))
            self.assertEqual(H.job(self.seed, self.w, DAYS, late).delivery, "UNKNOWN")
            specs = [{"mode": "resend", "last": DAYS, "rid": "id%d" % i} for i in range(3)]
            results, texts = self.run_children(specs)
            self.assertLessEqual(len(texts), 3)
            self.assertEqual(sorted(r["delivery"] for r in results).count("SENT"), len(texts))
            claims = sorted(x for x in self.remote.names(H.OUTBOX) if ".resend-id" in x and x.endswith(".claim.json"))
            self.assertLessEqual(len(claims), 3)
            self.assertLessEqual(len(texts), len(claims))                                   # each id sends at most once
            for text in texts:
                self.assertTrue(text.startswith(LINE + "\n"))


if __name__ == "__main__":
    unittest.main()
