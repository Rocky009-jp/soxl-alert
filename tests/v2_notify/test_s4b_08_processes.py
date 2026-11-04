"""S4B-15: two to four independent processes start at the same moment (when a file appears). (a) the same morning job:
at most one judgment and at most one no-judgment notice per day, the no-judgment notice carries the note for a run at
the same time (the trial's T-3), and one healthy run afterwards leaves exactly one judgment; (b) the same resend id: one
send; (c) different resend ids: each id sends at most once (the contract of the upper design 5.3: an UNKNOWN original may
be sent once per id). All outcomes of a race are allowed; only these facts are asserted."""
import os
import shutil
import tempfile
import unittest

import s4b_helpers as H

N, S, D = H.N, H.S, H.D

DAYS = 4
CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"
REPETITIONS = 4


class Race(H.Case):
    def start(self, specs):
        go = os.path.join(self.hroot + "_signal")
        self.addCleanup(lambda: os.path.exists(go) and os.unlink(go))
        logs = []
        kids = []
        for i, spec in enumerate(specs):
            log = os.path.join(self.oroot + "_log%d" % i)
            self.addCleanup(lambda p=log: os.path.exists(p) and os.unlink(p))
            logs.append(log)
            kids.append(H.Child(dict(spec, go=go, log=log, hist=self.hroot, out=self.oroot)))
        try:
            for kid in kids:
                kid.ready()
            H.signal(go)
            return [kid.result() for kid in kids], logs
        finally:
            for kid in kids:
                if kid.proc.poll() is None:
                    kid.proc.kill()
                    kid.proc.communicate()

    def fresh(self):
        shutil.rmtree(self.hroot, True)
        shutil.rmtree(self.oroot, True)
        self.hroot, self.oroot = tempfile.mkdtemp(prefix="v2s4b_hist_"), tempfile.mkdtemp(prefix="v2s4b_out_")
        self.addCleanup(shutil.rmtree, self.hroot, True)
        self.addCleanup(shutil.rmtree, self.oroot, True)
        self.w = H.P.World(0)
        S.decide(self.w, range(1, DAYS + 1))
        self._store = None

    def texts_of(self, logs):
        return [t for log in logs for t in H.read_lines(log)]

    def test_the_morning_job_in_two_to_four_processes(self):
        for n in (2, 3, 4):
            for _ in range(REPETITIONS):
                self.fresh()
                self.store()
                spec = {"mode": "job", "last": DAYS, "decisions": list(range(1, DAYS + 1))}
                results, logs = self.start([spec] * n)
                texts = self.texts_of(logs)
                kinds = [H.kind_of(t) for t in texts]
                self.assertLessEqual(kinds.count("morning"), 1, (n, kinds))
                self.assertLessEqual(kinds.count("halt"), 1, (n, kinds))
                self.assertEqual(kinds.count("error"), 0)
                for r in results:
                    self.assertIn(r["kind"], ("morning", "halt"), r)
                    if r["kind"] == "halt":
                        self.assertIn(r["code"], ("store_busy", "publication_stale"), r)
                for text in texts:
                    if H.kind_of(text) == "halt":
                        self.assertIn(CONCURRENT, text.splitlines())
                self.assertEqual(sum(1 for r in results if r["delivery"] == "SENT"), len(texts))
                self.assertFalse([name for name in os.listdir(self.hroot) if name != S.HIST])         # no lock, no leftover
                # the outbox holds at most one claim per key and a result for each
                claims = [name for name in H.names(self.oroot) if name.endswith(".claim.json")]
                self.assertEqual(sorted(claims), sorted(set(claims)))
                # a healthy run afterwards: exactly one judgment of the day in total
                sender = H.Sender()
                report = N.morning_job(S.real_store(self.hroot, self.w, initialize=False), self.outbox(), sender,
                                       H.now_at(D[DAYS]), self.w.series, self.w.sessions, self.w.ledger)
                total = kinds.count("morning") + [H.kind_of(t) for t in sender.texts].count("morning")
                self.assertEqual(total, 1, (n, kinds, report))
                self.assertEqual(report.exit_code, 0)

    def prepare_unknown_original(self):
        self.fresh()
        S.real_store(self.hroot, self.w)
        report = N.morning_job(S.real_store(self.hroot, self.w, initialize=False), self.outbox(), H.Sender(TimeoutError("late")),
                               H.now_at(D[DAYS]), self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual(report.delivery, "UNKNOWN")

    def test_the_same_resend_id_in_two_to_four_processes_sends_once(self):
        for n in (2, 3, 4):
            for _ in range(REPETITIONS):
                self.prepare_unknown_original()
                spec = {"mode": "resend", "last": DAYS, "decisions": list(range(1, DAYS + 1)), "rid": "same"}
                results, logs = self.start([spec] * n)
                self.assertEqual(len(self.texts_of(logs)), 1, (n, results))
                self.assertEqual(sum(1 for r in results if r["delivery"] == "SENT"), 1, results)
                for r in results:
                    # REFUSED_DAMAGED: the other process's claim was read while it was being written (a safe refusal)
                    self.assertIn(r["delivery"], ("SENT", "SKIPPED_CLAIMED", "REFUSED_ALREADY_SENT", "REFUSED_DAMAGED"), r)

    def test_different_resend_ids_in_two_to_four_processes_send_at_most_once_per_id(self):
        for n in (2, 3, 4):
            for _ in range(REPETITIONS):
                self.prepare_unknown_original()
                specs = [{"mode": "resend", "last": DAYS, "decisions": list(range(1, DAYS + 1)), "rid": "id%d" % i}
                         for i in range(n)]
                results, logs = self.start(specs)
                sent = len(self.texts_of(logs))
                self.assertGreaterEqual(sent, 1, results)
                self.assertLessEqual(sent, n, results)
                claims = [name for name in H.names(self.oroot) if ".resend-" in name and name.endswith(".claim.json")]
                self.assertEqual(len(claims), sent, (claims, results))                    # one claim per send, none without
                self.assertEqual(sum(1 for r in results if r["delivery"] == "SENT"), sent)
                for r in results:
                    # REFUSED_DAMAGED: another id's claim was read while it was being written (a safe refusal, asked again later)
                    self.assertIn(r["delivery"], ("SENT", "REFUSED_ALREADY_SENT", "REFUSED_DAMAGED"), r)


if __name__ == "__main__":
    unittest.main()
