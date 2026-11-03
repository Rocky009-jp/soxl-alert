import sys, os
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
D, P = C.D, C.P
b = C.s_declare(); b.w.ledger.append(P.obs("X5", D[5], 49.0))
try:
    r = C.plan(b, 3, [("DROP", 4), (C.CONSUME, D[3]), (C.CONSUME, D[5]), ("REAPPLY", 5)], D[7]); print("OK", r.status)
except CoreError as e:
    print("REFUSED", e.code, getattr(e, "rule", None), e.detail)
except Exception as e:
    print("CRASH", type(e).__name__, e)
