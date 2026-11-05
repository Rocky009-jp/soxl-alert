"""Helpers for the S4-E (entry of the morning run) tests (never imported by the runtime).

The real `urllib.request.urlopen` is replaced at import by a function that fails the test, and sockets are disabled by the
helpers this file imports: the only network of the tests is the fake `urlopen` (`Net`) that is passed to `main`. The S4-D, S4-C,
S4-B and S4-A helpers (and through them the existing ones) are only imported, never changed. The only remotes are bare
repositories in a temporary directory whose path carries the mark SECRETMARK_; the webhook URL carries the mark SECRETTOKEN_
and the responses of a failed post carry SECRETBODY_. The chart responses are bytes in the shape of the chart API made from the
research data by the S4-D helper; the expected values come from the research fixture, from `git` called directly, and from the
requests that the fake `urlopen` received (never from the code under test).
"""
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_inputs")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import s4d_helpers as D  # noqa: E402  (existing helper; it also disables sockets)


def _real_urlopen_is_forbidden(*args, **kwargs):
    raise AssertionError("the real urlopen was called")


urllib.request.urlopen = _real_urlopen_is_forbidden        # a test that reaches the real network fails

import v2_run as R  # noqa: E402
from v2_run import entry as ENTRY  # noqa: E402
from v2_run import web as WEB  # noqa: E402

C, B, I, N = D.C, D.B, D.I, D.N
GS = C.GS
tgit = C.tgit
WORKER = os.path.join(HERE, "s4e_worker.py")
MARK = C.MARK
TOKEN_MARK = "SECRETTOKEN_"
BODY_MARK = "SECRETBODY_"
WEBHOOK = "https://discord.com/api/webhooks/123456/" + TOKEN_MARK + "abcdef"
CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
UTC = timezone.utc
CODE = "0" * 40
START = "2026-07-20"
SYMBOLS = ("SOXX", "SPY", "IEF", "SOXL")
STATE_REFS = {"dry": ("v2-dry-state", "v2-dry-outbox", "v2-dry-market"), "live": ("v2-state", "v2-outbox", "v2-market")}


# --- the fake network -------------------------------------------------------------------------------------------------
class Resp(io.BytesIO):
    """A response of the fake urlopen: bytes with a status, usable as a context manager."""

    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def http_error(url, code):
    return urllib.error.HTTPError(url, code, "reason " + url, {}, io.BytesIO(("body " + BODY_MARK).encode("ascii")))


class Net(object):
    """The fake urlopen. A chart request is answered from the research rows up to `upto` (the S4-D Provider; `kw` goes to it),
    unless `override[symbol]` says otherwise: bytes, an exception, ("status", n), ("size", n). A Discord request takes the next
    behaviour of `discord` (default "204"): "204", "200", "400", "401", "404", "429", "500", "503", "refused", "dns", "timeout",
    "url_timeout", "other", "202" (a 2xx that is not 204). Every request is recorded; anything else fails the test."""

    def __init__(self, upto=None, **kw):
        self.provider = D.Provider(upto, **kw) if upto is not None else None
        self.override, self.discord, self.requests, self.chart_args = {}, [], [], []

    @property
    def upto(self):
        return self.provider.upto

    @upto.setter
    def upto(self, value):
        self.provider.upto = value

    def posts(self):
        return [r for r in self.requests if r["kind"] == "discord"]

    def charts(self):
        return [r for r in self.requests if r["kind"] == "chart"]

    def __call__(self, request, timeout=None):
        url = request.full_url
        record = {"url": url, "method": request.get_method(), "timeout": timeout,
                  "headers": {k.lower(): v for k, v in request.header_items()}, "data": request.data}
        self.requests.append(record)
        if url.startswith(CHART_BASE):
            return self._chart(url, record)
        if url.startswith(WEB.WEBHOOK_PREFIXES):
            return self._discord(url, record)
        raise AssertionError("unexpected url")

    def _chart(self, url, record):
        record["kind"] = "chart"
        symbol = url[len(CHART_BASE):].split("?")[0]
        query = dict(p.split("=") for p in url.split("?")[1].split("&"))
        start, end = (datetime.fromtimestamp(int(query[k]), UTC).date().isoformat() for k in ("period1", "period2"))
        record["symbol"] = symbol
        self.chart_args.append((symbol, start, end))
        answer = self.override.get(symbol)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, tuple) and answer[0] == "status":
            return Resp(b"{}", answer[1])
        if isinstance(answer, tuple) and answer[0] == "size":
            return Resp(b"x" * answer[1])
        if isinstance(answer, bytes):
            return Resp(answer)
        return Resp(self.provider(symbol, start, end))

    def _discord(self, url, record):
        record["kind"] = "discord"
        body = json.loads(request_body(record))
        record["content"], record["mentions"] = body["content"], body.get("allowed_mentions")
        behaviour = self.discord.pop(0) if self.discord else "204"
        record["behaviour"] = behaviour
        if behaviour in ("204", "200", "202"):
            return Resp(b"{}", int(behaviour))
        if behaviour in ("400", "401", "404", "429", "500", "503"):
            raise http_error(url, int(behaviour))
        if behaviour == "refused":
            raise urllib.error.URLError(ConnectionRefusedError(111, "refused " + url))
        if behaviour == "dns":
            raise urllib.error.URLError(socket.gaierror(-2, "unknown host " + url))
        if behaviour == "timeout":
            raise socket.timeout("timed out " + url)
        if behaviour == "url_timeout":
            raise urllib.error.URLError(TimeoutError("timed out " + url))
        raise RuntimeError("other " + url + " " + BODY_MARK)


def request_body(record):
    return record["data"].decode("utf-8")


# --- one entry call ---------------------------------------------------------------------------------------------------
class Clock(object):
    """The clock passed to main: the first call gives `now`, every later call gives it plus `step` seconds more than the one
    before (so that the commits and the time of a pin differ from `now` when step is not 0). `calls` counts the reads."""

    def __init__(self, now, step=0):
        self.now, self.step, self.calls = now, step, 0

    def __call__(self):
        value = self.now + timedelta(seconds=self.step * self.calls)
        self.calls += 1
        return value


class Result(object):
    """What main returned and wrote: the exit code, the lines as (key, value) pairs, the text, the summary file's text."""

    def __init__(self, code, text, summary, clock):
        self.code, self.text, self.summary, self.clock = code, text, summary, clock
        self.pairs = [tuple(line[2:].split(": ", 1)) for line in text.splitlines() if line.startswith("- ") and ": " in line]
        self.kv = dict(self.pairs)

    def all(self, key):
        return [v for k, v in self.pairs if k == key]

    def block(self):
        parts = self.text.split("```")
        return parts[1].strip("\n") if len(parts) >= 3 else None


def aware(day, hour=7, minute=40):
    """The time of the run of the morning of the day after `day` (Japan time), as a UTC time."""
    return D.jst_morning(day, hour, minute).astimezone(UTC)


class Work(object):
    """A bare remote (path with the mark) and the work directory (a clone with the remote configured), and what a test reads
    of them with git directly."""

    def __init__(self, case):
        self.case = case
        self.remote = C.Remote(case)
        self.dir = tempfile.mkdtemp(prefix="v2s4e_work_")
        case.addCleanup(shutil.rmtree, self.dir, True)
        tgit(self.dir, "init", "-q")
        tgit(self.dir, "remote", "add", "origin", self.remote.path)
        self.ledger = ""
        self.summary_dir = tempfile.mkdtemp(prefix="v2s4e_summary_")
        case.addCleanup(shutil.rmtree, self.summary_dir, True)
        self.runs = 0

    def put_ledger(self, text):
        self.ledger = text
        self.remote.plant("v2-ledger", {"observations.csv": text.encode("utf-8")}, parent="HEAD~")

    def sync_ledger(self, start, day, extra=""):
        want = D.ledger_text(D.table_days(D.next_day(start), day), extra)
        if want != self.ledger:
            self.put_ledger(want)

    def heads(self):
        """{ref name: sha} of the heads of the bare remote."""
        return {k[len("refs/heads/"):]: v for k, v in self.remote.refs().items() if k.startswith("refs/heads/")}

    def v2_heads(self, *names):
        heads = self.heads()
        return {n: heads.get(n) for n in names}

    def history(self, ref):
        return json.loads(self.remote.blob(ref, "history.json").decode("utf-8"))

    def run(self, net, args, now, env=None, clock_step=0, workdir=None, out=None, urlopen=None):
        """main(args + --workdir ...) with the fake network. `now`: an aware time. Returns a Result."""
        self.runs += 1
        summary = os.path.join(self.summary_dir, "summary_%d.md" % self.runs)
        environment = {"GITHUB_STEP_SUMMARY": summary}
        environment.update(env or {})
        lines = []
        clock = Clock(now, clock_step)
        argv = list(args) + ["--workdir", workdir or self.dir, "--code-version", CODE]
        code = R.main(argv, env=environment, out=out or lines.append, now_fn=clock, urlopen=urlopen or net)
        text = "\n".join(lines) if out is None else ""
        content = None
        if os.path.exists(summary):
            with open(summary, "rb") as f:
                content = f.read().decode("utf-8")
        return Result(code, text, content, clock)

    def cmd(self, net, command, mode, day=None, hhmm="07:40", extra=(), env=None, **kw):
        """A command of the morning of the day after `day`."""
        now = aware(day, *[int(x) for x in hhmm.split(":")]) if day else kw.pop("now")
        return self.run(net, [command, "--mode", mode] + list(extra), now, env, **kw)

    def init(self, net, mode, start=START, **kw):
        return self.cmd(net, "init", mode, D.next_day(start), "07:00", ["--start-after", start], **kw)

    def morning(self, net, mode, day, hhmm="07:40", env=None, sync=True, **kw):
        net.upto = day
        if sync:
            self.sync_ledger(kw.pop("start", START), day)
        if mode == "live":
            env = dict({R.SECRET_NAME: WEBHOOK}, **(env or {}))
        return self.cmd(net, "morning", mode, day, hhmm, env=env)


class Child(C.Child):
    """One independent Python process (s4e_worker.py): READY, wait for the GO file, run once, print one JSON line."""

    def __init__(self, spec, timeout=600):
        self.timeout = timeout
        self.proc = subprocess.Popen([sys.executable, "-B", "-I", WORKER, json.dumps(spec)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def days(first, last):
    return D.table_days(first, last)


def leaks(text):
    """The marks, and every `http` that is not the first letters of the fixed word http_<status> (a URL), that must never
    appear in a record."""
    found = [m for m in (MARK, TOKEN_MARK, BODY_MARK, "SECRETPATH") if m in text]
    return found + (["http"] if re.search(r"http(?!_[0-9]{3}\b)", text) else [])


def git_version():
    proc = subprocess.run(["git", "--version"], capture_output=True)
    return proc.stdout.decode("ascii").split()[2]


def run_bash(script, env):
    """The output of a bash script with exactly the given environment (None when bash is not available)."""
    bash = shutil.which("bash")
    if bash is None:
        return None
    proc = subprocess.run([bash, "-c", script], capture_output=True, env=env, timeout=60)
    if proc.returncode != 0:
        raise AssertionError((proc.returncode, proc.stderr[-500:]))
    return proc.stdout.decode("utf-8")


def read_source(relative):
    return D.read_source(relative)
