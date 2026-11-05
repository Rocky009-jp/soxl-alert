"""S4-D second edition re-review probes. Usage: python -B s4d_rereview_probe.py <tree with the 2nd trial applied> <tmp dir> <first probe path>
Y1 Z1/Z2 again: the pinned market.json has no row of the open session and is byte-equal to the control's
Y2 defect injection 21 alone (calendar check against the closed sessions only) on the Z1/Z2 inputs and the holiday row
Y3 a bar after the target with a bad value (NaN) and a null is dropped"""
import sys, datetime as dt, hashlib, math
ROOT, TMP, FIRST = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(FIRST).read().split("# Z1 / Z2")[0]
sys.argv = ["x", ROOT, TMP]
exec(compile(src, "probe", "exec"))
import v2_inputs.load as L

def pinned(g):
    return g.blob(g.fetch("v2-market"), "market.json")

out = {}
for tag, kw in (("control", {}), ("live1", {"live": "2026-07-23"}), ("live2", {"live": "2026-07-23", "live_dup": True})):
    g, hs, ob = world(); s = Sender()
    run(g, hs, ob, s, dt.datetime(2026, 7, 22, 7, 40, tzinfo=JST), Provider("2026-07-21"))
    inp, r = run(g, hs, ob, s, dt.datetime(2026, 7, 23, 23, 40, tzinfo=JST), Provider("2026-07-22", **kw))
    b = pinned(g); out[tag] = b
    print("Y1", tag, r.run_outcome, r.kind, r.delivery, "| 2026-07-23 in market.json:", b"2026-07-23" in b, "| sha", hashlib.sha256(b).hexdigest()[:12])
print("Y1 pinned bytes equal to control:", out["live1"] == out["control"], out["live2"] == out["control"])

# Y2: injection 21 alone -- the calendar check against the closed sessions only
orig = L._last_complete
def inj21(sessions_all, sessions_closed, by_symbol, now):
    return orig(sessions_closed, sessions_closed, by_symbol, now)
L._last_complete = inj21
for tag, kw in (("live1", {"live": "2026-07-23"}), ("live2", {"live": "2026-07-23", "live_dup": True})):
    g, hs, ob = world(); s = Sender()
    run(g, hs, ob, s, dt.datetime(2026, 7, 22, 7, 40, tzinfo=JST), Provider("2026-07-21"))
    inp, r = run(g, hs, ob, s, dt.datetime(2026, 7, 23, 23, 40, tzinfo=JST), Provider("2026-07-22", **kw))
    print("Y2 inj21", tag, r.run_outcome, r.code, r.kind, r.delivery)
SRC["SPY"]["2026-07-03"] = SRC["SPY"]["2026-07-02"]
g, hs, ob = world(); s = Sender()
inp, r = run(g, hs, ob, s, dt.datetime(2026, 7, 22, 7, 40, tzinfo=JST), Provider("2026-07-21"))
print("Y2 inj21 holiday row:", r.run_outcome, r.code, getattr(inp.failure, "detail", None))
del SRC["SPY"]["2026-07-03"]
L._last_complete = orig

# Y3: rows after the target with NaN / null values are dropped
import json
body = json.loads(chart("SOXX", "2026-07-22"))
res = body["chart"]["result"][0]
res["timestamp"] += [ts_of("2026-07-23"), ts_of("2026-07-24")]
res["indicators"]["quote"][0]["close"] += [float("nan"), None]
res["indicators"]["adjclose"][0]["adjclose"] += [float("nan"), None]
rows, _ = M.parse_chart(json.dumps(body).encode(), "SOXX", through="2026-07-22")
print("Y3 after-target NaN/null dropped:", max(rows), "2026-07-23" in rows)
try:
    M.parse_chart(json.dumps(body).encode(), "SOXX", through="2026-07-23")
except Exception as e:
    print("   with through=2026-07-23:", getattr(e, "code", type(e).__name__), getattr(e, "detail", None))
