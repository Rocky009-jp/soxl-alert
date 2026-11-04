"""N-01 repro (C-3 design review): a hand-made publication without the "mode" (or "source") key escapes the trial
store as a raw KeyError, while check_publication refuses the same value with publication_invalid/shape.
Run from the root of the trial tree (d6b0332 + the trial diff): python -B <this file>"""
import os, sys, tempfile, shutil
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_publish"))
sys.path.insert(0, ROOT)
import c2_helpers as X  # noqa: E402
from v2_core.errors import CoreError  # noqa: E402
from v2_history_local import HistoryFileStore  # noqa: E402


def outcome(fn, *a):
    try:
        fn(*a)
        return "ok"
    except CoreError as e:
        return "%s/%s" % (e.code, getattr(e, "rule", None))
    except Exception as e:  # noqa: BLE001
        return "LEAK %s" % type(e).__name__


for case, key, op in ((X.day_case(), "mode", "publish"), (X.genesis_case(), "mode", "initialize"),
                      (X.genesis_case(), "source", "initialize")):
    pub = X.rehash(case.pub, lambda b: b.pop(key))
    d = tempfile.mkdtemp(prefix="c3n01_")
    try:
        if case.current is not None:
            with open(os.path.join(d, "history.json"), "wb") as f:
                f.write(case.current)
        st = HistoryFileStore(d, writable=True, durability="file_sync_only")
        print("%-8s without %-6s  check_publication: %-28s  store.%s: %s  lock left: %s" % (
            case.source, key, outcome(X.U.check_publication, case.current, pub), op, outcome(getattr(st, op), pub),
            os.path.exists(os.path.join(d, "write.lock"))))
    finally:
        shutil.rmtree(d)
