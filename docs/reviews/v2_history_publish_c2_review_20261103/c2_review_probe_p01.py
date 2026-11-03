"""C-2 review probe (read-only): P-01 paths on the trial build, the documented limit of check_publication, and the
reconcile_publication boundary of a negative candidate_head_seq. argv[1] = a tree with the trial diff applied."""
import copy, sys, os
ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
from v2_persistence.codec import canonical_json, sha256_text
import v2_history_publish as PUB
from v2_history_publish.values import HistoryPublication
from v2_history_ops.values import digest_of
from v2_history_restore import RestorePlan, RestoreConfirmResult, CONFIRMED_IN_MEMORY
D, P, V, H = C.D, C.P, C.V, C.H

def out(tag, fn):
    try:
        r = fn(); print(tag, "->", "OK", r if not hasattr(r, "summary") else r.summary()["mode"])
    except CoreError as e:
        print(tag, "->", e.code, getattr(e, "rule", None))
    except Exception as e:                      # an unexpected exception is the finding
        print(tag, "-> UNEXPECTED", type(e).__name__, e)

b = C.s_gap(); b.w.ledger.append(P.obs("X5", D[5], 50.0))
bad_entries = [("REPLAY", 2), ("REAPPLY", 3), (C.CONSUME, D[5])]
out("plan(bad)", lambda: C.plan(b, 1, bad_entries, D[7]))
bad = H.history_of(C.oracle(b, 1, bad_entries, "c1-x", D[7]))
out("checker(bad)", lambda: V.validate_history(bad).head_seq)

# a READY plan on the same base
good = None
for entries in ([("REPLAY", 2), ("REAPPLY", 3)], [("REPLAY", 2), (C.CONSUME, D[2]), (C.CONSUME, D[3]), ("REAPPLY", 3)],
                [("DROP", 2), (C.CONSUME, D[2]), (C.CONSUME, D[3]), ("REAPPLY", 3)]):
    try:
        good = C.plan(b, 1, entries, D[7]); print("READY plan with", entries); break
    except CoreError as e:
        print("not ready", entries, e.code, getattr(e, "rule", None))
w = b.w
if good is not None:
    out("publish_restore(good)", lambda: PUB.publish_restore(good, good.plan_hash, b.history(), w.sessions, w.ledger, w.series))
    # (a) the basis rewritten to the bad history, rehashed
    view = good.to_dict(); basis = view["basis"]
    keys = [k for k in basis if "candidate" in k]
    print("candidate keys in basis:", keys)
    chk = V.validate_history(bad)
    for k in keys:
        if k == "candidate_history": basis[k] = bad.to_dict()
        elif k == "candidate_digest": basis[k] = bad.digest
        elif k == "candidate_head_seq": basis[k] = chk.head_seq
        elif k == "candidate_head_hash": basis[k] = chk.head_hash
        elif k == "candidate_state_digest": basis[k] = chk.state_digest
    forged = RestorePlan.from_dict({"basis": basis, "plan_hash": sha256_text(canonical_json(basis))})
    out("(a) forged plan", lambda: PUB.publish_restore(forged, forged.plan_hash, b.history(), w.sessions, w.ledger, w.series))
# (b) a result object instead of a plan
res = RestoreConfirmResult(CONFIRMED_IN_MEMORY, bad, "0" * 64)
out("(b) result object", lambda: PUB.publish_restore(res, "0" * 64, b.history(), w.sessions, w.ledger, w.series))

# (c) the documented limit: a value made with _make outside build.py is accepted by check_publication
base = b.history(); bchk = V.validate_history(base)
n = len(base.events)
body = {"operation": "soxl-v2-history-publication/1", "mode": "APPEND", "source": "RESTORE", "d": None,
        "request_id": "c1-x", "plan_hash": "0" * 64,
        "expected": {"head_seq": bchk.head_seq, "head_hash": bchk.head_hash, "history_digest": bchk.history_digest},
        "source_v1": None, "records": bad.events[n:], "candidate_history": None,
        "candidate_head_seq": chk.head_seq, "candidate_head_hash": chk.head_hash, "candidate_digest": bad.digest,
        "candidate_state_digest": chk.state_digest}
fake = HistoryPublication._make(body)
cur = PUB.history_bytes(base)
out("(c) check_publication(_make of the bad history)", lambda: PUB.check_publication(cur, fake) == bad)

# reconcile: candidate_head_seq negative (re-hashed) against a short current history
for hs in (-1, -2, -5, -50):
    body2 = copy.deepcopy(body); body2["candidate_head_seq"] = hs
    p2 = HistoryPublication._make(body2)
    out("reconcile head_seq=%d (current %d records)" % (hs, n), lambda: PUB.reconcile_publication(cur, p2).outcome)
    out("check     head_seq=%d" % hs, lambda: PUB.check_publication(cur, p2))
