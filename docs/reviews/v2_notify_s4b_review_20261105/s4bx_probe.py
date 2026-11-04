"""Review probes for the S4-B design (run on 6ad609f + the trial diff). Usage: python -B s4bx_probe.py <trial worktree>.
The trial job keys ERROR by now.date() in now's own zone; the design (sec.3) says the UTC date, so X1/X2 pass a UTC now."""
import os, sys, tempfile, shutil
from datetime import datetime, timedelta, timezone
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence"), os.path.join(ROOT, "tests", "v2_history")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
from v2_notify import LocalOutbox, morning_job, resend
D = P.DATES
UTC, JST = timezone.utc, timezone(timedelta(hours=9))
TMP = os.environ.get("TMPDIR", tempfile.gettempdir())


class Sender(object):
    def __init__(self):
        self.sent = []
    def send(self, text):
        self.sent.append(text); return "SENT"


class BadSeries(object):
    def through(self, d):
        raise ZeroDivisionError("data source bug /secret/path")


def setup(unconfirmed=()):
    w = P.World(0, unconfirmed=unconfirmed)
    h, o = tempfile.mkdtemp(dir=TMP), tempfile.mkdtemp(dir=TMP)
    HistoryFileStore(h, writable=True).initialize(publish_genesis(w.start_after, w.sessions))
    return w, h, o


def job(w, h, o, s, now, series=None):
    try:
        r, n, st = morning_job(HistoryFileStore(h, writable=True), LocalOutbox(o), s, now,
                               series or w.series, w.sessions, w.ledger)
        return (r.outcome if r else None, r.code if r else None, n.kind, n.d, st)
    except ZeroDivisionError:
        return ("raised ZeroDivisionError",)


print("== X1 ERROR key = UTC date: a daytime JST retry silences the next JST morning")
for label, tz in (("UTC (design sec.3)", UTC), ("JST (for comparison)", JST)):
    w, h, o = setup(); s = Sender()
    n1 = datetime(2026, 3, 4, 1, 0, tzinfo=UTC).astimezone(tz)      # Wed 10:00 JST, target Tue 03-03
    n2 = datetime(2026, 3, 4, 21, 30, tzinfo=UTC).astimezone(tz)    # Thu 06:30 JST, target Wed 03-04 (closed 21:00Z)
    a = job(w, h, o, s, n1, BadSeries()); b = job(w, h, o, s, n2, BadSeries())
    print("  %-22s run1 %s -> sends %d" % (label, n1.isoformat(), len(s.sent)))
    print("  %-22s run2 %s -> sends %d  files=%s" % ("", n2.isoformat(), len(s.sent), sorted(os.listdir(o))))

print("== X2 ERROR after a judgment of the same morning (key is not tied to D)")
w, h, o = setup(); s = Sender()
w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
n1 = datetime(2026, 3, 4, 21, 30, tzinfo=UTC)                        # Thu 06:30 JST, target Wed 03-04
print("  run1", job(w, h, o, s, n1))
print("  run2 (later rerun, data source fails)", job(w, h, o, s, n1 + timedelta(hours=1), BadSeries()))
print("  sends", len(s.sent), "| last text first lines:", s.sent[-1].splitlines()[:2])

print("== X3 halt then halt for the same D: the second run's consumed gaps are never shown")
w, h, o = setup(unconfirmed=(D[4],)); s = Sender()
w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R3", D[3], 31.0)]      # D2 has no record
now = datetime(2026, 3, 6, 18, 0, tzinfo=P.TZ)                      # after D4 (03-06) close
open(os.path.join(h, "write.lock"), "wb").write(b"x")                # a run holding the lock (or a leftover)
print("  A (lock held)", job(w, h, o, s, now))
os.unlink(os.path.join(h, "write.lock"))
print("  B (D4 unconfirmed)", job(w, h, o, s, now + timedelta(minutes=1)))
w.sessions = P.make_sessions(); w.ledger.append(P.obs("R4", D[4], 32.0))
print("  C (D4 confirmed)", job(w, h, o, s, now + timedelta(hours=1)))
print("  sends", len(s.sent), "| D2(%s) appears in any sent text: %s" % (D[2], any(D[2] in t for t in s.sent)))

print("== X4 a claim left empty (O_EXCL done, crash before the write): no route delivers D")
w, h, o = setup(); s = Sender()
w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
now = datetime(2026, 3, 5, 18, 0, tzinfo=P.TZ)
open(os.path.join(o, "%s-morning.claim.json" % D[3]), "wb").close()
print("  rerun", job(w, h, o, s, now), "| state", LocalOutbox(o).state(D[3], "morning")[0])
print("  resend", resend(LocalOutbox(o), s, D[3], "morning", "req1", now), "| sends", len(s.sent))

print("== X5 outbox root = history root (not rejected by the request's checks)")
w, h, o = setup(); s = Sender()
w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
print("  run1", job(w, h, h, s, datetime(2026, 3, 4, 18, 0, tzinfo=P.TZ)))
w.ledger.append(P.obs("R3", D[3], 31.0))
print("  run2 next morning", job(w, h, h, s, datetime(2026, 3, 5, 18, 0, tzinfo=P.TZ)))
