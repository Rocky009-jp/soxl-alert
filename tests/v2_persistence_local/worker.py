"""Independent worker process for the v2_persistence.local tests. Driven by l_helpers.Worker over stdin / stdout.

argv[1] is a JSON spec: root, mode (read | commit | init | probe), plan / genesis, durability, wait_go (read, print
READY, wait for GO before the operation), hook (null or {point, action}). Points: lock_acquired, partial_write,
after_file_fsync, after_tmp_close, before_replace, after_replace, after_dir_fsync. Actions: exit (os._exit(77) with no clean-up),
pause (print AT, wait for CONTINUE).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import l_helpers as H  # noqa: E402  (disables sockets in this process)
from v2_persistence.codec import decode_snapshot  # noqa: E402
from v2_persistence.local import LocalFileStore, LocalStoreError  # noqa: E402


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def make_action(point, action):
    def fire():
        if action == "exit":
            sys.stdout.flush()
            os._exit(77)
        emit({"event": "AT", "point": point})
        line = sys.stdin.readline()
        if line.strip() != "CONTINUE":
            os._exit(78)
    return fire


def build_ops(hook):
    ops = H.FaultOps()
    if not hook:
        return ops
    point, act = hook["point"], make_action(hook["point"], hook["action"])
    if point == "lock_acquired":
        ops.add("listdir", before=act)
    elif point == "partial_write":
        def wrap(real, writer, data):
            real(writer, data[:max(1, len(data) // 2)])
            act()
            return real(writer, data[max(1, len(data) // 2):])
        ops.add("write", "tmp", wrap=wrap)
    elif point == "after_file_fsync":
        ops.add("fsync_file", "tmp", after=act)
    elif point == "after_tmp_close":
        ops.add("close", "tmp", after=act)
    elif point == "before_replace":
        ops.add("replace", before=act)
    elif point == "after_replace":
        ops.add("replace", after=act)
    elif point == "after_dir_fsync":
        ops.add("fsync_dir", after=act)
    else:
        raise SystemExit("unknown hook point")
    return ops


def main():
    spec = json.loads(sys.argv[1])
    mode = spec["mode"]
    if mode == "probe":
        import socket
        blocked = False
        try:
            socket.socket()
        except RuntimeError:
            blocked = True
        emit({"event": "RESULT", "ok": True, "socket_blocked": blocked, "pid": os.getpid()})
        return
    store = LocalFileStore(spec["root"], writable=spec.get("writable", True),
                           durability=spec.get("durability", "strict"), _ops=build_ops(spec.get("hook")))
    plan = H.plan_from_json(spec["plan"]) if spec.get("plan") else None
    try:
        if spec.get("wait_go"):
            snap = store.read()
            emit({"event": "READY", "head_seq": snap.head_seq})
            if sys.stdin.readline().strip() != "GO":
                os._exit(78)
        if mode == "read":
            snap = store.read()
            emit({"event": "RESULT", "ok": True, "head_seq": snap.head_seq, "head_hash": snap.head_hash})
        elif mode == "commit":
            res = store.commit(plan)
            emit({"event": "RESULT", "ok": True, "status": res.status, "head_seq": res.snapshot.head_seq,
                  "persistence_level": res.persistence_level})
        elif mode == "init":
            res = store.initialize(decode_snapshot(spec["genesis"]))
            emit({"event": "RESULT", "ok": True, "status": res.status, "persistence_level": res.persistence_level})
        else:
            raise SystemExit("unknown mode")
    except LocalStoreError as e:
        emit({"event": "RESULT", "ok": False, "code": e.code, "field": e.field, "phase": e.phase,
              "cleanup": list(e.cleanup), "primary": e.primary})
    except Exception as e:  # S1 errors (PersistenceError / CoreError)
        emit({"event": "RESULT", "ok": False, "code": getattr(e, "code", type(e).__name__),
              "field": getattr(e, "field", None), "phase": None, "cleanup": [], "primary": None})


main()
