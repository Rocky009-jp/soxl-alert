"""run_morning: read the history, consume every confirmed session after its processing start up to the latest closed
one (one DAILY publication per day, through the injected store), evaluate the latest closed session and return the
preview text with a report.

Fixed order: the arguments (before the store is touched) -> the target session D (the last one with close_at <= now) ->
store.read -> the start (read_effective(history).processing_after) -> for each later session up to D, oldest first: an
unconfirmed one stops the run (STALE), otherwise prepare_history_day and, for a PREPARED day only, publish_day and
store.publish -> the evaluation of D (the loop's own result, or one prepare_history_day call when nothing lay after the
start) -> the report.

A CoreError after the store was read becomes a STOPPED report: the handler only turns the error into plain values and
the report is built outside it. Any other exception is a program error and passes through unchanged. Nothing here reads
a clock, an environment variable, a file or the network, retries a save, unlocks, migrates or adopts."""
import datetime

from v2_core.display import render_message
from v2_core.errors import CoreError
from v2_core.sessions import SessionList
from v2_history_ops import ALREADY_APPLIED, NO_COMMIT, PREPARED, prepare_history_day, read_effective
from v2_history_publish import PUBLISHED, PUBLISHED_THEN_EXTENDED, publish_day

from .values import (ARGS_INVALID, DONE, NO_CLOSED_SESSION, PUBLISH_CONFLICT, PUBLISH_NOT_PUBLISHED, PUBLISH_UNCERTAIN,
                     SESSION_UNCONFIRMED, STALE, STOPPED, TARGET_BEFORE_HEAD, ConsumedDay, RunError, RunReport)

_RESTART = object()
_IDENT = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_NOT_PUBLISHED, _CONFLICT = "NOT_PUBLISHED", "CONFLICT"


class _Run(object):
    """What the run has done so far (plain values; it is never part of the report)."""

    __slots__ = ("consumed", "target_status", "core_result", "history", "restarts", "sent")

    def __init__(self):
        self.consumed, self.target_status, self.core_result = [], None, None
        self.history, self.restarts, self.sent = None, 0, set()


def _check_args(store, now, sessions):
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise RunError(ARGS_INVALID, "now")
    if not isinstance(sessions, SessionList):
        raise RunError(ARGS_INVALID, "sessions")
    for name in ("read", "publish", "reconcile"):
        if not callable(getattr(store, name, None)):
            raise RunError(ARGS_INVALID, "store")


def _target(sessions, now):
    target = None
    for s in sessions.sessions:
        if s.close_at <= now:
            target = s
    if target is None:
        raise RunError(NO_CLOSED_SESSION, "sessions")
    return target.date


def _consumed(res):
    skipped = res.batch.body["records"][0]["skipped_sessions"]
    return ConsumedDay(res.d, res.status, res.core_result.gap, skipped)


def _catch_up(store, history, target_d, series, sessions, raw, run):
    """One pass from the effective start of `history`. Returns None (the target was evaluated), a stop tuple
    (outcome, code, field, rule, detail), or _RESTART (a save was uncertain and reconciled as published)."""
    run.history = history
    run.target_status, run.core_result = None, None
    start = read_effective(history).processing_after
    if target_d < start:
        return (STOPPED, TARGET_BEFORE_HEAD, "sessions", None, None)
    for s in sessions.sessions:
        if s.date <= start:
            continue
        if s.date > target_d:
            break
        if not s.confirmed:
            return (STALE, SESSION_UNCONFIRMED, "sessions", None, s.date)
        res = prepare_history_day(history, s.date, series, sessions, raw)
        if res.status == PREPARED:
            publication = publish_day(history, s.date, series, sessions, raw)
            if publication.publication_hash in run.sent:
                return (STOPPED, PUBLISH_UNCERTAIN, "store", None, s.date)      # never the same value twice
            run.sent.add(publication.publication_hash)
            day, uncertain, saved = _consumed(res), False, None
            try:
                saved = store.publish(publication)
            except CoreError as e:
                if e.code != "store_commit_uncertain":
                    raise
                uncertain = True
            if uncertain:
                if run.restarts >= 1:
                    return (STOPPED, PUBLISH_UNCERTAIN, "store", None, s.date)
                outcome = store.reconcile(publication).outcome
                if outcome in (PUBLISHED, PUBLISHED_THEN_EXTENDED):
                    run.consumed.append(day)
                    run.restarts += 1
                    return _RESTART
                if outcome == _NOT_PUBLISHED:
                    return (STOPPED, PUBLISH_NOT_PUBLISHED, "store", None, s.date)
                if outcome == _CONFLICT:
                    return (STOPPED, PUBLISH_CONFLICT, "store", None, s.date)
                raise AssertionError("unknown reconciliation outcome")
            history = run.history = saved.history
            run.consumed.append(day)
        elif res.status == NO_COMMIT or res.status == ALREADY_APPLIED:
            pass
        else:
            raise AssertionError("unknown day status")
        if s.date == target_d:
            run.target_status, run.core_result = res.status, res.core_result
    return None


def _evaluate_target(target_d, series, sessions, raw, run):
    """The target was not among the days after the start (it is the start itself): evaluate it once, on the history the
    run ended with. A CoreError here is a STOPPED too (the trial's T-2)."""
    res = prepare_history_day(run.history, target_d, series, sessions, raw)
    run.target_status, run.core_result = res.status, res.core_result


def _drive(store, target_d, series, sessions, raw, run):
    history = store.read()
    while True:
        verdict = _catch_up(store, history, target_d, series, sessions, raw, run)
        if verdict is not _RESTART:
            return verdict
        history = store.read()


def _ident(text):
    return text if isinstance(text, str) and 0 < len(text) <= 64 and set(text) <= _IDENT else None


def _date(text):
    ok = isinstance(text, str) and len(text) == 10 and text[4] == "-" and text[7] == "-" \
        and (text[:4] + text[5:7] + text[8:]).isdigit() and text.isascii()
    return text if ok else None


def _days(days):
    return "、".join(days) if days else "なし"


def _gap_lines(consumed):
    lines = []
    for day in consumed:
        if day.gap:
            lines.append("  %s を消費しました。直前までの観測が途切れていました（decisionの無いセッション: %s）。"
                         % (day.d, _days(day.skipped_sessions)))
    if lines:
        lines.insert(0, "【今回の追いつきで見つかった欠測】")
    return lines


def _notice(outcome, target_d, consumed, code, field, detail):
    label = "未確定のセッションがあります" if outcome == STALE else "実行を止めました"
    lines = ["【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=%s ／%s" % (target_d, label),
             "  今朝は結果を出していません。条件未達ではありません。前日の値や古い日付で補ってもいません。",
             "  理由コード: %s%s" % (code, "" if field is None else "（%s）" % field)]
    if detail is not None:
        lines.append("  対象のセッション: %s" % detail)
    lines.append("  この実行で保存した日: %s" % _days([d.d for d in consumed]))
    lines.append("  市場状態は、保存した日までです。それより後の日は処理していません。")
    return "\n".join(lines)


def _report(target_d, run, stop):
    digest = None if run.history is None else run.history.digest
    if stop is None:
        lines = _gap_lines(run.consumed)
        message = "\n".join(lines + [render_message(run.core_result)])
        return RunReport(DONE, target_d, run.consumed, run.target_status, message, history_digest=digest)
    outcome, code, field, rule, detail = stop
    return RunReport(outcome, target_d, run.consumed, run.target_status,
                     _notice(outcome, target_d, run.consumed, code, field, detail), code, field, rule, detail,
                     digest)


def run_morning(store, now, series, sessions, raw_observations):
    """One morning run; see the module text. Raises RunError for a wrong argument or when no session has closed."""
    _check_args(store, now, sessions)
    target_d = _target(sessions, now)
    run, stop = _Run(), None
    try:
        stop = _drive(store, target_d, series, sessions, raw_observations, run)
        if stop is None and run.core_result is None:
            _evaluate_target(target_d, series, sessions, raw_observations, run)
    except CoreError as e:
        stop = (STOPPED, _ident(e.code) or "unknown_error", _ident(getattr(e, "field", None)),
                _ident(getattr(e, "rule", None)), _date(getattr(e, "detail", None)))
    return _report(target_d, run, stop)
