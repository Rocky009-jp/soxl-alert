"""T-3 re-check: N processes run the trial morning job at once (one history root, one outbox). For every round, record
each process's (outcome, code, kind, delivery) and the order of the sends. Usage: N=2 K=40 python -B s4bx_race.py <trial worktree>"""
import os, sys, subprocess, tempfile, shutil, time, json
from datetime import datetime
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
D, TZ = P.DATES, P.TZ
NOTE_CODES = ("store_busy", "publication_stale")


def now():
    y, m, d = (int(x) for x in D[6].split("-")); return datetime(y, m, d, 18, tzinfo=TZ)


def world():
    w = P.World(0); w.ledger += [P.obs("R%d" % i, D[i], 30.0) for i in range(1, 6)]; return w


if len(sys.argv) > 2:
    h, o, sync, i, logf = sys.argv[2:7]
    from v2_history_local import HistoryFileStore
    from v2_notify import LocalOutbox, morning_job

    class S(object):
        def send(self, text):
            with open(logf, "a") as f:
                f.write(json.dumps({"i": i, "head": text.splitlines()[0]}, ensure_ascii=False) + "\n")
            return "SENT"
    w = world()
    open(os.path.join(sync, "ready." + i), "w").close()
    while not os.path.exists(os.path.join(sync, "go")):
        time.sleep(0.001)
    r, n, s = morning_job(HistoryFileStore(h, writable=True), LocalOutbox(o), S(), now(), w.series, w.sessions, w.ledger)
    print(json.dumps([i, r.outcome, r.code, n.kind, s])); sys.exit(0)

from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
N, K, TMP = int(os.environ.get("N", 4)), int(os.environ.get("K", 20)), os.environ.get("TMPDIR", tempfile.gettempdir())
tally, halt_codes, orders, bad = {}, {}, {}, 0
for k in range(K):
    h, o, sync = (tempfile.mkdtemp(dir=TMP) for _ in range(3)); logf = os.path.join(sync, "sent.log")
    w = world(); HistoryFileStore(h, writable=True).initialize(publish_genesis(w.start_after, w.sessions))
    ps = [subprocess.Popen([sys.executable, "-B", __file__, ROOT, h, o, sync, str(i), logf], stdout=subprocess.PIPE,
                           text=True) for i in range(N)]
    while len([x for x in os.listdir(sync) if x.startswith("ready.")]) < N:
        time.sleep(0.01)
    open(os.path.join(sync, "go"), "w").close()
    runs = [json.loads(p.communicate()[0].strip()) for p in ps]
    sent = [json.loads(x) for x in open(logf).read().splitlines()] if os.path.exists(logf) else []
    kinds = tuple("halt" if "判定なし" in x["head"] else "judgment" for x in sent)
    tally[tuple(sorted(kinds))] = tally.get(tuple(sorted(kinds)), 0) + 1
    orders[kinds] = orders.get(kinds, 0) + 1
    by_i = {r[0]: r for r in runs}
    for x in sent:
        r = by_i[x["i"]]
        if r[3] == "halt":
            halt_codes[r[2]] = halt_codes.get(r[2], 0) + 1
            if "judgment" in kinds and r[2] not in NOTE_CODES:
                bad += 1
    if len([x for x in kinds if x == "judgment"]) > 1 or len([x for x in kinds if x == "halt"]) > 1:
        bad += 1000
    for d in (h, o, sync):
        shutil.rmtree(d)
print(json.dumps({"N": N, "K": K, "sent_kinds": {",".join(k) or "none": v for k, v in tally.items()},
                  "order": {">".join(k) or "none": v for k, v in orders.items()}, "halt_codes": halt_codes,
                  "halt_without_note_beside_judgment_or_double": bad}, ensure_ascii=False))
