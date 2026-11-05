"""Independent probes for the S4-B implementation review (f3b9f7f). Run: python -B s4bi_probe.py <repo>"""
import os, sys, shutil, tempfile, json
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
import s4b_helpers as H
N, S, D, P = H.N, H.S, H.D, H.P

def fresh():
    h, o = tempfile.mkdtemp(prefix="pr_h_"), tempfile.mkdtemp(prefix="pr_o_")
    w = P.World(0)
    return h, o, w

def job(h, o, w, now, sender, **kw):
    store = kw.pop("store", None) or S.real_store(h, w, initialize=not os.listdir(h))
    return N.morning_job(store, N.LocalOutbox(o), sender, now, kw.get("series", w.series),
                         kw.get("sessions", w.sessions), kw.get("ledger", w.ledger))

out = {}
print("TZ", S.TZ, "D", D[:6])

# X1: R-03 fallback key vs D key, and the fallback ERROR after a judgment of the same date
h, o, w = fresh(); S.decide(w, [1, 2, 3])
snd = H.Sender()
now = H.now_at(D[3])                                   # 18:00 local
print("X1 now", now.isoformat(), "utc date", H.utc_date(now))
r1 = job(h, o, w, now, snd)
r2 = job(h, o, w, H.now_at(D[3], 19), snd, sessions=["bad"])   # fallback: sessions wrong
print("X1a judgment then fallback error:", r1.kind, r1.d, r1.delivery, "|", r2.kind, r2.d, r2.delivery, r2.existing_status)
print("X1a texts:", [t.splitlines()[0] for t in snd.texts])
# X1b: fallback error first, then a D-key error of the same date (program error)
h, o, w = fresh(); S.decide(w, [1, 2, 3])
snd = H.Sender()
a = job(h, o, w, H.now_at(D[3], 19), snd, sessions=["bad"])
try:
    job(h, o, w, H.now_at(D[3], 20), snd, series=H.RaisingSeries(ZeroDivisionError("x")))
    b = None
except ZeroDivisionError:
    b = "raised"
print("X1b fallback then D error:", a.d, a.delivery, "| second", b, "texts", [t.splitlines()[0] for t in snd.texts])
print("X1b outbox", sorted(os.listdir(o)))

# X2: resend of a HALT (UNKNOWN) after the judgment of the same D was SENT
h, o, w = fresh(); S.decide(w, [1, 2])                 # D3 has no decision -> ?
w2 = P.World(0, unconfirmed=(D[3],)); S.decide(w2, [1, 2, 3])
snd = H.Sender([TimeoutError("late")])
r = N.morning_job(S.real_store(h, w2), N.LocalOutbox(o), snd, H.now_at(D[3]), w2.series, w2.sessions, w2.ledger)
print("X2 first:", r.run_outcome, r.kind, r.d, r.delivery)
snd2 = H.Sender()
w3 = P.World(0); S.decide(w3, [1, 2, 3])
r = N.morning_job(S.real_store(h, w3, initialize=False), N.LocalOutbox(o), snd2, H.now_at(D[3], 20), w3.series, w3.sessions, w3.ledger)
print("X2 then judgment:", r.run_outcome, r.kind, r.d, r.delivery)
rr = N.resend(N.LocalOutbox(o), snd2, D[3], "halt", "req1", H.now_at(D[3], 21))
print("X2 resend of the halt after the judgment:", rr.delivery, rr.original_status, "| sent heading:", snd2.texts[-1].splitlines()[:2])

# X3: an empty (crashed) morning claim blocks the day for good
h, o, w = fresh(); S.decide(w, [1, 2, 3])
open(os.path.join(o, D[3] + "-morning.claim.json"), "wb").close()
snd = H.Sender()
r = job(h, o, w, H.now_at(D[3]), snd)
rr = N.resend(N.LocalOutbox(o), snd, D[3], "morning", "fix1", H.now_at(D[3], 19))
print("X3 empty morning claim:", r.delivery, r.existing_status, r.exit_code, "| resend", rr.delivery, "| sends", len(snd.texts))

# X4: write failure in the claim leaves a damaged claim (ENOSPC on write)
h, o, w = fresh(); S.decide(w, [1, 2, 3])
ops = H.Ops({"write": (1, OSError(28, "No space left"))})
snd = H.Sender()
r = N.morning_job(S.real_store(h, w), N.LocalOutbox(o, _ops=ops), snd, H.now_at(D[3]), w.series, w.sessions, w.ledger)
r2 = job(h, o, w, H.now_at(D[3], 19), snd)
print("X4 ENOSPC on claim write:", r.delivery, "| rerun", r2.delivery, r2.existing_status, "| files", {n: os.path.getsize(os.path.join(o, n)) for n in os.listdir(o)})

# X5: result-only key (the fix) for morning, halt and resend
h, o, w = fresh(); S.decide(w, [1, 2, 3])
H.bwrite(o, D[3] + "-morning.result.json", H.canonical({"claim_id": "0"*32, "status": "SENT", "recorded_at": "x"}))
snd = H.Sender()
r = job(h, o, w, H.now_at(D[3]), snd)
print("X5 result only:", r.delivery, r.existing_status, "sends", len(snd.texts), sorted(os.listdir(o)))

# X6: a claim being written (empty) by another process seen by a HALT -> SKIPPED_JUDGMENT_EXISTS (safe)
print("X6 see test_s4b_05 Damage / S4B-05(d)")

# X7: exit code of a sent HALT rerun, and DONE rerun after UNKNOWN
h, o, w = fresh(); S.decide(w, [1, 2, 3])
snd = H.Sender([None])
r = job(h, o, w, H.now_at(D[3]), snd); r2 = job(h, o, w, H.now_at(D[3], 19), H.Sender())
print("X7 DONE with sender None:", r.delivery, r.exit_code, "| rerun", r2.delivery, r2.existing_status, r2.exit_code)
