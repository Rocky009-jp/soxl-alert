"""now exactly at close_at of D: the job's own target D must equal run_morning's (V04 was not detected)."""
import os, sys, tempfile
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
import s4b_helpers as H
N, S, D, P = H.N, H.S, H.D, H.P
h, o = tempfile.mkdtemp(), tempfile.mkdtemp(); w = P.World(0); S.decide(w, [1, 2, 3, 4]); snd = H.Sender()
N.morning_job(S.real_store(h, w), N.LocalOutbox(o), snd, H.now_at(D[3]), w.series, w.sessions, w.ledger)
close = w.sessions.get(D[4]).close_at if hasattr(w.sessions, "get") else [s for s in w.sessions.sessions if s.date == D[4]][0].close_at
try:
    N.morning_job(S.real_store(h, w, initialize=False), N.LocalOutbox(o), snd, close, H.RaisingSeries(ZeroDivisionError()), w.sessions, w.ledger)
except ZeroDivisionError:
    pass
print("V04 probe: now == close_at(%s) program error -> sends" % D[4], [t.splitlines()[0] for t in snd.texts], sorted(os.listdir(o)))
