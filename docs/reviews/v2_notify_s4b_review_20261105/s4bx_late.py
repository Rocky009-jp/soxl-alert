"""A run after the next open, with the target's decision present (PREPARED): is the passed-open note added?
Usage: python -B s4bx_late.py <trial worktree>"""
import os, sys, tempfile
from datetime import timedelta
ROOT = sys.argv[1]
for p in (ROOT, os.path.join(ROOT, "tests", "v2_persistence")):
    sys.path.insert(0, p)
import p_helpers as P
from v2_history_local import HistoryFileStore
from v2_history_publish import publish_genesis
from v2_notify import LocalOutbox, morning_job
D = P.DATES
class S(object):
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return "SENT"
w = P.World(0); h, o = tempfile.mkdtemp(), tempfile.mkdtemp()
HistoryFileStore(h, writable=True).initialize(publish_genesis(w.start_after, w.sessions))
w.ledger += [P.obs("R%d" % i, D[i], 30.0) for i in range(1, 4)]
late = w.sessions.next(D[3]).open_at + timedelta(minutes=5); s = S()
r, n, st = morning_job(HistoryFileStore(h, writable=True), LocalOutbox(o), s, late, w.series, w.sessions, w.ledger)
print(r.outcome, r.target_d, r.target_status, st, "| passed-open note:", "寄付きは過ぎています" in s.sent[-1])
print("    first lines:", s.sent[-1].splitlines()[:2])
