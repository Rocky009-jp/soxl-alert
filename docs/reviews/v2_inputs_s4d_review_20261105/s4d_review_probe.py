"""S4-D design review probes (reviewer's, not a request). Usage: python -B s4d_review_probe.py <tree with the trial applied> <tmp dir>
Z1 a live bar of the session still open (pin behind, run during US hours)
Z2 the same with Yahoo's separate live row (two rows of today)
Z3 an ex-dividend revision of the whole adjclose between D and D+1 (the next D runs, nothing stops)
Z4 a corrected early close of a day already consumed (session_context_mismatch)
Z5 a market.json whose through is far ahead of its rows
Z6 now before the first close of the table (no closed session)"""
import os, sys, json, csv, tempfile, subprocess, datetime as dt
ROOT = sys.argv[1]; TMP = sys.argv[2]
sys.path.insert(0, ROOT)
from v2_core.errors import InputError
from v2_history_publish import publish_genesis
from v2_git_store import Git, GitHistoryStore, GitOutbox
from v2_notify import morning_job
from v2_inputs import load_inputs, guarded_store, build_sessions
from v2_inputs.xnys import ny_offset, session_days
import v2_inputs.xnys as X
from v2_inputs import market as M

JST = dt.timezone(dt.timedelta(hours=9))
DATA = os.path.join(ROOT, "research/SOXL_initial_trend_20261023/data")
daily = json.load(open(os.path.join(DATA, "daily.json")))
adj = list(csv.DictReader(open(os.path.join(DATA, "daily_adjclose.csv"))))
fg = {r["Date"]: r["Fear Greed"] for r in csv.DictReader(open(os.path.join(DATA, "fear-greed.csv")))}
SRC = {"SOXX": {d: (a, a) for d, a in zip(daily["date"], daily["references"]["SOXX"]["adjClose"]) if a},
       "SOXL": {d: (c, c) for d, c in zip(daily["funds"]["SOXL"]["ohlcv"]["date"], daily["funds"]["SOXL"]["ohlcv"]["close"])},
       "SPY": {r["Date"]: (float(r["SPY"]), float(r["SPY"])) for r in adj if r["SPY"]},
       "IEF": {r["Date"]: (float(r["IEF"]), float(r["IEF"])) for r in adj if r["IEF"]}}

def ts_of(d, hh=9, mm=30):
    day = dt.date.fromisoformat(d)
    return int((dt.datetime(day.year, day.month, day.day, hh, mm) - ny_offset(day)).replace(tzinfo=dt.timezone.utc).timestamp())

def chart(symbol, upto, scale_before=None, live=None, live_dup=False):
    rows = sorted((d, v) for d, v in SRC[symbol].items() if d <= upto and d != "2026-05-25")
    ts = [ts_of(d) for d, _ in rows]; close = [v[0] for _, v in rows]
    adjc = [v[1] * (scale_before[1] if scale_before and d < scale_before[0] else 1.0) for d, v in rows]
    if live:                                   # today's bar while the session is open
        if not live_dup:
            ts.append(ts_of(live)); close.append(close[-1]); adjc.append(adjc[-1])
        else:                                  # the bar at the open and a separate live row of the same date
            ts += [ts_of(live), ts_of(live, 10, 15)]; close += [close[-1]] * 2; adjc += [adjc[-1]] * 2
    body = {"chart": {"result": [{"meta": {"symbol": symbol}, "timestamp": ts,
            "indicators": {"quote": [{"close": close}], "adjclose": [{"adjclose": adjc}]}}], "error": None}}
    return json.dumps(body).encode()

class Provider(object):
    def __init__(self, upto, **kw): self.upto, self.kw, self.calls = upto, kw, 0
    def __call__(self, symbol, start, end):
        self.calls += 1
        return chart(symbol, self.upto, **self.kw)

def sh(*a, cwd=None): return subprocess.run(a, cwd=cwd, check=True, capture_output=True)
CLOCK = lambda: dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
REFS = {"market": "v2-market", "ledger": "v2-ledger"}
COLS = "record_id,target_us_session_date,observation_role,observation_status,current_fg_value,observed_at_iso8601\n"
days = [d.isoformat() for d in session_days() if "2026-07-21" <= d.isoformat() <= "2026-08-10"]

class Sender(object):
    def __init__(self): self.sent = []
    def send(self, t): self.sent.append(t); return "SENT"

def world():
    o = tempfile.mkdtemp(prefix="SECRETMARK_", dir=TMP); sh("git", "init", "-q", "--bare", o)
    w = tempfile.mkdtemp(dir=TMP); sh("git", "init", "-q", w); sh("git", "remote", "add", "origin", o, cwd=w)
    p = tempfile.mkdtemp(dir=TMP); g = Git(w)
    hs, ob = GitHistoryStore(g, "v2-state", CLOCK), GitOutbox(g, "v2-outbox", p, CLOCK)
    ob.initialize()
    hs.initialize(publish_genesis("2026-07-20", build_sessions(dt.datetime(2026, 7, 21, 7, 40, tzinfo=JST), "2026-07-20")))
    return g, hs, ob

def put_ledger(g, upto_next):
    lines = [COLS]
    for d in days:
        nxt = dt.date.fromisoformat(d) + dt.timedelta(1)
        if nxt.isoformat() <= upto_next:
            lines.append("fg-%s,%s,decision,observed,%s,%sT07:05+09:00\n" % (d, d, fg[d], nxt.isoformat()))
    head = g.fetch("v2-ledger"); text = "".join(lines).encode()
    if head is None or g.blob(head, "observations.csv") != text:
        g.push(g.commit_with(head, "observations.csv", text, "ledger", CLOCK()), "v2-ledger")

def run(g, hs, ob, s, now, provider):
    put_ledger(g, now.astimezone(JST).date().isoformat())
    inp = load_inputs(g, provider, now, REFS, CLOCK)
    r = morning_job(guarded_store(hs, inp.failure), ob, s, now, inp.series, inp.sessions, inp.raw_observations)
    return inp, r

def show(tag, inp, r):
    f = inp.failure
    print(tag, "| failure:", None if f is None else "%s detail=%s" % (f.code, getattr(f, "detail", None)),
          "| run:", r.run_outcome, r.code, r.kind, r.delivery, "| pinned_by:", inp.provenance.get("pinned_by"),
          "through:", inp.provenance.get("market_through"))

# Z1 / Z2: the morning run of 7/23 failed to fetch (nothing pinned for 7/22); a retry at 7/23 10:40 New York (23:40 JST,
# the session of 7/23 is open) gets 7/22 plus today's live bar.
for tag, dup in (("Z1 live bar of the open session", False), ("Z2 live bar + separate live row", True)):
    g, hs, ob = world(); s = Sender()
    run(g, hs, ob, s, dt.datetime(2026, 7, 22, 7, 40, tzinfo=JST), Provider("2026-07-21"))
    now = dt.datetime(2026, 7, 23, 23, 40, tzinfo=JST)          # 2026-07-23 10:40 EDT
    inp, r = run(g, hs, ob, s, now, Provider("2026-07-22", live="2026-07-23", live_dup=dup))
    show(tag, inp, r)
    # control: the same retry, the data without today's bar
    g, hs, ob = world(); s = Sender()
    run(g, hs, ob, s, dt.datetime(2026, 7, 22, 7, 40, tzinfo=JST), Provider("2026-07-21"))
    inp, r = run(g, hs, ob, s, now, Provider("2026-07-22"))
    show("   control (no live bar)", inp, r)

# Z3: SOXX/SPY/IEF adjclose before 7/24 scaled by 0.997 on the fetch of 7/24 (an ex-dividend adjustment between D and D+1)
g, hs, ob = world(); s = Sender()
for d in days[:3]:
    nxt = dt.datetime.fromisoformat((dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat() + "T07:40:00+09:00")
    inp, r = run(g, hs, ob, s, nxt, Provider(d))
d = days[3]
nxt = dt.datetime.fromisoformat((dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat() + "T07:40:00+09:00")
inp, r = run(g, hs, ob, s, nxt, Provider(d, scale_before=(d, 0.997)))
show("Z3 next D after a whole-history adjustment", inp, r)
inp, r = run(g, hs, ob, s, nxt, Provider(d))
show("   same morning rerun (unadjusted fetch)", inp, r)

# Z4: 7/21..7/23 consumed with the table; then the table says 7/22 closed at 13:00 (an early close corrected later)
g, hs, ob = world(); s = Sender()
for d in days[:3]:
    nxt = dt.datetime.fromisoformat((dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat() + "T07:40:00+09:00")
    run(g, hs, ob, s, nxt, Provider(d))
keep = X.EARLY_CLOSES; X.EARLY_CLOSES = keep | {dt.date(2026, 7, 22)}
d = days[3]
nxt = dt.datetime.fromisoformat((dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat() + "T07:40:00+09:00")
inp, r = run(g, hs, ob, s, nxt, Provider(d))
show("Z4 early close of a consumed day added to the table", inp, r)
X.EARLY_CLOSES = keep

# Z5: market.json on v2-market says through=2026-12-31 but its rows end on 7/21
g, hs, ob = world(); s = Sender()
fetched = {x: M.parse_chart(chart(x, "2026-07-21"), x)[0] for x in M.SYMBOLS}
body = json.loads(M.snapshot_bytes("2026-07-21", fetched)); body["through"] = "2026-12-31"
data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
g.push(g.commit_with(None, "market.json", data, "hand edit", CLOCK()), "v2-market")
inp, r = run(g, hs, ob, s, dt.datetime(2026, 7, 24, 7, 40, tzinfo=JST), Provider("2026-07-23"))
show("Z5 through ahead of the rows", inp, r)
sl = inp.sessions
print("   sessions confirmed after now:", sum(1 for x in sl.sessions if x.confirmed and x.close_at > dt.datetime(2026, 7, 24, 7, 40, tzinfo=JST)))

# Z6: now before the first close of the table, with a pin on the ref
try:
    load_inputs(g, Provider("2026-07-21"), dt.datetime(2026, 1, 2, 12, 0, tzinfo=dt.timezone.utc), REFS, CLOCK)
    print("Z6 returned")
except Exception as e:
    print("Z6 raised:", type(e).__name__, getattr(e, "code", ""))
