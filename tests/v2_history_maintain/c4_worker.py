"""Independent worker process for the C-4 tests. Driven by c4_helpers.Worker over stdin / stdout.

argv[1] is a JSON spec: root, op (adopt | migrate), mode (race | one | probe), durability, wait_go (print READY, wait for
GO before the first operation), attempts (race), hook (null or {point, action}). Points: after_manifest (after the MANIFEST
was put in place), after_publish (after the replace of history.json). Actions: exit (os._exit(77) with no clean-up), pause
(print AT, wait for CONTINUE; the parent kills the process while it waits). The child builds the same case as its parent
(the synthetic world of the existing helpers is deterministic).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import c4_helpers as H  # noqa: E402  (disables sockets in this process)
from v2_core.errors import CoreError  # noqa: E402
from v2_history_maintain import HistoryMaintenance  # noqa: E402


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
    ops = H.C4Ops()
    if not hook:
        return ops
    point, act = hook["point"], make_action(hook["point"], hook["action"])
    if point == "after_manifest":
        ops.add("replace", "manifest", after=act)
    elif point == "after_publish":
        ops.add("replace", "history", after=act)
    else:
        raise SystemExit("unknown hook point")
    return ops


def code_of(e):
    return getattr(e, "code", type(e).__name__)


def call(m, case, op):
    if op == "adopt":
        return m.adopt(case.pub)
    return m.migrate(case.pub, True)


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
    op = spec["op"]
    case = H.adoption() if op == "adopt" else H.migration()
    m = HistoryMaintenance(spec["root"], writable=True, durability=spec.get("durability", "strict"),
                           _ops=build_ops(spec.get("hook")))
    if spec.get("wait_go"):
        emit({"event": "READY"})
        if sys.stdin.readline().strip() != "GO":
            os._exit(78)
    if mode == "one":
        try:
            res = call(m, case, op)
            emit({"event": "RESULT", "ok": True, "status": res.status, "resumed": res.resumed})
        except CoreError as e:
            emit({"event": "RESULT", "ok": False, "code": code_of(e), "phase": getattr(e, "phase", None),
                  "cleanup": list(getattr(e, "cleanup", ())), "primary": getattr(e, "primary", None)})
        return
    if mode == "race":
        outcomes = []
        for _ in range(spec["attempts"]):
            try:
                res = call(m, case, op)
                outcomes.append("%s:%s" % (res.status, "resumed" if res.resumed else "first"))
            except CoreError as e:
                outcomes.append(code_of(e))
        emit({"event": "RESULT", "ok": True, "outcomes": outcomes})
        return
    raise SystemExit("unknown mode")


main()
