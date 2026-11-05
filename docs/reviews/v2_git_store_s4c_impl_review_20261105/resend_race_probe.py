"""Y4: different resend ids at the same time (the implementer's note: one of three ends CLAIM_FAILED every time).
usage: resend_race_probe.py <repo at 13be0d0> <rounds> <n> [<n> ...]
For each n, <rounds> rounds: an UNKNOWN original (the sender timed out), then n children (own clones, one bare remote,
started together by a file) each resend the morning of D with its own id. Counted: the deliveries, the texts sent, the
resend claims left on the remote, and whether a later resend with the id of a CLAIM_FAILED child is refused because a
resend was SENT (REFUSED_ALREADY_SENT) - i.e. what the user sees when they ask again with that id."""
import collections
import os
import sys
import unittest

REPO, ROUNDS, NS = sys.argv[1], int(sys.argv[2]), [int(x) for x in sys.argv[3:]]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_git_store"))
sys.path.insert(0, REPO)
import s4c_helpers as H  # noqa: E402
import test_s4c_06_processes as T  # noqa: E402

B, N, D = H.B, H.N, H.D


class Probe(T.Race):
    def test_rounds(self):
        counts = collections.Counter()
        again = collections.Counter()
        for n in NS:
            for _ in range(ROUNDS):
                self.w = H.world(range(1, T.DAYS + 1))
                self.remote, self.seed = H.start(self, self.w)
                late = B.Sender(TimeoutError("late"))
                self.assertEqual(H.job(self.seed, self.w, T.DAYS, late).delivery, "UNKNOWN")
                specs = [{"mode": "resend", "last": T.DAYS, "rid": "id%d" % i} for i in range(n)]
                results, texts = self.run_children(specs)
                deliveries = tuple(sorted(r["delivery"] for r in results))
                claims = [x for x in self.remote.names(H.OUTBOX) if ".resend-id" in x and x.endswith(".claim.json")]
                counts[(n, len(texts), len(claims), deliveries)] += 1
                for i, r in enumerate(results):
                    if r["delivery"] == "CLAIM_FAILED":
                        report = N.resend(self.seed.outbox, B.Sender(), D[T.DAYS], "morning", "id%d" % i,
                                          H.now_at(T.DAYS))
                        again[(n, report.delivery)] += 1
        print("(n, texts sent, resend claims on the remote, deliveries) -> rounds")
        for k, v in sorted(counts.items()):
            print("  %2d x n=%d sends=%d claims=%d %s" % ((v,) + k))
        print("the same id asked again after CLAIM_FAILED -> delivery")
        for k, v in sorted(again.items()):
            print("  %2d x n=%d %s" % ((v,) + k))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromName("test_rounds", Probe)
    r = unittest.TextTestRunner(verbosity=0).run(suite)
    sys.exit(0 if r.wasSuccessful() else 1)
