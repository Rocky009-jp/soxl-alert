"""Review probe X1: the trial runner after a RESTART_UNKNOWN (S3-B-3) on the real C-3 store."""
import os, sys, tempfile, shutil
from datetime import datetime, timezone
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis, publish_restart
from v2_history_ops import read_effective, prepare_history_day
from v2_history_restart import prepare_restart_plan
from v2_daily_run import run_morning
D, TZ = P.DATES, P.TZ
def morning(d):
    y, m, dd = (int(x) for x in d.split("-")); return datetime(y, m, dd, 18, 0, tzinfo=TZ)
w = P.World(0); root = tempfile.mkdtemp(dir=os.environ["TMPDIR"]); st = HistoryFileStore(root, writable=True)
st.initialize(publish_genesis(w.start_after, w.sessions))
w.ledger += [P.obs("R1", D[1], 27.0), P.obs("R2", D[2], 28.0)]
print("A", run_morning(st, morning(D[3]), w.series, w.sessions, w.ledger))
h = st.read()
when = datetime(2026, 3, 6, 1, 0, tzinfo=timezone.utc)
plan = prepare_restart_plan(h, D[3], w.sessions, w.ledger, D[3], "restart-1", when)
pub = publish_restart(plan, plan.plan_hash, h, w.sessions, w.ledger)
h = st.publish(pub).history
v = read_effective(h)
print("view latest_apply_d=%s processing_after=%s boundary=%s" % (v.latest_apply_d, v.processing_after, v.current_boundary))
w.ledger += [P.obs("R4", D[4], 31.0)]
direct = prepare_history_day(h, D[4], w.series, w.sessions, w.ledger)
print("direct prepare_history_day(D4):", direct.status)
for k in (4, 5, 6):
    r = run_morning(st, morning(D[k]), w.series, w.sessions, w.ledger)
    print("run after D%d close:" % k, r)
# the same with the start position taken from processing_after (the rule the review proposes)
import v2_daily_run.run as RUN
src = open(RUN.__file__, encoding="utf-8").read().replace("view.latest_apply_d or view.processing_after", "view.processing_after")
ns = {"__name__": "patched"}; exec(compile(src, "patched_run", "exec"), ns)
r = ns["run_morning"](st, morning(D[5]), w.series, w.sessions, w.ledger)
print("patched (processing_after) after D5 close:", r)
shutil.rmtree(root)
