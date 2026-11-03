"""Search for a plan that tells mutation 11 apart: READY, a CONSUME, no DROP, every REAPPLY same=true.
argv[1] = repo root. Read-only."""
import sys, os, itertools
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_history_consume"))
import c1_helpers as C
from v2_core.errors import CoreError
D, P, R, H = C.D, C.P, C.R, C.H
CONSUME = C.CONSUME
NONDROP = {"APPLY": ["REAPPLY"], "ACK": ["REPLAY"], "DECLARE_MISSING": ["REPLAY"], "RESTART_UNKNOWN": ["REPLAY"],
           "RECOVERY_RESTORE": ["RETIRE"]}

def scenarios():
    yield "declare", C.s_declare(), {}
    yield "gap", C.s_gap(), {}
    yield "restart_between", R.ex_restart_between(), {}
    yield "ack_between", R.ex_ack_between(), {}
    yield "old_skip", R.ex_old_skip(), {}
    yield "double_restart", R.ex_double_restart(), {}
    b, s, ses, ser = C.s_calendar()
    yield "calendar", b, {"sessions": ses, "series": ser, "extra": [s]}

stats = {"tried": 0, "ready_consume_nodrop": 0, "hits": 0, "refused": {}}
for name, b, kw in scenarios():
    extra = kw.pop("extra", [])
    applied = {e["d"] for e in b.events if e["kind"] == "APPLY"}
    days = [d for d in D[1:13] if d not in applied] + extra
    have = {r["date"] if "date" in r else None for r in []}
    base_ledger = list(b.w.ledger)
    chain = H.chain_of(b.events)
    check = max(D[13], max(extra) if extra else D[13])
    for p in chain:
        sup = chain[chain.index(p) + 1:]
        if not sup or len(sup) > 4:
            continue
        base = [(NONDROP[b.events[s]["kind"]][0], s) for s in sup]
        for n in (1, 2):
            for cdays in itertools.permutations(days, n):
                for places in itertools.combinations_with_replacement(range(len(base) + 1), n):
                    entries = list(base)
                    for off, (pl, d) in enumerate(sorted(zip(places, cdays))):
                        entries.insert(pl + off, (CONSUME, d))
                    stats["tried"] += 1
                    led = base_ledger + [P.obs("Z" + d, d, 40.0) for d in cdays
                                         if not any(r.get("target_us_session_date") == d for r in base_ledger)]
                    try:
                        plan = C.plan(b, p, entries, check, ledger=led, **{k: v for k, v in kw.items()})
                    except CoreError as e:
                        key = getattr(e, "rule", None) or e.code
                        stats["refused"][key] = stats["refused"].get(key, 0) + 1
                        continue
                    stats["ready_consume_nodrop"] += 1
                    print("READY", name, p, entries)
                    flags = [c["same_as_superseded"] for c in plan.basis["changes"] if c["op"] == "REAPPLY"]
                    if all(f is not False for f in flags):
                        stats["hits"] += 1
                        print("HIT", name, p, entries, flags)
print(stats)
