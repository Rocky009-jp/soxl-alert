"""C-2 review probe (read-only): mutation 15 (PUBLISHED_THEN_EXTENDED by the last record hash only). With a valid current
the record hashes chain (event_hash covers seq and the audit-previous hash), so an honest publication cannot tell the two
rules apart; a re-hashed publication whose candidate_digest disagrees with its candidate_head_hash can.
argv[1] = a tree with the trial diff applied."""
import sys, os
ROOT = sys.argv[1]
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
import v2_history_publish as PUB
from v2_history_publish.values import HistoryPublication
D, P, V, H = C.D, C.P, C.V, C.H
b = C.s_gap(); b.w.ledger.append(P.obs("X5", D[5], 50.0)); w = b.w
plan = C.plan(b, 1, [("DROP", 2), (C.CONSUME, D[2]), (C.CONSUME, D[3]), ("REAPPLY", 3)], D[7])
pub = PUB.publish_restore(plan, plan.plan_hash, b.history(), w.sessions, w.ledger, w.series)
base = b.history(); cand = PUB.check_publication(PUB.history_bytes(base), pub)
bc = V.validate_history(base)
# a publication whose candidate is `base` (head = base head), so that `cand` is "base then more records"
body = pub.body
body.update({"expected": {"head_seq": 0, "head_hash": base.events[0]["event_hash"], "history_digest": "1" * 64},
             "records": base.events[1:], "candidate_head_seq": bc.head_seq, "candidate_head_hash": bc.head_hash,
             "candidate_digest": bc.history_digest, "candidate_state_digest": "2" * 64})
honest_like = HistoryPublication._make(body)
print("candidate digest right :", PUB.reconcile_publication(PUB.history_bytes(cand), honest_like).outcome)
body["candidate_digest"] = "3" * 64
wrong = HistoryPublication._make(body)
print("candidate digest wrong :", PUB.reconcile_publication(PUB.history_bytes(cand), wrong).outcome,
      "(the hash-only mutant would say PUBLISHED_THEN_EXTENDED)")
