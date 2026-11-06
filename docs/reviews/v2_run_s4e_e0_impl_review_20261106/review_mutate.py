#!/usr/bin/env python3
"""Independent mutations of the S4-E review. usage: vmut.py REPO REV PY JOBS OUT.json [ids]"""
import json, os, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
REPO, REV, PY, JOBS, OUT = sys.argv[1:6]
ONLY = set(sys.argv[6:])
E, W, K = "v2_run/entry.py", "v2_run/web.py", "v2_run/check.py"
M = [
 ("V00", "baseline: no change", E, "COMMANDS = (", "COMMANDS = ("),
 ("V01", "a refused connection wrapped in URLError is UNKNOWN", W,
  "answer = \"refused\" if isinstance(error.reason, (ConnectionRefusedError, socket.gaierror)) else \"unsure\"",
  "answer = \"refused\" if isinstance(error.reason, socket.gaierror) else \"unsure\""),
 ("V02", "a DNS failure wrapped in URLError is UNKNOWN", W,
  "answer = \"refused\" if isinstance(error.reason, (ConnectionRefusedError, socket.gaierror)) else \"unsure\"",
  "answer = \"refused\" if isinstance(error.reason, ConnectionRefusedError) else \"unsure\""),
 ("V03", "a raw ConnectionRefusedError is UNKNOWN", W,
  "        except (ConnectionRefusedError, socket.gaierror):\n            answer = \"refused\"\n", ""),
 ("V04", "fetch: a raw ConnectionError is other", W,
  "    if isinstance(error, (ConnectionError, socket.gaierror)):\n        return \"url_error\"\n", ""),
 ("V05", "fetch: no Accept header", W, ", \"Accept\": \"application/json\"", ""),
 ("V06", "morning: SKIPPED_JUDGMENT_EXISTS ends with 1", E,
  "OK_DELIVERIES = (SENT, SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS)", "OK_DELIVERIES = (SENT, SKIPPED_CLAIMED)"),
 ("V07", "morning: a raised load_inputs ends with 0 when the error was sent", E,
  "return 0 if (raised is None and job.delivery in OK_DELIVERIES) else 1", "return 0 if job.delivery in OK_DELIVERIES else 1"),
 ("V08", "check-source: end is the UTC date + 1", K,
  "    return (ny_date(now) + dt.timedelta(days=1)).isoformat()",
  "    return (now.astimezone(dt.timezone.utc).date() + dt.timedelta(days=1)).isoformat()"),
 ("V09", "check-source: pin_last_close_changed compares the adjusted close", K,
  "last[0] != pinned.get(through, (None,))[0]", "last[1] != pinned.get(through, (None, None))[1]"),
 ("V10", "check-source: research-only and response-only swapped", K,
  "facts[\"pre2026_only_in_research\"] = len(ref - before)", "facts[\"pre2026_only_in_research\"] = len(before - ref)"),
 ("V11", "split: >= instead of > at the join", W, "elif len(cur) + 1 + len(line) > limit:", "elif len(cur) + 1 + len(line) >= limit:"),
 ("V12", "summary file overwritten, not appended", E, "with open(path, \"a\", encoding=\"utf-8\") as f:", "with open(path, \"w\", encoding=\"utf-8\") as f:"),
 ("V13", "dry also builds a DiscordSender from the env (unused)", E,
  "        self.sender = DrySender() if mode == \"dry\" else DiscordSender(env.get(SECRET_NAME), urlopen)",
  "        _unused = DiscordSender(env.get(SECRET_NAME), urlopen)\n        self.sender = DrySender() if mode == \"dry\" else _unused"),
 ("V14", "why() shows the text of an exception without a code", E,
  "    return type(error).__name__ + (\"（%s）\" % code if type(code) is str else \"\")",
  "    return type(error).__name__ + (\"（%s）\" % code if type(code) is str else \" \" + str(error))"),
 ("V15", "resend refused only when the morning is SENT", E,
  "s.outbox.status(d, MORNING).status != NONE:", "s.outbox.status(d, MORNING).status == SENT:"),
 ("V16", "init: the outbox is made even when the history failed, before it", E,
  "    first = _create(rec, \"state\", state_missing, lambda: s.store.initialize(publish_genesis(start_after, sessions)))\n    second = _create(rec, \"outbox\", outbox_missing, s.outbox.initialize)",
  "    second = _create(rec, \"outbox\", outbox_missing, s.outbox.initialize)\n    first = _create(rec, \"state\", state_missing, lambda: s.store.initialize(publish_genesis(start_after, sessions)))"),
 ("V17", "check-source exits 0 after a failed fetch", E, "            worst = 1\n", ""),
 ("V18", "check-source reads the pin of the state ref", E, "MarketPin(s.git, s.refs[\"market\"], s.clock).read()", "MarketPin(s.git, s.refs[\"state\"], s.clock).read()"),
 ("V19", "a later part refused (4xx) at index 1 is NOT_STARTED", W, "answer == \"refused\" and index == 0", "answer == \"refused\" and index <= 1"),
 ("V20", "http status 2xx other than 200 accepted by the fetch", W, "if status != 200:", "if not (200 <= (status or 0) < 300):"),
 ("V21", "status reads a fresh outbox of the other mode", E, "for entry in outbox_status(s.outbox, d):", "for entry in outbox_status(GitOutbox(s.git, MODES['live' if s.mode == 'dry' else 'dry']['outbox'], tempfile.mkdtemp(), s.clock), d):"),
 ("V22", "the record of outbox_files counts the state ref", E, "head = s.git.fetch(s.refs[\"outbox\"])", "head = s.git.fetch(s.refs[\"state\"])"),
 ("V23", "the dry text block is replaced to the live heading", E, "rec.block(\"text (dry: not sent)\", s.sender.texts[-1])", "rec.block(\"text (dry: not sent)\", live_text(s.sender.texts[-1]))"),
 ("V24", "inspect: target_rows counts all rows", K, "facts[\"target_rows\"] = sum(1 for day, _clock in days_of if day == target)", "facts[\"target_rows\"] = sum(1 for day, _clock in days_of if day >= target)"),
 ("V25", "the entry exception exits 0", E, "        rec.add(\"failed\", why(error))\n        code = 1", "        rec.add(\"failed\", why(error))\n        code = 0"),
 ("V26", "the code_version is recorded as given", E, "args.code_version if _SHA.fullmatch(args.code_version or \"\") else \"unknown\"", "args.code_version or \"unknown\""),
 ("V27", "inspect: null rows counted in the table days that have a value", K, "have = {d for d, v in rows.items() if v[0] is not None and v[1] is not None}", "have = set(rows)"),
 ("V28", "init: a refused start_after still creates the outbox", E, "        rec.add(\"refused\", \"start_after_not_a_closed_session\")\n        return 1", "        rec.add(\"refused\", \"start_after_not_a_closed_session\")\n        s.outbox.initialize()\n        return 1"),
]
if "V23" in [m[0] for m in M]:
    pass
def run(m):
    mid, desc, path, old, new = m
    d = tempfile.mkdtemp(prefix="vm_")
    subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "-q", "--shared", REPO, d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "-q", REV], check=True)
    p = os.path.join(d, path); src = open(p, encoding="utf-8").read()
    if src.count(old) != 1:
        shutil.rmtree(d, True); return {"id": mid, "desc": desc, "result": "setup_failed", "count": src.count(old)}
    src = src.replace(old, new)
    if mid == "V23":
        src = src.replace("from .web import DiscordSender, DrySender, make_fetch, real_urlopen", "from .web import DiscordSender, DrySender, live_text, make_fetch, real_urlopen")
    open(p, "w", encoding="utf-8").write(src)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    t = time.time()
    r = subprocess.run([PY, "-B", "-m", "unittest", "discover", "-f", "-s", "tests/v2_run", "-p", "test_s4e_*.py"], cwd=d, env=env, capture_output=True, text=True)
    out = r.stderr
    fails = [l for l in out.splitlines() if l.startswith(("FAIL:", "ERROR:"))]
    shutil.rmtree(d, True)
    res = {"id": mid, "desc": desc, "result": "detected" if r.returncode else "survived", "failed": fails[:6], "nfail": len(fails), "sec": round(time.time() - t)}
    with open(OUT + ".lines", "a") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    return res
ms = [m for m in M if not ONLY or m[0] in ONLY]
with ThreadPoolExecutor(int(JOBS)) as ex:
    res = list(ex.map(run, ms))
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)
for x in res:
    print(x["id"], x["result"], x.get("nfail"), x.get("sec"), x["desc"], (x.get("failed") or [""])[0])
