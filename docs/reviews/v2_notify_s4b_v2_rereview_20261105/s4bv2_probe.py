"""Re-review of the S4-B second edition (36b2cb1): the ERROR key rule of sec.3 modelled on top of the unchanged trial
(compose / outbox from the trial diff). Not the implementation. Usage: python -B s4bv2_probe.py <worktree: 6ad609f + trial>"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_core.sessions import SessionList
from v2_daily_run import RunError, run_morning
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
from v2_notify import LocalOutbox
from v2_notify.compose import ERROR, MORNING, Notice, compose_notice
from v2_notify.job import _send
from v2_notify.outbox import NONE
D = P.DATES
UTC, JST = timezone.utc, timezone(timedelta(hours=9))


def target_d(sessions, now):                                  # sec.3 (2nd ed.): same rule as S4-A, before run_morning
    try:
        if not isinstance(sessions, SessionList):
            return None
        t = None
        for s in sessions.sessions:
            if s.close_at <= now:
                t = s.date
        return t
    except Exception:
        return None


def morning_job2(store, outbox, sender, now, series, sessions, raw):
    d = target_d(sessions, now)
    exc, code = None, None
    try:
        report = run_morning(store, now, series, sessions, raw)
    except RunError as e:
        report, code = None, e.code
    except Exception as e:
        report, code, exc = None, "unexpected_error", e
    if report is not None:
        notice = compose_notice(report, sessions, now)
    else:
        key_d = d if d is not None else now.astimezone(UTC).date().isoformat()
        notice = Notice(ERROR, key_d, "【SOXL日次】%s 判定なし（実行の誤り）\n  理由: %s" % (key_d, code), None, code)
    status = None
    if notice.kind != MORNING and d is not None and outbox.state(d, MORNING)[0] != NONE:
        status = "SKIPPED_JUDGMENT_EXISTS"
    else:
        cid = outbox.claim(notice, now)
        if cid is None:
            status = "SKIPPED_CLAIMED"
        else:
            status = _send(sender, notice.text)
            outbox.record(notice.d, notice.kind, cid, status, now)
    if exc is not None:
        raise exc
    return notice.kind, notice.d, status


class Sender(object):
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return "SENT"


class BadSeries(object):
    def through(self, d): raise ZeroDivisionError("data source bug /secret/path")


def setup():
    w = P.World(0); h, o = tempfile.mkdtemp(), tempfile.mkdtemp()
    HistoryFileStore(h, writable=True).initialize(publish_genesis(w.start_after, w.sessions))
    return w, h, o


def job(w, h, o, s, now, series=None, sessions=None):
    try:
        return morning_job2(HistoryFileStore(h, writable=True), LocalOutbox(o), s, now, series or w.series,
                            w.sessions if sessions is None else sessions, w.ledger)
    except ZeroDivisionError:
        return "raised ZeroDivisionError"


print("== X1' (S4B-06(d)) daytime JST retry, then next JST morning, both errors")
w, h, o = setup(); s = Sender()
print("  run1 Wed 10:00 JST", job(w, h, o, s, datetime(2026, 3, 4, 1, 0, tzinfo=UTC), BadSeries()), "sends", len(s.sent))
print("  run2 Thu 06:30 JST", job(w, h, o, s, datetime(2026, 3, 4, 21, 30, tzinfo=UTC), BadSeries()), "sends", len(s.sent))
print("  files", sorted(os.listdir(o)))

print("== X2' (S4B-06(e)) judgment, then an error rerun of the same D, then an error-first D followed by a judgment")
w, h, o = setup(); s = Sender(); w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
n = datetime(2026, 3, 4, 21, 30, tzinfo=UTC)
print("  judgment", job(w, h, o, s, n))
print("  error rerun", job(w, h, o, s, n + timedelta(hours=1), BadSeries()), "sends", len(s.sent))
w2, h2, o2 = setup(); s2 = Sender(); w2.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
print("  error first", job(w2, h2, o2, s2, n, BadSeries()), "| then judgment", job(w2, h2, o2, s2, n + timedelta(hours=1)),
      "sends", len(s2.sent))

print("== X6 fallback key (UTC date) and a D key share one file name")
w, h, o = setup(); s = Sender()
n1 = datetime(2026, 3, 4, 21, 30, tzinfo=UTC)                  # Thu 06:30 JST; the session list is broken -> no D
print("  run1 broken sessions", job(w, h, o, s, n1, sessions=["not a SessionList"]), "sends", len(s.sent))
n2 = datetime(2026, 3, 5, 3, 0, tzinfo=UTC)                     # Thu 12:00 JST; list fixed, D = Wed 03-04, data error
print("  run2 fixed list, D=%s" % target_d(w.sessions, n2), job(w, h, o, s, n2, BadSeries()), "sends", len(s.sent))
