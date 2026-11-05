"""S4-E review probes Z1-Z2 (reuses the setup of the trial probe s4e_trial.py: fake urlopen, local bare remote)."""
import os, sys, json, csv, tempfile, subprocess, time, socket, io, datetime as dt, urllib.error
ROOT = sys.argv[1]; TMP = sys.argv[2]; sys.path.insert(0, ROOT)
from v2_git_store import Git
from v2_inputs.xnys import ny_offset, session_days
from v2_notify import morning_job, LocalOutbox, outbox_status
from v2_run import main, split_text, DiscordSender, live_text
from v2_run.entry import Setup

JST = dt.timezone(dt.timedelta(hours=9))
DATA = os.path.join(ROOT, "research/SOXL_initial_trend_20261023/data")
daily = json.load(open(os.path.join(DATA, "daily.json")))
adj = list(csv.DictReader(open(os.path.join(DATA, "daily_adjclose.csv"))))
fg = {r["Date"]: r["Fear Greed"] for r in csv.DictReader(open(os.path.join(DATA, "fear-greed.csv")))}
SRC = {"SOXX": {d: a for d, a in zip(daily["date"], daily["references"]["SOXX"]["adjClose"]) if a},
       "SOXL": {d: c for d, c in zip(daily["funds"]["SOXL"]["ohlcv"]["date"], daily["funds"]["SOXL"]["ohlcv"]["close"])},
       "SPY": {r["Date"]: float(r["SPY"]) for r in adj if r["SPY"]}, "IEF": {r["Date"]: float(r["IEF"]) for r in adj if r["IEF"]}}
WEBHOOK = "https://discord.com/api/webhooks/123/SECRETTOKEN_abc"

def ts_of(d, hh=9, mm=30):
    day = dt.date.fromisoformat(d)
    return int((dt.datetime(day.year, day.month, day.day, hh, mm) - ny_offset(day)).replace(tzinfo=dt.timezone.utc).timestamp())

class Resp(io.BytesIO):
    def __init__(self, data, status=200): super().__init__(data); self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): self.close()

class Net(object):
    """Fake urlopen. chart: rows of the research data up to self.upto (and an optional live bar of today);
    discord: self.discord is a list of behaviours, one per post ('204', '400', '500', 'refused', 'timeout')."""
    def __init__(self): self.upto, self.discord, self.posts, self.charts, self.live = None, [], [], 0, None
    def __call__(self, req, timeout=None):
        url = req.full_url
        if url.startswith("https://query1.finance.yahoo.com/"):
            self.charts += 1
            sym = url.split("/chart/")[1].split("?")[0]
            rows = sorted((d, v) for d, v in SRC[sym].items() if d <= self.upto and d != "2026-05-25")
            ts = [ts_of(d) for d, _ in rows]; vals = [v for _, v in rows]
            if self.live:                                        # R-02 shape: two rows of one date after the close
                ts.append(ts_of(self.live, 16, 0)); vals.append(vals[-1])
            body = {"chart": {"result": [{"meta": {"symbol": sym}, "timestamp": ts,
                    "indicators": {"quote": [{"close": vals}], "adjclose": [{"adjclose": vals}]}}], "error": None}}
            return Resp(json.dumps(body).encode())
        if url.startswith("https://discord.com/api/webhooks/"):
            b = self.discord.pop(0) if self.discord else "204"
            body = json.loads(req.data.decode()); self.posts.append((b, body["content"], body.get("allowed_mentions")))
            if b in ("204", "200"): return Resp(b"{}", 200)
            if b in ("400", "429", "500"): raise urllib.error.HTTPError(url, int(b), "x", {}, io.BytesIO(b""))
            if b == "refused": raise urllib.error.URLError(ConnectionRefusedError(111, "refused " + url))
            if b == "timeout": raise socket.timeout("timed out " + url)
        raise AssertionError("unexpected url")

def sh(*a, cwd=None): return subprocess.run(a, cwd=cwd, check=True, capture_output=True)
o = tempfile.mkdtemp(prefix="SECRETPATH_", dir=TMP); sh("git", "init", "-q", "--bare", o)
def clone():
    w = tempfile.mkdtemp(prefix="SECRETPATH_w", dir=TMP); sh("git", "init", "-q", w); sh("git", "remote", "add", "origin", o, cwd=w)
    return w
W = clone(); G = Git(W)
CLOCK = lambda: dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
COLS = "record_id,target_us_session_date,observation_role,observation_status,current_fg_value,observed_at_iso8601\n"
days = [d.isoformat() for d in session_days() if "2026-07-20" <= d.isoformat() <= "2026-08-10"]
def ledger_upto(next_day):
    rows = [COLS] + ["fg-%s,%s,decision,observed,%s,%sT07:05+09:00\n" % (d, d, fg[d], (dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat())
                     for d in days if (dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat() <= next_day]
    want = "".join(rows).encode(); head = G.fetch("v2-ledger")
    if head is None or G.blob(head, "observations.csv") != want:
        G.push(G.commit_with(head, "observations.csv", want, "user ledger", CLOCK()), "v2-ledger")
NET = Net(); OUT = []
def run(args, day, hhmm="07:40", env=None):
    now = dt.datetime.fromisoformat("%sT%s:00+09:00" % (day, hhmm)).astimezone(dt.timezone.utc)
    OUT.clear(); summary = os.path.join(tempfile.mkdtemp(dir=TMP), "summary.md")
    e = {"GITHUB_STEP_SUMMARY": summary}; e.update(env or {})
    code = main(args + ["--workdir", W, "--code-version", "0" * 40], env=e, out=OUT.append, now_fn=lambda: now, urlopen=NET)
    text = OUT[0]
    return code, dict(l[2:].split(": ", 1) for l in text.splitlines() if l.startswith("- ")), text

ALL = []

def nxt_of(d): return (dt.date.fromisoformat(d) + dt.timedelta(1)).isoformat()
def ledger_rows(pairs):
    """pairs: [(d, observed day, hh:mm)] -> push observations.csv with exactly these decision rows."""
    rows = [COLS] + ["fg-%s,%s,decision,observed,%s,%sT%s+09:00\n" % (d, d, fg[d], od, hm) for d, od, hm in pairs]
    want = "".join(rows).encode(); head = G.fetch("v2-ledger")
    if head is None or G.blob(head, "observations.csv") != want:
        G.push(G.commit_with(head, "observations.csv", want, "user ledger", CLOCK()), "v2-ledger")
def text_of(t): return t.split("```")[1].strip() if "```" in t else ""
def line(text, head): return [l for l in text.splitlines() if l.startswith(head)]

# ---- Z1: the decision of D is written after the 7:40 run but before the 8:40 run
c, kv, t = run(["init", "--mode", "dry", "--start-after", "2026-07-20"], "2026-07-21", "07:00")
pairs = []
for d in days[1:4]:
    pairs.append((d, nxt_of(d), "07:05")); NET.upto = d; ledger_rows(pairs)
    run(["morning", "--mode", "dry"], nxt_of(d))
d = days[4]; NET.upto = d; ledger_rows(pairs)                          # 7:40: no decision of D yet
c, kv, t = run(["morning", "--mode", "dry"], nxt_of(d), "07:40")
print("Z1 7:40 (no decision yet)  exit", c, kv["run_outcome"], kv["key"], kv["delivery"], "consumed=", kv.get("consumed"))
print("   ", line(text_of(t), "F&G現在値"), line(text_of(t), "  F&Gの値による分岐"))
pairs.append((d, nxt_of(d), "07:50")); ledger_rows(pairs)             # the user writes it at 7:50
c, kv, t = run(["morning", "--mode", "dry"], nxt_of(d), "08:40")
print("Z1 8:40 (decision written 7:50) exit", c, kv["run_outcome"], kv["key"], kv["delivery"], "consumed=", kv.get("consumed"), "dry text sent:", bool(text_of(t)))

# ---- Z2: the live start: a fresh boundary vs the boundary of the trial
for d in days[5:12]:
    pairs.append((d, nxt_of(d), "07:05"))
last = days[11]; NET.upto = last; ledger_rows(pairs)
c, kv, t = run(["morning", "--mode", "dry"], nxt_of(last))
print("Z2 dry  D=%s consumed=%s" % (last, kv.get("consumed")), line(text_of(t), "市場状態"))
c, kv, t = run(["init", "--mode", "live", "--start-after", days[10]], nxt_of(days[10]), "07:00")
NET.discord = ["204"]
c, kv, t = run(["morning", "--mode", "live"], nxt_of(last), env={"V2_DISCORD_WEBHOOK_URL": WEBHOOK})
print("Z2 live start_after=%s exit %s %s" % (days[10], c, kv["delivery"]), line(NET.posts[-1][1], "市場状態"), line(NET.posts[-1][1], "  前日までの"))
# the same live start with the boundary of the trial (a second remote, so the refs are fresh)
o2 = tempfile.mkdtemp(prefix="SECRETPATH_", dir=TMP); sh("git", "init", "-q", "--bare", o2)
sh("git", "push", "-q", o, "refs/v2remote/v2-ledger:refs/heads/v2-ledger", cwd=W)
sh("git", "fetch", "-q", o, "+refs/heads/v2-ledger:refs/heads/tmp-ledger", cwd=W); sh("git", "push", "-q", o2, "refs/heads/tmp-ledger:refs/heads/v2-ledger", cwd=W)
W2 = tempfile.mkdtemp(prefix="SECRETPATH_w", dir=TMP); sh("git", "init", "-q", W2); sh("git", "remote", "add", "origin", o2, cwd=W2)
W_saved, W = W, W2
c, kv, t = run(["init", "--mode", "live", "--start-after", "2026-07-20"], "2026-07-21", "07:00")
t0 = time.monotonic(); NET.discord = ["204"]
c, kv, t = run(["morning", "--mode", "live"], nxt_of(last), env={"V2_DISCORD_WEBHOOK_URL": WEBHOOK})
print("Z2 live start_after=2026-07-20 exit %s %s consumed=%d days %.1fs" % (c, kv["delivery"], len(kv["consumed"].split()), time.monotonic() - t0),
      line(NET.posts[-1][1], "市場状態"))
