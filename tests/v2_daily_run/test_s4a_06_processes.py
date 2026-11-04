"""S4A-13 (b): two to four independent processes run the same morning at the same moment (they start when a file
appears). Every report is DONE or a STOPPED whose code is store_busy or publication_stale; no day is saved twice; the
file is a first part of the one-run result (all of it when any run says DONE); one more run then gives the one-run
result. All outcomes of the race are allowed; only these facts are asserted."""
import os
import unittest

import s4a_helpers as S

D, P = S.D, S.P
DAYS = 8
ALLOWED_STOPS = ("store_busy", "publication_stale")


class Race(S.RootCase):
    def run_children(self, n):
        w = P.World(0)
        S.decide(w, range(1, DAYS + 1))
        S.real_store(self.root, w)
        go = os.path.join(self.root + "_signal")
        self.addCleanup(lambda: os.path.exists(go) and os.unlink(go))
        spec = {"root": self.root, "last": DAYS, "decisions": list(range(1, DAYS + 1)), "go": go}
        kids = [S.Child(spec) for _ in range(n)]
        try:
            for kid in kids:
                kid.ready()
            S.signal(go)
            return w, [kid.result() for kid in kids]
        finally:
            for kid in kids:
                if kid.proc.poll() is None:
                    kid.proc.kill()
                    kid.proc.communicate()

    def check(self, n):
        w, reports = self.run_children(n)
        for r in reports:
            self.assertIn(r["outcome"], ("DONE", "STOPPED"), r)
            if r["outcome"] == "STOPPED":
                self.assertIn(r["code"], ALLOWED_STOPS, r)
        applied = S.applies_of(self.root)
        self.assertEqual(len(applied), len(set(applied)), "a day was saved twice")
        self.assertEqual(applied, [D[i] for i in range(1, len(applied) + 1)])      # a first part, in order
        full = S.expected_bytes(w, DAYS)
        prefixes = [S.expected_bytes(w, k) for k in range(0, DAYS + 1)]
        self.assertIn(S.raw(self.root), prefixes)
        if any(r["outcome"] == "DONE" for r in reports):
            self.assertEqual(S.raw(self.root), full)
        self.assertFalse([name for name in os.listdir(self.root) if name != S.HIST])       # no lock, no leftover
        after = S.run(S.real_store(self.root, w, initialize=False), w, S.now_at(D[DAYS]))
        self.assertEqual(after.outcome, "DONE")
        self.assertEqual(S.raw(self.root), full)
        return reports

    def test_two_processes(self):
        self.check(2)

    def test_three_processes(self):
        self.check(3)

    def test_four_processes(self):
        self.check(4)


if __name__ == "__main__":
    unittest.main()
