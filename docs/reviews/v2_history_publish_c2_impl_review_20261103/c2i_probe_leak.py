"""C-2 implementation review: an independent search for unexpected exceptions and for the code family of refusals.
Run from the repository root: python -B docs/reviews/v2_history_publish_c2_impl_review_20261103/c2i_probe_leak.py
Every body is changed through the private constructor (hash written again), as the C-2 tests do; nothing is written."""
import collections, copy, os, sys
ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_publish"))
import c2_helpers as X  # noqa: E402
U = X.U
from v2_core.errors import CoreError  # noqa: E402

WEIRD = [None, True, False, 0, -1, 1, 2**63, -2**63, 10**30, 1.5, "", "x", "0" * 64, [], [None], {}, {"a": 1},
         [[]], [{}], "2026-01-01"]
leaks, codes, calls = [], collections.Counter(), 0


def paths(x, prefix=()):
    yield prefix
    if isinstance(x, dict):
        for k in x:
            yield from paths(x[k], prefix + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x[:3]):          # the first three elements of each list
            yield from paths(v, prefix + (i,))


def set_at(body, path, value):
    if not path:
        return value
    t = body
    for p in path[:-1]:
        t = t[p]
    if value is DELETE:
        del t[path[-1]]
    else:
        t[path[-1]] = value
    return body


DELETE = object()


def call(fn, *a):
    global calls
    calls += 1
    try:
        r = fn(*a)
        codes[(fn.__name__, "ok" if fn is U.check_publication else r.outcome)] += 1
    except CoreError as e:
        codes[(fn.__name__, e.code, getattr(e, "rule", None))] += 1
    except Exception as e:  # noqa: BLE001
        leaks.append((fn.__name__, type(e).__name__, str(e)[:80]))


for case in X.every_case():
    body0 = case.pub.body
    cand_bytes = X.file_bytes(case.candidate)
    currents = [case.current, cand_bytes, None, b"\xef\xbb\xbf" + cand_bytes, b"{", b"[]", b"null"]
    try:
        currents.append(X.file_bytes(X.extended_history(case)))
    except Exception:  # noqa: BLE001
        pass
    for path in list(paths(body0)):
        if not path:
            continue
        for value in WEIRD + [DELETE]:
            body = copy.deepcopy(body0)
            try:
                body = set_at(body, path, value)
                pub = U.HistoryPublication._make(body)
            except CoreError:
                continue
            except (KeyError, IndexError, TypeError):
                continue
            for cur in currents:
                call(U.check_publication, cur, pub, case.source_v1)
                call(U.reconcile_publication, cur, pub)
    # structural: events/records whose items are not records, extra key, a missing key
    key = "records" if body0["mode"] == "APPEND" else "candidate_history"
    lst = body0["records"] if key == "records" else body0["candidate_history"]["events"]
    for item in [1, "x", None, [], {}, {"seq": 1}, dict(lst[-1], extra=1)]:
        body = copy.deepcopy(body0)
        target = body["records"] if key == "records" else body["candidate_history"]["events"]
        target[-1] = item
        pub = U.HistoryPublication._make(body)
        for cur in currents:
            call(U.check_publication, cur, pub, case.source_v1)
            call(U.reconcile_publication, cur, pub)

print("calls", calls, "leaks", len(leaks))
for l in sorted(set(leaks))[:30]:
    print("LEAK", l)
for k, v in sorted(codes.items(), key=lambda kv: str(kv[0])):
    print(v, k)
