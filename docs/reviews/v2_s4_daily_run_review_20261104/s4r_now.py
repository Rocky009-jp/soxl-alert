"""Review probe X4: what the trial runner does with `now` beyond choosing the target (delayed run, future observation)."""
import os, sys
from datetime import datetime
ROOT, HERE = sys.argv[1], os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, "tests", "v2_history"), os.path.join(ROOT, "tests", "v2_persistence"), HERE):
    sys.path.insert(0, p)
import h_helpers as H
import p_helpers as P
from s4r_fakestore import MemStore
from v2_daily_run import run_morning
D, TZ = P.DATES, P.TZ
def at(d, h, m=0):
    y, mo, dd = (int(x) for x in d.split("-")); return datetime(y, mo, dd, h, m, tzinfo=TZ)
# (a) a run delayed into the next session (after D4 opened at 09:00, before it closes at 16:00): target D3
b = H.HB(); b.apply(D[1], 27.0); b.apply(D[2], 28.0); w = b.w
r = run_morning(MemStore(b.history()), at(D[4], 11), w.series, w.sessions, w.ledger)
print("a delayed run:", r, "| next open of D3 passed:", w.sessions.next(D[3]).open_at < at(D[4], 11))
print("  run class line:", r.message.splitlines()[0])
print("  has branch table lines:", any("分岐" in l or "なら" in l for l in r.message.splitlines()))
# (b) a decision for D3 whose observed_at (20:00 on D3) is after now (18:00 on D3)
b = H.HB(); b.apply(D[1], 27.0); b.apply(D[2], 28.0); w = b.w
w.ledger.append(P.obs("R3", D[3], 22.0, hour=20))
r = run_morning(MemStore(b.history()), at(D[3], 18), w.series, w.sessions, w.ledger)
print("b observation after now:", r)
