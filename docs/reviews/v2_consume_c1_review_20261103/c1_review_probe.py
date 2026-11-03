"""C-1 review probes (read-only; run with the repo root as argv[1]). Never writes into the repo."""
import sys, os, traceback
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
D, P, R = C.D, C.P, C.R
CONSUME = C.CONSUME

def outcome(fn, *a, **k):
    try:
        r = fn(*a, **k)
        return ("OK", getattr(r, "status", r))
    except CoreError as e:
        return ("REFUSED", e.code, e.field, getattr(e, "rule", None), e.detail)
    except Exception as e:                       # anything else is an uncaught crash
        return ("CRASH", type(e).__name__, str(e)[:80])

print("dates", len(D), D[0], D[-1])
res = {}
# A: consume the last session of the calendar (no next(D))
b = C.s_tail(); b.w.ledger.append(P.obs("XL", D[-1], 47.0))
res["A_last_session_check_d5"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, D[-1])], D[5])
b = C.s_tail(); b.w.ledger.append(P.obs("XL", D[-1], 47.0))
res["A_last_session_check_dlast"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, D[-1])], D[-1])
# B: consume a day after check_d (has a next session)
b = C.s_tail(); b.w.ledger.append(P.obs("X10", D[10], 47.0))
res["B_after_check_d"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, D[10])], D[5])
# C: the consumed day itself unconfirmed
b = C.s_tail()
res["C_unconfirmed_D"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2])], D[5],
                                 sessions=R.sessions_with(unconfirmed=(D[2],)))
# C2: next(D) unconfirmed
b = C.s_tail()
res["C2_unconfirmed_next"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, D[2])], D[5],
                                  sessions=R.sessions_with(unconfirmed=(D[3],)))
# D: replayed declaration, consume before the reapply (design 3.10 row 5 order)
b = C.s_declare()
res["D_replay_decl_consume_before_reapply"] = outcome(C.plan, b, 3, [("REPLAY", 4), (CONSUME, D[3]), ("REAPPLY", 5)], D[5])
# E: point at the declaration (kept), consume D3 before the reapply
b = C.s_declare()
res["E_kept_decl"] = outcome(C.plan, b, 4, [(CONSUME, D[3]), ("REAPPLY", 5)], D[5])
# F: order: consume after the reapply
b = C.s_declare()
res["F_after_reapply"] = outcome(C.plan, b, 3, [("DROP", 4), ("REAPPLY", 5), (CONSUME, D[3])], D[5])
# G: a day that is no session (weekend)
b = C.s_tail()
res["G_weekend"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, "2026-03-07")], D[5])
# H: day form
b = C.s_tail()
res["H_bad_day"] = outcome(C.plan, b, 1, [("DROP", 2), (CONSUME, "2026-3-7")], D[5])
for k, v in res.items():
    print(k, v)
