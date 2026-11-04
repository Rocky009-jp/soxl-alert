"""Review probe X5: a calendar that ends before `now` (the runner must not fall back to an old day)."""
import os, sys
from datetime import datetime
ROOT, HERE = sys.argv[1], os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, "tests", "v2_history"), os.path.join(ROOT, "tests", "v2_persistence"), HERE):
    sys.path.insert(0, p)
import h_helpers as H
import p_helpers as P
from v2_core.sessions import SessionList
from s4r_fakestore import MemStore
from v2_daily_run import run_morning
D, TZ = P.DATES, P.TZ
def at(d, h):
    y, mo, dd = (int(x) for x in d.split("-")); return datetime(y, mo, dd, h, 0, tzinfo=TZ)
b = H.HB(); b.apply(D[1], 27.0); b.apply(D[2], 28.0); w = b.w
short = SessionList([s for s in w.sessions.sessions if s.date <= D[6]])   # the calendar ends at D6
for k in (5, 6, 9):
    r = run_morning(MemStore(b.history()), at(D[k], 18), w.series, short, w.ledger)
    print("now = after D%d close, calendar ends at D6:" % k, r)
