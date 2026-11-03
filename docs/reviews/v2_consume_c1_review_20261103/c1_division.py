"""The division of D-2 (ii): a history the checker accepts, with a CONSUME of a day the plan refuses as not freed.
argv[1] = repo root. Read-only."""
import sys, os
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
D, P, V, H = C.D, C.P, C.V, C.H
b = C.s_gap(); b.w.ledger.append(P.obs("X5", D[5], 50.0))
entries = [("REPLAY", 2), ("REAPPLY", 3), (C.CONSUME, D[5])]
try:
    C.plan(b, 1, entries, D[7]); print("plan: READY")
except CoreError as e:
    print("plan:", e.code, getattr(e, "rule", None), e.detail)
events = C.oracle(b, 1, entries, "c1-x", D[7])      # the independent builder writes the same restore anyway
try:
    chk = V.validate_history(H.history_of(events))
    print("checker: accepted, head", chk.head_seq)
except CoreError as e:
    print("checker:", e.code, getattr(e, "rule", None))
