"""Change #1 and #3 of the result's section 5, on the tree given as argv[1] (trial or implementation). Read-only."""
import sys, os
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
D, P, R = C.D, C.P, C.R
CONSUME = C.CONSUME
import v2_history_restore as Z
print("runtime from", os.path.dirname(Z.__file__))
def outcome(fn, *a, **k):
    try:
        r = fn(*a, **k); return ("OK", getattr(r, "status", r))
    except CoreError as e:
        return ("REFUSED", e.code, getattr(e, "rule", None), e.detail)
    except Exception as e:
        return ("CRASH", type(e).__name__, str(e)[:60])
b, s, ses, ser = C.s_calendar()
print("#1 calendar CONSUME S before REAPPLY D11:", outcome(C.plan, b, 1, [(CONSUME, s), ("REAPPLY", 2)], D[13], sessions=ses, series=ser))
print("#1 calendar no CONSUME:", outcome(C.plan, b, 1, [("REAPPLY", 2)], D[13], sessions=ses, series=ser))
# #3: tamper only the ops of a CONSUME plan (re-hashed) -> mismatch expected
b = C.s_declare()
p = C.plan(b, 3, [("DROP", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
def tamper(data):
    ops = data["ops"]
    ops[1], ops[0] = ops[0], ops[1]
f = R.refreshed(p, tamper)
print("#3 swapped ops (rehashed):", outcome(R.confirm, f, b.history(), b.w))
def tamper2(data):
    data["ops"][1]["d"] = D[2]
f = R.refreshed(p, tamper2)
print("#3 changed consume day (rehashed):", outcome(R.confirm, f, b.history(), b.w))
