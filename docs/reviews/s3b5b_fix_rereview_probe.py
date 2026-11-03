"""Independent re-review checks for the S3-B-5b R-01 fix (fix/v2-history-adopt-s3b5b-review-20261103).
Synthetic data only; calls public APIs and the existing test helpers; writes nothing.
Usage: python -B -I docs/reviews/s3b5b_fix_rereview_probe.py --repo <complete checkout> [--seed N] [--n N]
  A: real diagnoses with junk discarded tails -> CONFIRMED_IN_MEMORY on the raw bytes and NO_CHANGE on the candidate.
  B: random edits of plan.basis.discarded with plan_hash recomputed, judged by an independent reading of the fix
     request section 3: well formed -> NO_CHANGE on the candidate bytes; malformed -> history_plan_mismatch on all paths.
  C: strict integers for from_index and item index (float 6.0, and True when adopt_count is 1) -> mismatch.
Exit 0 when no finding. Reference run: 61659892086b559a4e9c62caedcc79145f0b75dd, Python 3.13.18, seed 20261103, n 3000."""
import argparse, copy, datetime, json, random, re, sys, collections
ap = argparse.ArgumentParser(); ap.add_argument("--repo"); ap.add_argument("--seed", type=int, default=20261103)
ap.add_argument("--n", type=int, default=3000); a = ap.parse_args()
sys.path[:0] = [a.repo, a.repo + "/tests/v2_history_adopt"]
import a5_helpers as Z
from a5_helpers import H, X
from v2_persistence.errors import PersistenceError
from v2_persistence.codec import canonical_json, sha256_text
from v2_history import KINDS
rnd = random.Random(a.seed)
RID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

def out(plan, data):
    try:
        return Z.A.confirm_prefix_adoption(plan, plan.plan_hash, data).status
    except PersistenceError as e:
        return (e.code, e.field, e.rule)
    except Exception as e:            # anything else is a finding
        return ("UNEXPECTED", type(e).__name__, str(e)[:80])

def real_date(x):
    if type(x) is not str: return False
    try: return datetime.date.fromisoformat(x).isoformat() == x
    except ValueError: return False

def ref_ok(block, k):            # independent reading of request section 3
    if type(block) is not dict or set(block) != {"from_index", "count", "items"}: return False
    f, c, it = block["from_index"], block["count"], block["items"]
    if type(f) is not int or f != k or type(c) is not int or c < 0 or type(it) is not list or len(it) != c: return False
    for p, i in enumerate(it):
        if type(i) is not dict or set(i) != {"index", "kind", "seq", "d", "request_id"}: return False
        if type(i["index"]) is not int or i["index"] != f + p: return False
        if not (i["kind"] == "?" or (type(i["kind"]) is str and i["kind"] in KINDS)): return False
        if not (i["seq"] is None or type(i["seq"]) is int): return False
        if not (i["d"] is None or real_date(i["d"])): return False
        if not (i["request_id"] is None or (type(i["request_id"]) is str and RID.fullmatch(i["request_id"]))): return False
    return True

JUNK = [None, True, False, 0, -1, 1, 7, 2**70, -2**70, 1.0, -0.0, "", "?", "APPLY", "apply", "GENESIS", "BOGUS",
        "2026-01-02", "2026-02-30", "2026-1-2", "20260102", "2026-01-02T00:00", "rid-1", "-bad", "a" * 64, "a" * 65,
        "é", [], {}, [1], {"a": 1}]
def jv(): return rnd.choice(JUNK + list(KINDS))

# ---- A: real diagnoses with junk tails are never refused (no false mismatch) --------------------------------------
stats = collections.Counter(); bad = []
base = X.ex_new().events
for n in range(a.n // 3):
    ev = copy.deepcopy(base)
    k = rnd.randint(1, len(ev) - 1)
    tail = []
    for j in range(rnd.randint(0, 5)):
        if rnd.random() < 0.2: tail.append(jv()); continue
        rec = {}
        for key in ("kind", "seq", "d", "request_id", "x"):
            if rnd.random() < 0.85: rec[key] = jv()
        tail.append(rec)
    mode = rnd.random()
    if mode < 0.5:   # damaged record k, then junk
        evs = X.with_hash(ev, k)[: rnd.randint(k + 1, len(ev))] + tail
    else:            # junk directly after a good prefix of k records
        evs = ev[:k] + tail
        if not tail: evs = X.with_hash(ev, k)
    doc = H.header(evs[:k]); doc["events"] = evs
    data = X.doc_bytes(doc)
    d = X.diagnose(data)
    if d.get("status") != "PREFIX_ONLY" or not d.get("verified"):
        stats["A_not_prefix_only"] += 1; continue
    kk = d["verified"]["count"]
    try:
        plan = Z.prep(data, kk)
    except PersistenceError as e:
        stats["A_prepare_refused:" + e.code + "/" + str(e.rule)] += 1; continue
    r1, r2 = out(plan, data), out(plan, Z.candidate_bytes(data, kk))
    ok = (r1 == "CONFIRMED_IN_MEMORY" and r2 == "NO_CHANGE" and ref_ok(plan.basis["discarded"], kk))
    stats["A_ok" if ok else "A_BAD"] += 1
    if not ok: bad.append(("A", r1, r2, plan.basis["discarded"]))

# ---- B: random plan edits of the discarded block, hash recomputed ---------------------------------------------------
_b, data, k = Z.new_world()
plan = Z.prep(data, k); block = plan.basis["discarded"]; cand = Z.candidate_bytes(data, k)
MIS = ("history_plan_mismatch", "plan", None)
def mutate(b):
    b = copy.deepcopy(b)
    for _ in range(rnd.randint(1, 3)):
        t = rnd.randrange(9)
        if t == 0: b = jv()
        elif type(b) is not dict: continue
        elif t == 1: b[rnd.choice(["from_index", "count", "items", "extra"])] = jv()
        elif t == 2 and b: del b[rnd.choice(list(b))]
        elif t == 3 and type(b.get("items")) is list and b["items"] and type(b["items"][0]) is dict:
            i = rnd.randrange(len(b["items"])); it = b["items"][i]
            if type(it) is dict: it[rnd.choice(["index", "kind", "seq", "d", "request_id", "zz"])] = jv()
        elif t == 4 and type(b.get("items")) is list:   # append a well formed item and maybe fix the count
            items = b["items"]; base_i = b.get("from_index", k) if type(b.get("from_index")) is int else k
            items.append({"index": base_i + len(items), "kind": rnd.choice(list(KINDS) + ["?"]),
                          "seq": rnd.choice([None, -3, 0, 99]), "d": rnd.choice([None, "2026-03-04"]),
                          "request_id": rnd.choice([None, "x1"])})
            if rnd.random() < 0.7: b["count"] = len(items)
        elif t == 5 and type(b.get("items")) is list and b["items"]:
            b["items"].pop(rnd.randrange(len(b["items"])))
            if rnd.random() < 0.7: b["count"] = len(b["items"])
        elif t == 6 and type(b.get("items")) is list and b["items"]:
            rnd.shuffle(b["items"])
        elif t == 7: b["from_index"] = rnd.choice([k, k + 1, k - 1, True, float(k)])
        elif t == 8: b["count"] = rnd.choice([0, -1, True, False, b.get("count")])
    return b
for n in range(a.n):
    mb = mutate(block)
    p2 = Z.refreshed(plan, lambda d: d["basis"].__setitem__("discarded", mb))
    exp_ok = ref_ok(mb, k)
    res = {name: out(p2, x) for name, x in (("cand", cand), ("raw", data), ("none", None), ("other", b"{}"))}
    if any(isinstance(v, tuple) and v[0] == "UNEXPECTED" for v in res.values()):
        stats["B_UNEXPECTED"] += 1; bad.append(("B", mb, res)); continue
    if exp_ok:
        same = mb == block
        good = (res["cand"] == "NO_CHANGE" and res["raw"] == ("CONFIRMED_IN_MEMORY" if same else MIS)
                and res["none"] == ("adoption_invalid", "data", "type") and res["other"] == ("history_plan_stale", "plan", None))
        stats["B_wellformed_ok" if good else "B_wellformed_BAD"] += 1
        if not same: stats["B_wellformed_but_changed(NO_CHANGE_on_candidate)"] += 1
    else:
        good = all(v == MIS for v in res.values())
        stats["B_malformed_all_mismatch" if good else "B_malformed_BAD"] += 1
    if not good: bad.append(("B", mb, res))
# ---- C: strict integers that the equality alone does not catch -----------------------------------------------------
for name, (dat, kc) in (("k6", Z.damaged_last(X.ex_new())), ("k1", Z.damaged_at(X.ex_new(), 1))):
    pc = Z.prep(dat, kc); bc = pc.basis["discarded"]; cc = Z.candidate_bytes(dat, kc); f = bc["items"][0]
    for label, v in (("float_start", dict(bc, from_index=float(kc))), ("bool_start", dict(bc, from_index=True)),
                     ("float_index", dict(bc, items=[dict(f, index=float(f["index"]))] + bc["items"][1:]))):
        if label == "bool_start" and kc != 1: continue
        r = out(Z.refreshed(pc, lambda d: d["basis"].__setitem__("discarded", v)), cc)
        stats["C_%s_%s_mismatch" % (name, label) if r == MIS else "C_%s_%s_BAD" % (name, label)] += 1
        if r != MIS: bad.append(("C", name, label, r))
for kk, v in sorted(stats.items()): print(kk, v)
print("FINDINGS", len(bad))
for x in bad[:10]: print(json.dumps(x, default=str)[:400])
sys.exit(1 if bad else 0)
