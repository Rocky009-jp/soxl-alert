"""S4-C second edition re-review probes (run against the trial tree of 0caabe2's diff; nothing here is a request).
Y1 a stale lock on the remote state ref ([remote rejected] (failed to update ref), head unmoved) -> store_io_error, no note.
Y2 a pre-receive that refuses only the outbox ref -> CLAIM_FAILED, one push only (no retry), nothing sent.
Y3 two clones initialize the history at the same moment -> one INITIALIZED, the other already_initialized.
Y4 the identical-commit race (same second, same parent, same candidate, pushed at once) -> outcomes counted.
Y5 the push of the result is refused with the head unmoved -> RESULT_NOT_RECORDED, the claim stays UNKNOWN, no retry."""
import os, sys, tempfile, subprocess, threading
from datetime import datetime, timezone
ROOT = sys.argv[1]
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests", "v2_persistence")]
import p_helpers as P
from v2_history_publish import publish_genesis, publish_day
from v2_git_store import Git, GitHistoryStore, GitOutbox
from v2_git_store import git as G
from v2_notify import morning_job, outbox_status
from v2_persistence.local.errors import LocalStoreError
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
def code(f):
    try: return f()
    except LocalStoreError as e: return e.code

# Y1
w, o, g, h, ob = setup(); s = Sender()
open(os.path.join(o, "refs", "heads", "state.lock"), "w").close()
r = morning_job(h, ob, s, at(D[3]), w.series, w.sessions, w.ledger)
os.unlink(os.path.join(o, "refs", "heads", "state.lock"))
print("Y1", r.run_outcome, r.code, r.kind, r.delivery, "concurrent note:", any("同時に動いていた" in t for t in s.sent))

# Y2
w, o, g, h, ob = setup(); s = Sender()
hook = os.path.join(o, "hooks", "pre-receive")
with open(hook, "w") as f: f.write("#!/bin/sh\nwhile read a b ref; do [ \"$ref\" = refs/heads/outbox ] && exit 1; done\nexit 0\n")
os.chmod(hook, 0o755)
class Count(G.Git):
    pushes = 0
    def push(self, commit, ref):
        if ref == "outbox": Count.pushes += 1
        return G.Git.push(self, commit, ref)
gc, hc, oc = clone(o, gcls=Count)
r = morning_job(hc, oc, s, at(D[3]), w.series, w.sessions, w.ledger)
print("Y2", r.run_outcome, r.kind, r.delivery, "sends", len(s.sent), "outbox pushes", Count.pushes)

# Y3
for k in range(5):
    w = P.World(0); o = origin(); gA, hA, _ = clone(o); gB, hB, _ = clone(o)
    pub = publish_genesis(w.start_after, w.sessions); out = {}
    def go(name, hh):
        try: out[name] = hh.initialize(pub).status
        except LocalStoreError as e: out[name] = e.code
    ts = [threading.Thread(target=go, args=(n, x)) for n, x in (("A", hA), ("B", hB))]
    [t.start() for t in ts]; [t.join() for t in ts]
    print("Y3 round", k, sorted(out.values()))

# Y4
res = {}
for k in range(10):
    w, o, gA, hA, oA = setup(); gB, hB, oB = clone(o)
    pub = publish_day(hA.read(), D[1], w.series, w.sessions, w.ledger); out = []
    def go(hh):
        out.append(code(lambda: hh.publish(pub).status))
    ts = [threading.Thread(target=go, args=(x,)) for x in (hA, hB)]
    [t.start() for t in ts]; [t.join() for t in ts]
    applies = sum(1 for e in hA.read().events if e.get("kind") == "APPLY" and e.get("d") == D[1])
    key = (tuple(sorted(out)), applies); res[key] = res.get(key, 0) + 1
print("Y4 identical-commit race (outcomes, APPLY of D1):", res)

# Y5
w, o, gA, hA, oA = setup(); s = Sender()
class NoResult(G.Git):
    def push(self, commit, ref):
        return G.REJECTED if ref == "outbox" and NoResult.block and self.names(commit)[-1:] and any(n.endswith(".result.json") for n in self.names(commit)) else G.Git.push(self, commit, ref)
    block = True
gN, hN, oN = clone(o, gcls=NoResult)
r = morning_job(hN, oN, s, at(D[3]), w.series, w.sessions, w.ledger)
print("Y5 first run (result push refused)", r.delivery, r.send_status, "sends", len(s.sent),
      [(e.kind, e.status) for e in outbox_status(oA, r.d)][:1])
