"""R-03 collision with a realistic hour (JST morning = UTC 21-22h of the US session date)."""
import os, sys, tempfile
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
import s4b_helpers as H
N, S, D, P = H.N, H.S, H.D, H.P
from datetime import datetime, timezone, timedelta
JST = timezone(timedelta(hours=9))
def at_jst(d, h, m=0):
    y, mo, dd = (int(x) for x in d.split("-"))
    return datetime(y, mo, dd, h, m, tzinfo=JST)
def fresh():
    return tempfile.mkdtemp(prefix="pr_h_"), tempfile.mkdtemp(prefix="pr_o_")
# D[3]=2026-03-05 (Thu) closes 16:00 -05:00 = 21:00 UTC = 06:00 JST 03-06.
n1 = at_jst("2026-03-06", 6, 30); n2 = at_jst("2026-03-06", 7, 0)
print("now UTC", n1.astimezone(timezone.utc).isoformat())
# (a) judgment for D=03-05 sent, then a run with wrong sessions -> fallback key 03-05-error (same name space as D)
h, o = fresh(); w = P.World(0); S.decide(w, [1, 2, 3]); snd = H.Sender()
r1 = N.morning_job(S.real_store(h, w), N.LocalOutbox(o), snd, n1, w.series, w.sessions, w.ledger)
r2 = N.morning_job(S.real_store(h, w, initialize=False), N.LocalOutbox(o), snd, n2, w.series, ["bad"], w.ledger)
print("R03a", r1.kind, r1.d, r1.delivery, "| fallback", r2.kind, r2.d, r2.delivery, r2.existing_status)
print("     headings:", [t.splitlines()[0] for t in snd.texts])
# (b) fallback error first, then a program error for D=03-05 in the same morning
h, o = fresh(); w = P.World(0); S.decide(w, [1, 2, 3]); snd = H.Sender()
a = N.morning_job(S.real_store(h, w), N.LocalOutbox(o), snd, n1, w.series, ["bad"], w.ledger)
try:
    N.morning_job(S.real_store(h, w, initialize=False), N.LocalOutbox(o), snd, n2, H.RaisingSeries(ZeroDivisionError()), w.sessions, w.ledger)
except ZeroDivisionError:
    pass
print("R03b fallback", a.d, a.delivery, "| then D error -> sends", len(snd.texts), [t.splitlines()[0] for t in snd.texts])
# (c) D error first (program error), then the fixed run judges: judgment is sent
h, o = fresh(); w = P.World(0); S.decide(w, [1, 2, 3]); snd = H.Sender()
try:
    N.morning_job(S.real_store(h, w), N.LocalOutbox(o), snd, n1, H.RaisingSeries(ZeroDivisionError()), w.sessions, w.ledger)
except ZeroDivisionError:
    pass
b = N.morning_job(S.real_store(h, w, initialize=False), N.LocalOutbox(o), snd, n2, w.series, w.sessions, w.ledger)
print("R03c D error then judgment:", b.kind, b.delivery, [t.splitlines()[0] for t in snd.texts])
st = N.outbox_status(N.LocalOutbox(o), "2026-03-05")
print("status", st)
