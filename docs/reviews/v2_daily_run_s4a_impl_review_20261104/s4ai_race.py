"""Implementation review: the design review race probe (s4r_race.py, unchanged logic) run against the S4-A implementation c15ab18.
Checks the trial's request S4A-13(b) claim: the final history.json equals one run's result."""
import os, sys, tempfile, shutil, subprocess, time, json
from datetime import datetime
ROOT = sys.argv[1]; NPROC = int(sys.argv[2]); TRIALS = int(sys.argv[3]); DAYS = int(sys.argv[4])
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
from v2_history_ops import read_effective
from v2_daily_run import run_morning
D, TZ = P.DATES, P.TZ
def morning(d):
    y, m, dd = (int(x) for x in d.split("-")); return datetime(y, m, dd, 18, 0, tzinfo=TZ)
def world():
    w = P.World(0); w.ledger += [P.obs("R%d" % i, D[i], 25.0 + (i % 7)) for i in range(1, DAYS + 1)]; return w
if len(sys.argv) > 5:                                    # child: wait for the go file, run once, print the report
    root, go = sys.argv[5], sys.argv[6]
    w = world(); st = HistoryFileStore(root, writable=True)
    while not os.path.exists(go): time.sleep(0.001)
    import random; time.sleep(random.Random(os.getpid()).uniform(0, float(os.environ.get('STAGGER', '0'))))
    r = run_morning(st, morning(D[DAYS + 1]), w.series, w.sessions, w.ledger)
    print(json.dumps([r.outcome, r.code, len(r.consumed)])); sys.exit(0)
w = world()
ref = tempfile.mkdtemp(dir=os.environ["TMPDIR"]); st = HistoryFileStore(ref, writable=True)
st.initialize(publish_genesis(w.start_after, w.sessions))
run_morning(st, morning(D[DAYS + 1]), w.series, w.sessions, w.ledger)
expect = open(os.path.join(ref, "history.json"), "rb").read(); shutil.rmtree(ref)
same = partial = 0; outcomes = {}
for t in range(TRIALS):
    root = tempfile.mkdtemp(dir=os.environ["TMPDIR"]); st = HistoryFileStore(root, writable=True)
    st.initialize(publish_genesis(w.start_after, w.sessions)); go = os.path.join(os.environ["TMPDIR"], "go%d" % t)
    procs = [subprocess.Popen([sys.executable, "-B", __file__, ROOT, str(NPROC), "0", str(DAYS), root, go],
                              stdout=subprocess.PIPE, text=True) for _ in range(NPROC)]
    time.sleep(1.5); open(go, "w").close()
    outs = [json.loads(p.communicate()[0]) for p in procs]; os.remove(go)
    final = open(os.path.join(root, "history.json"), "rb").read()
    applies = [a["d"] for a in read_effective(st.read()).applies]
    assert len(applies) == len(set(applies)), "double APPLY"
    if final == expect: same += 1
    else: partial += 1
    key = tuple(sorted((o[0], o[1]) for o in outs)); outcomes[key] = outcomes.get(key, 0) + 1
    if final != expect and partial <= 3: print("trial %d: final has %d applies (expected %d); reports %s" % (t, len(applies), DAYS, outs))
    shutil.rmtree(root)
print("NPROC=%d DAYS=%d trials=%d same_as_one_run=%d prefix_only=%d" % (NPROC, DAYS, TRIALS, same, partial))
for k, v in sorted(outcomes.items(), key=lambda kv: -kv[1]): print("  ", v, k)
