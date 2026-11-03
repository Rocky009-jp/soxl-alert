"""C-2 review probe (read-only): integer boundary values of every integer field of a publication (re-hashed with
_make, as C2-14 does), against check_publication and reconcile_publication. argv[1] = a tree with the trial diff."""
import copy, sys, os
ROOT = sys.argv[1]
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
import v2_history_publish as PUB
from v2_history_publish.values import HistoryPublication
D, P, V, H = C.D, C.P, C.V, C.H
b = C.s_gap(); b.w.ledger.append(P.obs("X5", D[5], 50.0)); w = b.w
plan = C.plan(b, 1, [("DROP", 2), (C.CONSUME, D[2]), (C.CONSUME, D[3]), ("REAPPLY", 3)], D[7])
app = PUB.publish_restore(plan, plan.plan_hash, b.history(), w.sessions, w.ledger, w.series)
cand = PUB.check_publication(PUB.history_bytes(b.history()), app)
gen = PUB.publish_genesis(D[0], w.sessions)
rep_body = gen.body; rep_body.update({"mode": "REPLACE", "source": "ADOPTION", "request_id": "c2-r", "plan_hash": "0" * 64,
                                      "expected": PUB.raw_identity(b"broken")})
rep = HistoryPublication._make(rep_body)
VALUES = [-10 ** 6, -50, -5, -2, -1, 0, 1, 2, 3, 50, 10 ** 6, 2 ** 70]
currents = {"base": PUB.history_bytes(b.history()), "cand": PUB.history_bytes(cand), "none": None, "junk": b"\xff{",
            "broken": b"broken"}
paths = {"APPEND": [("candidate_head_seq",), ("expected", "head_seq"), ("records", 0, "seq"), ("records", 1, "seq")],
         "CREATE": [("candidate_head_seq",), ("candidate_history", "head_seq"), ("candidate_history", "events", 0, "seq")],
         "REPLACE": [("candidate_head_seq",), ("expected", "raw_size")]}
leaks = 0; runs = 0
for pub in (app, gen, rep):
    for path in paths[pub.mode]:
        for v in VALUES:
            body = pub.body; node = body
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = v
            forged = HistoryPublication._make(body)
            for cname, cur in currents.items():
                for fn in ("check", "reconcile"):
                    runs += 1
                    try:
                        if fn == "check":
                            PUB.check_publication(cur, forged)
                        else:
                            PUB.reconcile_publication(cur, forged)
                    except CoreError:
                        pass
                    except Exception as e:
                        leaks += 1
                        print("LEAK", pub.mode, "/".join(map(str, path)), v, cname, fn, type(e).__name__)
print("runs", runs, "leaks", leaks)
