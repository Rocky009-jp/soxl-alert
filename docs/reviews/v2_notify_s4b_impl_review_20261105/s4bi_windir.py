"""Windows-like directory sync (os.open on a directory -> PermissionError 13, as C-3's rule windows_strict assumes).
Only the LocalOutbox's FileOps is affected (a subclass); the history store is the S4-A helper's file_sync_only."""
import os, sys, tempfile
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
import s4b_helpers as H
N, S, D, P = H.N, H.S, H.D, H.P
from v2_persistence.local.fsops import FileOps
class WinDir(FileOps):
    def fsync_dir(self, path):
        raise PermissionError(13, "Permission denied")
    def probe_dir_sync(self, path):
        raise PermissionError(13, "Permission denied")
h, o = tempfile.mkdtemp(), tempfile.mkdtemp(); w = P.World(0); S.decide(w, [1, 2, 3]); snd = H.Sender()
ob = N.LocalOutbox(o, _ops=WinDir())
print("constructed:", ob)
r1 = N.morning_job(S.real_store(h, w), ob, snd, H.now_at(D[3]), w.series, w.sessions, w.ledger)
print("W1 first morning:", r1.run_outcome, r1.delivery, r1.exit_code, "sends", len(snd.texts), sorted(os.listdir(o)))
r2 = N.morning_job(S.real_store(h, w, initialize=False), ob, snd, H.now_at(D[3], 19), w.series, w.sessions, w.ledger)
print("W2 rerun:", r2.delivery, r2.existing_status, r2.exit_code, "sends", len(snd.texts))
rr = N.resend(ob, snd, D[3], "morning", "req1", H.now_at(D[3], 20))
print("W3 resend:", rr.delivery, rr.original_status, "sends", len(snd.texts), sorted(os.listdir(o)))
rr2 = N.resend(ob, snd, D[3], "morning", "req2", H.now_at(D[3], 21))
print("W4 resend another id:", rr2.delivery, rr2.original_status, "sends", len(snd.texts))
print("status", N.outbox_status(ob, D[3], "morning"))
