"""S4-C design review probes (run against the trial tree of 68c030b's diff; nothing here is a request).
X1 add-only: a mirror that misses one remote file lets commit_with replace that file -> a second send.
X2 remote rejected: a pre-receive hook that declines every push of the state ref -> publication_stale + the concurrent note.
X3 same commit: two clones publishing the same candidate in the same second build the same commit; both pushes are OK.
X4 transient outbox fetch failure: the JobReport says SKIPPED_JUDGMENT_EXISTS with existing DAMAGED."""
import os, sys, tempfile, subprocess, shutil
from datetime import datetime, timezone
ROOT = sys.argv[1]
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests", "v2_persistence")]
import p_helpers as P
from v2_history_publish import publish_genesis
from v2_git_store import Git, GitHistoryStore, GitOutbox
from v2_git_store import git as G
from v2_notify import morning_job, outbox_status
from v2_daily_run import run_morning
D, TZ, TMP = P.DATES, P.TZ, os.environ["TMPDIR"]
CLOCK = lambda: datetime(2026, 11, 5, tzinfo=timezone.utc)
def sh(*a, cwd=None): return subprocess.run(a, cwd=cwd, check=True, capture_output=True)
def origin():
    o = tempfile.mkdtemp(prefix="SECRETMARK_", dir=TMP); sh("git", "init", "-q", "--bare", o); return o
def clone(o, gcls=Git, ocls=GitOutbox):
    w = tempfile.mkdtemp(dir=TMP); sh("git", "init", "-q", w); sh("git", "remote", "add", "origin", o, cwd=w)
    g = gcls(w); return g, GitHistoryStore(g, "state", CLOCK), ocls(g, "outbox", tempfile.mkdtemp(dir=TMP), CLOCK)
class Sender(object):
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return "SENT"
def at(d, h=18):
    y, m, dd = (int(x) for x in d.split("-")); return datetime(y, m, dd, h, tzinfo=TZ)
def setup():
    w = P.World(0); w.ledger += [P.obs("R1", D[1], 30.0), P.obs("R2", D[2], 31.0)]
    o = origin(); g, h, ob = clone(o)
    h.initialize(publish_genesis(w.start_after, w.sessions)); g.push(g.commit_with(None, "README", b"outbox\n", "init", CLOCK()), "outbox")
    return w, o, g, h, ob

# X1
w, o, gA, hA, oA = setup(); s = Sender()
r = morning_job(hA, oA, s, at(D[3]), w.series, w.sessions, w.ledger); print("X1 A", r.delivery, "sends", len(s.sent))
class Missing(GitOutbox):                      # a mirror rebuild that silently lost one file (the defect being probed)
    def _drop(self):
        for n in os.listdir(self._mirror):
            if n.endswith("-morning.claim.json") or n.endswith("-morning.result.json"): os.unlink(os.path.join(self._mirror, n))
    def _refresh(self):
        GitOutbox._refresh(self); self._drop()
gB, hB, oB = clone(o, ocls=Missing)
r = morning_job(hB, oB, s, at(D[3]), w.series, w.sessions, w.ledger); print("X1 B (mirror lost the morning files)", r.delivery, "sends", len(s.sent))
head = gA.fetch("outbox")
print("X1 remote morning claim replaced:", len([n for n in gA.names(head) if n.endswith("-morning.claim.json")]) == 1,
      "commits on outbox:", sh("git", "rev-list", "--count", head, cwd=gA.workdir).stdout.decode().strip())

# X2
w, o, gA, hA, oA = setup(); s = Sender()
hook = os.path.join(o, "hooks", "pre-receive")
with open(hook, "w") as f: f.write("#!/bin/sh\nwhile read a b ref; do [ \"$ref\" = refs/heads/state ] && { echo 'protected' >&2; exit 1; }; done\nexit 0\n")
os.chmod(hook, 0o755)
r = morning_job(hA, oA, s, at(D[3]), w.series, w.sessions, w.ledger)
print("X2", r.run_outcome, r.code, r.kind, r.delivery, "concurrent note:", any("同時に動いていた" in t for t in s.sent))
print("X2 push classified as", gA.push(gA.commit_with(gA.fetch("state"), "history.json", b"{}", "m", CLOCK()), "state"))

# X3
w, o, gA, hA, oA = setup()
gB, hB, oB = clone(o)
class Twin(G.Git):
    armed = True
    def push(self, commit, ref):
        if ref == "state" and Twin.armed:
            Twin.armed = False
            print("X3 B publishes the same candidate first:", run_morning(hB, at(D[3]), w.series, w.sessions, w.ledger).outcome)
        how = G.Git.push(self, commit, ref); print("X3 A push", how); return how
hT = GitHistoryStore(Twin(gA.workdir), "state", CLOCK)
print("X3 A", run_morning(hT, at(D[3]), w.series, w.sessions, w.ledger))

# X4
w, o, gA, hA, oA = setup(); s = Sender()
class Flaky(GitOutbox):
    n = 0
    def load(self, d, kind, resend_request_id=None):
        Flaky.n += 1
        if Flaky.n == 1:                      # one transient fetch failure on the first status read
            mv = o + "_away"; shutil.move(o, mv)
            try: return GitOutbox.load(self, d, kind, resend_request_id)
            finally: shutil.move(mv, o)
        return GitOutbox.load(self, d, kind, resend_request_id)
gF, hF, oF = clone(o, ocls=Flaky)
r = morning_job(hF, oF, s, at(D[3]), w.series, w.sessions, w.ledger)
print("X4", r.run_outcome, r.kind, r.delivery, r.existing_status, "sends", len(s.sent),
      "remote morning now:", [ (e.kind, e.status) for e in outbox_status(oA, r.d)][:1])

# X5 the two scheduled runs of D-6: the first run cannot fetch the state ref once (the outbox is reachable)
w, o, gA, hA, oA = setup(); s = Sender()
class StateBlip(G.Git):
    def fetch(self, ref):
        if ref == "state":
            raise G.GitError("git_fetch_failed", ref)
        return G.Git.fetch(self, ref)
g1, h1, o1 = clone(o, gcls=StateBlip)
r1 = morning_job(h1, o1, s, at(D[3], 7), w.series, w.sessions, w.ledger)
r2 = morning_job(hA, oA, s, at(D[3], 8), w.series, w.sessions, w.ledger)
print("X5 run1", r1.run_outcome, r1.code, r1.kind, r1.delivery, "| run2", r2.run_outcome, r2.kind, r2.delivery,
      "| sends:", [t.splitlines()[0] for t in s.sent])
print("X5 run1 halt has a 'later judgment' note:", any("そちらが有効" in t for t in s.sent[:1]))

# X3' the same candidate in the same second from two clones (one step only): the second push is '=' -> OK
w, o, gA, hA, oA = setup()
gB, hB, oB = clone(o)
from v2_history_publish import publish_day
hist = hA.read(); pub = publish_day(hist, D[1], w.series, w.sessions, w.ledger)
class Hold(G.Git):
    armed = True
    def push(self, commit, ref):
        if ref == "state" and Hold.armed:
            Hold.armed = False
            print("X3' B publish:", hB.publish(pub).status)
        return G.Git.push(self, commit, ref)
hH = GitHistoryStore(Hold(gA.workdir), "state", CLOCK)
print("X3' A publish:", hH.publish(pub).status, "| APPLY count of D1 on the remote:",
      sum(1 for e in hA.read().events if e.get("kind") == "APPLY" and e.get("d") == D[1]))
