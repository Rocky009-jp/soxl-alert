"""X3 detail: what run B consumed, and that B alone (no earlier halt) would have shown D2. Usage: python -B s4bx_x3b.py <trial worktree>"""
import os, sys, tempfile
from datetime import datetime, timedelta
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
from v2_daily_run import run_morning
from v2_notify import LocalOutbox, morning_job
D = P.DATES
class S(object):
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return "SENT"
for with_a in (True, False):
    w = P.World(0, unconfirmed=(D[4],)); h, o = tempfile.mkdtemp(), tempfile.mkdtemp()
    HistoryFileStore(h, writable=True).initialize(publish_genesis(w.start_after, w.sessions))
    w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R3", D[3], 31.0)]
    now = datetime(2026, 3, 6, 18, 0, tzinfo=P.TZ); s = S()
    if with_a:
        open(os.path.join(h, "write.lock"), "wb").write(b"x")
        morning_job(HistoryFileStore(h, writable=True), LocalOutbox(o), s, now, w.series, w.sessions, w.ledger)
        os.unlink(os.path.join(h, "write.lock"))
    r, n, st = morning_job(HistoryFileStore(h, writable=True), LocalOutbox(o), s, now + timedelta(minutes=1), w.series, w.sessions, w.ledger)
    print("earlier halt=%s: B %s consumed=%s status=%s; D2 in B's composed text=%s; sends=%d"
          % (with_a, r.outcome, [(c.d, c.gap, c.skipped_sessions) for c in r.consumed], st, D[2] in n.text, len(s.sent)))
