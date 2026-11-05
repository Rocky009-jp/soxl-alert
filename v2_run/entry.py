"""python -m v2_run <command> --mode dry|live --workdir <checkout of the private repository> [...]

Commands: morning (the scheduled run), status (the outbox of one date), resend (a manual resend), init (the genesis of the
history and the outbox on the refs of the mode, each only when it is missing), check-source (the facts of the chart responses,
nothing written). The entry is the only place that reads the clock, the environment (the webhook secret of the live run and the
summary file) and chooses the HTTP functions. Everything of a run is decided once in Setup and the same objects are passed on
(R2-P01). The record of a run (standard output and the Actions summary) holds codes, dates, digests, counts and seconds: never a
path, a URL, a secret, the text of an exception, the output of git or a response body."""
import argparse
import datetime as dt
import os
import re
import shutil
import sys
import tempfile
import time

from v2_core.errors import CoreError
from v2_git_store import Git, GitHistoryStore, GitOutbox
from v2_history_publish import publish_genesis
from v2_inputs import MarketPin, PREHISTORY_START, SYMBOLS, build_sessions, guarded_store, load_inputs
from v2_notify import (ERROR, HALT, KINDS, MORNING, NONE, SENT, SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS, morning_job,
                       outbox_status, resend)

from . import check
from .web import DiscordSender, DrySender, make_fetch, real_urlopen

MODES = {
    "dry": {"state": "v2-dry-state", "outbox": "v2-dry-outbox", "market": "v2-dry-market", "ledger": "v2-ledger"},
    "live": {"state": "v2-state", "outbox": "v2-outbox", "market": "v2-market", "ledger": "v2-ledger"},
}
COMMANDS = ("morning", "status", "resend", "init", "check-source")
SECRET_NAME = "V2_DISCORD_WEBHOOK_URL"
SUMMARY_NAME = "GITHUB_STEP_SUMMARY"
OK_DELIVERIES = (SENT, SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS)
REFUSED_JUDGMENT_EXISTS = "REFUSED_JUDGMENT_EXISTS"
_SHA = re.compile(r"[0-9a-f]{40}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def utc_now():
    """The one clock of the program (UTC, with its time zone)."""
    return dt.datetime.now(dt.timezone.utc)


class Setup(object):
    """Everything of one run, decided once and in this order (R2-P01): now (the clock is read once; the function itself goes
    only to the stores and load_inputs for the time of a commit), the Git of the work directory, the ref names of the mode, the
    history store, the outbox (one GitOutbox), the sender and the fetch function (with its list of failure words)."""

    def __init__(self, mode, workdir, env, urlopen, now_fn, scratch):
        self.mode, self.clock = mode, now_fn
        self.now = now_fn()
        self.git = Git(workdir)
        self.refs = MODES[mode]
        self.store = GitHistoryStore(self.git, self.refs["state"], now_fn)
        self.outbox = GitOutbox(self.git, self.refs["outbox"], scratch, now_fn)
        self.sender = DrySender() if mode == "dry" else DiscordSender(env.get(SECRET_NAME), urlopen)
        self.fetch_failures = []
        self.fetch = make_fetch(urlopen, self.fetch_failures)


class Record(object):
    """The record of a run: `- key: value` lines and, for the text of a dry run, one fenced block."""

    def __init__(self):
        self.lines = []

    def add(self, key, value):
        self.lines.append("- %s: %s" % (key, value))

    def block(self, title, text):
        self.lines += ["", "#### " + title, "", "```", text.replace("```", "'''"), "```"]


def why(error):
    """The only thing that is ever shown of an exception: its type name and, when it is a text, its `code` attribute."""
    code = getattr(error, "code", None)
    return type(error).__name__ + ("（%s）" % code if type(code) is str else "")


def _git_version(git):
    proc = git.run(["--version"])
    found = re.search(r"[0-9]+\.[0-9]+(\.[0-9]+)?", proc.stdout.decode("ascii", "replace")) if proc is not None else None
    return found.group(0) if found else "unknown"


def _outbox_files(s):
    head = s.git.fetch(s.refs["outbox"])
    return 0 if head is None else len(s.git.tree(head))


def _fetch_failures(s, rec):
    for symbol, word in s.fetch_failures:
        rec.add("fetch_failure", "%s %s" % (symbol, word))


def cmd_morning(s, rec):
    t0 = time.monotonic()
    inputs, raised = None, None
    try:
        inputs = load_inputs(s.git, s.fetch, s.now, {"market": s.refs["market"], "ledger": s.refs["ledger"]}, s.clock)
    except CoreError as error:                  # input_args_invalid / input_calendar_ended: still one notice (ERROR)
        raised = error
    t1 = time.monotonic()
    if inputs is None:
        job = morning_job(s.store, s.outbox, s.sender, s.now, None, None, [])
    else:
        job = morning_job(guarded_store(s.store, inputs.failure), s.outbox, s.sender, s.now, inputs.series,
                          inputs.sessions, inputs.raw_observations)
    t2 = time.monotonic()
    if raised is not None:
        rec.add("inputs_raised", "%s（%s）" % (getattr(raised, "code", None), getattr(raised, "field", None)))
    elif inputs.failure is not None:
        failure = inputs.failure
        rec.add("inputs_failure", "%s（%s）%s" % (failure.code, failure.field, "" if not failure.detail else " " + failure.detail))
    _fetch_failures(s, rec)
    if inputs is not None:
        for key in sorted(inputs.provenance):
            rec.add("provenance." + key, inputs.provenance[key])
    rec.add("run_outcome", job.run_outcome)
    rec.add("key", "%s-%s" % (job.d, job.kind))
    rec.add("delivery", job.delivery)
    rec.add("send_status", job.send_status)
    rec.add("existing_status", job.existing_status)
    rec.add("code", job.code)
    if job.report is not None:
        rec.add("consumed", " ".join(d.d for d in job.report.consumed) or "-")
        rec.add("history_digest", (job.report.history_digest or "-")[:12])
    files = _outbox_files(s)
    t3 = time.monotonic()
    s.outbox.load(job.d, job.kind)              # one read of the outbox (the S4-C handoff 3)
    t4 = time.monotonic()
    rec.add("seconds.load_inputs", "%.2f" % (t1 - t0))
    rec.add("seconds.morning_job", "%.2f" % (t2 - t1))
    rec.add("seconds.outbox_load", "%.2f" % (t4 - t3))
    rec.add("outbox_files", files)
    if s.mode == "dry" and s.sender.texts:
        rec.block("text (dry: not sent)", s.sender.texts[-1])
    return 0 if (raised is None and job.delivery in OK_DELIVERIES) else 1


def cmd_status(s, rec, d):
    for entry in outbox_status(s.outbox, d):
        rec.add("%s-%s%s" % (entry.d, entry.kind, "" if entry.resend_request_id is None else "/" + entry.resend_request_id),
                "%s %s" % (entry.status, entry.recorded_at or entry.claimed_at or ""))
    return 0


def cmd_resend(s, rec, d, kind, request_id):
    if kind in (HALT, ERROR) and s.outbox.status(d, MORNING).status != NONE:      # S4-B review P-02
        rec.add("delivery", REFUSED_JUDGMENT_EXISTS)
        return 1
    report = resend(s.outbox, s.sender, d, kind, request_id, s.now)
    rec.add("delivery", report.delivery)
    rec.add("send_status", report.send_status)
    rec.add("original_status", report.original_status)
    return 0 if report.delivery == SENT else 1


def _create(rec, name, missing, make):
    """One of the two creations of init: made only when the ref is missing, recorded as INITIALIZED / EXISTS / failed."""
    if not missing:
        rec.add(name, "EXISTS")
        return True
    failed = None
    try:
        make()
    except Exception as error:                  # the type name only
        failed = why(error)
    rec.add(name, "INITIALIZED" if failed is None else "failed (%s)" % failed)
    return failed is None


def cmd_init(s, rec, start_after):
    sessions = build_sessions(s.now, start_after)       # the boundary is confirmed by the table up to that day
    closed = [x.date for x in sessions.sessions if x.close_at <= s.now]
    if start_after not in closed:
        rec.add("refused", "start_after_not_a_closed_session")
        return 1
    state_missing = s.git.fetch(s.refs["state"]) is None
    outbox_missing = s.git.fetch(s.refs["outbox"]) is None
    first = _create(rec, "state", state_missing, lambda: s.store.initialize(publish_genesis(start_after, sessions)))
    second = _create(rec, "outbox", outbox_missing, s.outbox.initialize)
    return 0 if (first and second) else 1


def cmd_check_source(s, rec):
    sessions = build_sessions(s.now, None)
    target = check.target_day(sessions, s.now)
    rec.add("target_d", target)
    table = check.table_dates(target) if target else []
    known = check.research_dates()
    pinned, through = None, None
    unreadable = None
    try:
        _head, through, pinned, _digest = MarketPin(s.git, s.refs["market"], s.clock).read()
    except CoreError as error:                  # a pin that is not a snapshot: the comparison is left out
        unreadable = why(error)
    rec.add("pin_through", through if unreadable is None else "unreadable (%s)" % unreadable)
    end, worst = check.end_date(s.now), 0
    for symbol in SYMBOLS:
        data, failed = None, None
        try:
            data = s.fetch(symbol, PREHISTORY_START, end)
        except Exception as error:
            failed = type(error).__name__
        if failed is not None:
            rec.add(symbol + ".fetch", "failed (%s)" % failed)
            worst = 1
            continue
        facts = check.inspect(data, symbol, target, table, known.get(symbol, set()),
                              (pinned or {}).get(symbol), through)
        for key, value in facts.items():
            rec.add("%s.%s" % (symbol, key), value)
    _fetch_failures(s, rec)
    return worst


class _ArgsError(Exception):
    """A wrong argument. It carries no text: the value of an argument is never shown."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _ArgsError()


def _real_date(text):
    ok = type(text) is str and _DATE.fullmatch(text) is not None
    if ok:
        try:
            ok = dt.date.fromisoformat(text).isoformat() == text
        except ValueError:
            ok = False
    return ok


def _parse(argv):
    """The arguments, or the name of the first wrong one (a fixed word), as (args, None) / (None, name)."""
    parser = _Parser(prog="v2_run", add_help=False, allow_abbrev=False)
    parser.add_argument("command")
    for name in ("--mode", "--workdir", "--code-version", "--date", "--kind", "--request-id", "--start-after"):
        parser.add_argument(name, default=None)
    parsed, bad = None, None
    try:
        parsed = parser.parse_args(list(argv))
    except (_ArgsError, SystemExit):
        bad = "arguments"
    if bad is not None:
        return None, bad
    if parsed.command not in COMMANDS:
        return None, "command"
    if parsed.mode not in MODES:
        return None, "mode"
    if not parsed.workdir:
        return None, "workdir"
    if parsed.command in ("status", "resend") and not _real_date(parsed.date):
        return None, "date"
    if parsed.command == "resend" and parsed.kind not in KINDS:
        return None, "kind"
    if parsed.command == "resend" and not parsed.request_id:
        return None, "request_id"
    if parsed.command == "init" and not _real_date(parsed.start_after):
        return None, "start_after"
    return parsed, None


def _finish(rec, code, env, out):
    rec.add("exit_code", code)
    text = "\n".join(["### v2_run"] + rec.lines)
    out(text)
    path = env.get(SUMMARY_NAME)
    if path:
        failed = False
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            failed = True
        if failed:
            out("- summary_file: not_written")
    return code


def main(argv, env=None, out=print, now_fn=utc_now, urlopen=real_urlopen):
    """Runs one command and returns its exit code (an int). A wrong argument returns 2 before anything is read or opened."""
    env = os.environ if env is None else env
    rec = Record()
    args, bad = _parse(argv)
    if args is None:
        rec.add("refused", "arguments_invalid (%s)" % bad)
        return _finish(rec, 2, env, out)
    code = 1
    scratch = tempfile.mkdtemp(prefix="v2run_")
    rec.add("command", args.command)
    rec.add("mode", args.mode)
    try:
        s = Setup(args.mode, os.path.abspath(args.workdir), env, urlopen, now_fn, scratch)
        rec.add("now_utc", s.now.isoformat(timespec="seconds"))
        rec.add("code_version", args.code_version if _SHA.fullmatch(args.code_version or "") else "unknown")
        rec.add("python", "%d.%d.%d" % sys.version_info[:3])
        rec.add("git", _git_version(s.git))
        if args.command == "morning":
            code = cmd_morning(s, rec)
        elif args.command == "status":
            code = cmd_status(s, rec, args.date)
        elif args.command == "resend":
            code = cmd_resend(s, rec, args.date, args.kind, args.request_id)
        elif args.command == "init":
            code = cmd_init(s, rec, args.start_after)
        else:
            code = cmd_check_source(s, rec)
    except Exception as error:                  # the type name only: the text of an exception may hold a path or a URL
        rec.add("failed", why(error))
        code = 1
    finally:
        shutil.rmtree(scratch, True)
    return _finish(rec, code, env, out)
