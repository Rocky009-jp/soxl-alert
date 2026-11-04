"""Review probe X2: DECLARE_MISSING / ACK between the head and the target, and the restart boundary itself."""
import os, sys
from datetime import datetime
ROOT, HERE = sys.argv[1], os.path.dirname(os.path.abspath(__file__))
for p in (ROOT, os.path.join(ROOT, "tests", "v2_history"), os.path.join(ROOT, "tests", "v2_persistence"), HERE):
    sys.path.insert(0, p)
import h_helpers as H
import p_helpers as P
from s4r_fakestore import MemStore
from v2_history_ops import read_effective
from v2_daily_run import run_morning
D, TZ = P.DATES, P.TZ
def morning(d):
    y, m, dd = (int(x) for x in d.split("-")); return datetime(y, m, dd, 18, 0, tzinfo=TZ)
# (a) APPLY D1, DECLARE_MISSING D2, decisions for D3 and D4 recorded; run after D4 closes
b = H.HB(); b.apply(D[1], 27.0); b.declare(D[2], "decl-1", check_d=D[3])
w = b.w; w.ledger += [P.obs("R3", D[3], 31.0), P.obs("R4", D[4], 30.0)]
v = read_effective(b.history()); print("a view latest=%s after=%s" % (v.latest_apply_d, v.processing_after))
st = MemStore(b.history()); r = run_morning(st, morning(D[4]), w.series, w.sessions, w.ledger); print("a", r)
print("  gap line:", [l for l in r.message.splitlines() if "欠測" in l or "途切" in l][:3])
# (b) restart at D3 made on the morning after D3 closed; run on that same morning (target == boundary)
b = H.HB(); b.apply(D[1], 27.0); b.apply(D[2], 28.0); b.restart(D[3], "rs-1", check_d=D[3])
w = b.w; st = MemStore(b.history())
import v2_daily_run.run as RUN
src = open(RUN.__file__, encoding="utf-8").read().replace("view.latest_apply_d or view.processing_after", "view.processing_after")
ns = {"__name__": "patched"}; exec(compile(src, "patched_run", "exec"), ns)
print("b trial  ", run_morning(st, morning(D[3]), w.series, w.sessions, w.ledger))
print("b patched", ns["run_morning"](st, morning(D[3]), w.series, w.sessions, w.ledger))
# (c) genesis only, run after the start_after session closes
b = H.HB(); w = b.w; st = MemStore(b.history())
print("c genesis, target == start_after:", run_morning(st, morning(w.start_after), w.series, w.sessions, w.ledger))
