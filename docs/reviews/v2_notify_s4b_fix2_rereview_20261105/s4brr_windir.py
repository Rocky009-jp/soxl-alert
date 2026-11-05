"""Re-review of the N-01 fix (3b2c4ea): a host whose directory cannot be synced (PermissionError 13, as on Windows).
Both modes, the morning job, a rerun, a resend, and what each leaves in the outbox. Usage: python -B s4brr_windir.py <repo>"""
import os, sys, tempfile
REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_notify"))
import s4b_helpers as H
N, S, D, P = H.N, H.S, H.D, H.P
from v2_persistence.local.fsops import FileOps

class WinDir(FileOps):
    def is_windows(self):
        return True
    def fsync_dir(self, path):
        raise PermissionError(13, "Permission denied")
    def probe_dir_sync(self, path):
        raise PermissionError(13, "Permission denied")

for mode in ("file_sync_only", "strict", None):
    h, o = tempfile.mkdtemp(), tempfile.mkdtemp(); w = P.World(0); S.decide(w, [1, 2, 3]); snd = H.Sender()
    try:
        ob = N.LocalOutbox(o, _ops=WinDir()) if mode is None else N.LocalOutbox(o, mode, _ops=WinDir())
    except N.NotifyError as e:
        print(mode or "default", "refused at construction:", e.code, sorted(os.listdir(o))); continue
    r1 = N.morning_job(S.real_store(h, w), ob, snd, H.now_at(D[3]), w.series, w.sessions, w.ledger)
    r2 = N.morning_job(S.real_store(h, w, initialize=False), ob, snd, H.now_at(D[3], 19), w.series, w.sessions, w.ledger)
    rr = N.resend(ob, snd, D[3], "morning", "req1", H.now_at(D[3], 20))
    print(mode or "default(strict)", "| first", r1.delivery, r1.exit_code, "| rerun", r2.delivery, r2.existing_status, r2.exit_code,
          "| resend", rr.delivery, "| sends", len(snd.texts), "| files", sorted(os.listdir(o)))
