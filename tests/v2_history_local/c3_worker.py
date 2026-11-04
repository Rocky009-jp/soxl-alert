"""Independent worker process for the C-3 tests. Driven by c3_helpers.Worker over stdin / stdout.

argv[1] is a JSON spec: root, mode (race | one | probe), durability, wait_go (print READY, wait for GO before the first
operation), attempts (race), hook (null or {point, action}). Points: after_tmp_close, before_replace, after_replace,
after_dir_fsync. Actions: exit (os._exit(77) with no clean-up), pause (print AT, wait for CONTINUE; the parent kills
the process while it waits).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import c3_helpers as H  # noqa: E402  (disables sockets in this process)
import v2_history_publish as U  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_history_local import HistoryFileStore, LocalStoreError  # noqa: E402


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
    ops = H.C3Ops()
    if not hook:
        return ops
    point, act = hook["point"], make_action(hook["point"], hook["action"])
    if point == "after_tmp_close":
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


def code_of(e):
    return getattr(e, "code", type(e).__name__)


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
    store = HistoryFileStore(spec["root"], writable=True, durability=spec.get("durability", "strict"),
                             _ops=build_ops(spec.get("hook")))
    h, pub, w = H.day1()
    if spec.get("wait_go"):
        emit({"event": "READY"})
        if sys.stdin.readline().strip() != "GO":
            os._exit(78)
    if mode == "one":
        try:
            res = store.publish(pub)
            emit({"event": "RESULT", "ok": True, "status": res.status, "head_seq": res.history.head_seq})
        except LocalStoreError as e:
            emit({"event": "RESULT", "ok": False, "code": e.code, "field": e.field, "phase": e.phase,
                  "cleanup": list(e.cleanup), "primary": e.primary})
        except CoreError as e:
            emit({"event": "RESULT", "ok": False, "code": e.code, "field": e.field, "phase": None, "cleanup": [],
                  "primary": None})
        return
    if mode == "race":
        outcomes = []
        for _ in range(spec["attempts"]):
            try:
                history = store.read()
                mine = U.publish_day(history, H.C2.D[1], w.series, w.sessions, w.ledger)
                store.publish(mine)
                outcomes.append("PUBLISHED")
            except CoreError as e:
                outcomes.append(code_of(e))
        emit({"event": "RESULT", "ok": True, "outcomes": outcomes})
        return
    raise SystemExit("unknown mode")


main()
