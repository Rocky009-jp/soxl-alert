"""C-3 implementation review: hand-made publications (HistoryPublication._make on mutated bodies of real values) through
all four operations. Only CoreError-family errors may leave; the lock is always released; the root never changes
unless the operation succeeded; a success is only possible for a value whose body equals a real builder's body.
usage: python c3i_handmade_fuzz.py <worktree> <n>"""
import copy, os, random, shutil, sys, collections
REPO = os.path.abspath(sys.argv[1]); N = int(sys.argv[2])
sys.path.insert(0, os.path.join(REPO, "tests", "v2_history_local")); os.chdir(REPO)
import c3_helpers as H  # noqa
from v2_core.errors import CoreError  # noqa
from v2_history_publish import HistoryPublication  # noqa
from v2_history_local import HistoryFileStore  # noqa
rng = random.Random(20261104)
cases = [H.C2.day_case(), H.C2.genesis_case(), H.C2.migration_case(), H.C2.adoption_case()] + H.append_cases()
WEIRD = [None, 0, -1, 2**70, 1.5, True, "", "x", "APPEND", "CREATE", "GENESIS", "REPLACE", [], {}, [1], {"a": 1},
         "0" * 64, "f" * 64]


def mutate(body):
    b = copy.deepcopy(body)
    for _ in range(rng.randint(1, 3)):
        r = rng.random()
        keys = list(b) if isinstance(b, dict) else []
        if not keys:
            break
        k = rng.choice(keys)
        if r < 0.3:
            b.pop(k)
        elif r < 0.7:
            b[k] = copy.deepcopy(rng.choice(WEIRD))
        elif r < 0.85 and isinstance(b[k], dict) and b[k]:
            kk = rng.choice(list(b[k])); b[k][kk] = copy.deepcopy(rng.choice(WEIRD))
        elif isinstance(b[k], list) and b[k]:
            i = rng.randrange(len(b[k])); b[k][i] = copy.deepcopy(rng.choice(WEIRD))
        else:
            b["extra"] = 1
    if rng.random() < 0.03:
        b = copy.deepcopy(rng.choice(WEIRD))
    return b


codes, problems = collections.Counter(), []
for i in range(N):
    c = rng.choice(cases)
    body = mutate(c.pub.body)
    try:
        pub = HistoryPublication._make(body)
    except CoreError:
        codes["_make refused"] += 1
        continue
    root = H.make_root()
    if c.current is not None and rng.random() < 0.9:
        H.put(root, H.HIST, c.current)
    before = H.state_of(root)
    op = rng.choice(["publish", "initialize", "reconcile"])
    try:
        getattr(HistoryFileStore(root, writable=True), op)(pub)
        codes[(op, "OK")] += 1
        if op != "reconcile" and body != c.pub.body:
            problems.append((i, op, "success for a mutated body"))
    except CoreError as e:
        codes[(op, e.code)] += 1
        if H.state_of(root) != before:
            problems.append((i, op, e.code, "root changed"))
    except BaseException as e:
        problems.append((i, op, "raw", type(e).__name__, str(e)[:80]))
    if H.LOCK in os.listdir(root):
        problems.append((i, op, "lock left"))
    shutil.rmtree(root)
print("values:", N)
for k, v in sorted(codes.items(), key=lambda kv: -kv[1])[:30]:
    print("  ", k, v)
print("problems:", len(problems))
for p in problems[:30]:
    print("  ", p)
