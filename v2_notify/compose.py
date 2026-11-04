"""The text of a notification. Pure: no clock, file, network or environment variable.

compose_notice(report, sessions, now) makes the MORNING notice (a judgment, the run was DONE) or the HALT notice (no
judgment, the run was STALE or STOPPED) from an S4-A RunReport. compose_error_notice makes the ERROR notice (no
report). Parts, top to bottom: the heading, the lines about sessions without a record (any day with skipped sessions;
in a MORNING notice only the days whose gap is false, because the S4-A text already writes the gap=true days), the notes
(only when their condition holds), then the S4-A text, unchanged. An ERROR notice names only a fixed code and the
name of the exception type: never the text of an exception, a path, a URL or a secret."""
import datetime

from v2_core.sessions import SessionList
from v2_daily_run import DONE, RunReport

from .values import (ARGS_INVALID, ERROR, HALT, MORNING, PUBLICATION_STALE, PUBLISH_CONFLICT, PUBLISH_UNCERTAIN,
                     STORE_BUSY, TARGET_NOT_AFTER_BOUNDARY, Notice, NotifyError, code_text, date_text, type_name_text)

NO_COMMIT_STATUS = "NO_COMMIT"
_UNSURE_CODES = (PUBLISH_UNCERTAIN, PUBLISH_CONFLICT)
_CONCURRENT_CODES = (STORE_BUSY, PUBLICATION_STALE)

NOTE_AFTER_OPEN = "※この実行は対象Dの次の寄付き（%s）の後です。下の分岐表の寄付きは過ぎています。"
NOTE_UNSURE = "※最後の日の保存は確認できていません。"
NOTE_BOUNDARY = "※対象Dは記録の開始境界の日です。次のセッションから処理します。異常ではありません。"
NOTE_CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"
MISSING_HEAD = "【F&Gの記録の欠け】"


def _aware(now):
    return isinstance(now, datetime.datetime) and now.tzinfo is not None and now.utcoffset() is not None


def _missing_lines(report, only_without_gap):
    lines = []
    for day in report.consumed:
        if not day.skipped_sessions or (only_without_gap and day.gap):
            continue
        lines.append("  %s の前に、F&Gの記録が無いセッションがありました: %s" % (day.d, "、".join(day.skipped_sessions)))
    return [MISSING_HEAD] + lines if lines else []


def compose_notice(report, sessions, now):
    """The notice for an S4-A report. Raises NotifyError (notify_args_invalid) for a wrong argument."""
    if not isinstance(report, RunReport):
        raise NotifyError(ARGS_INVALID, "report")
    if not isinstance(sessions, SessionList):
        raise NotifyError(ARGS_INVALID, "sessions")
    if not _aware(now):
        raise NotifyError(ARGS_INVALID, "now")
    if report.outcome == DONE:
        lines = ["【SOXL日次】対象D=%s" % report.target_d]
        lines += _missing_lines(report, only_without_gap=True)
        following = sessions.next(report.target_d)
        if report.target_status == NO_COMMIT_STATUS and following is not None and now >= following.open_at:
            lines.append(NOTE_AFTER_OPEN % following.open_at.isoformat())
        lines.append(report.message)
        return Notice(MORNING, report.target_d, "\n".join(lines), report.outcome, None)
    lines = ["【SOXL日次】対象D=%s ／判定なし" % report.target_d]
    lines += _missing_lines(report, only_without_gap=False)
    if report.code in _UNSURE_CODES:
        lines.append(NOTE_UNSURE)
    if report.code == TARGET_NOT_AFTER_BOUNDARY:
        lines.append(NOTE_BOUNDARY)
    if report.code in _CONCURRENT_CODES:
        lines.append(NOTE_CONCURRENT)
    lines.append(report.message)
    return Notice(HALT, report.target_d, "\n".join(lines), report.outcome, report.code)


def compose_error_notice(d, code, type_name=None, d_is_target=True):
    """The ERROR notice. d: the target date (d_is_target True) or, when no target date could be found, the UTC date
    of the call. code: a fixed code; type_name: the name of the exception type or None. Nothing else is written."""
    if date_text(d) is None:
        raise NotifyError(ARGS_INVALID, "d")
    code = code_text(code)
    if code is None:
        raise NotifyError(ARGS_INVALID, "code")
    label = "対象D" if d_is_target else "日付（UTC）"
    reason = code if type_name is None else "%s（%s）" % (code, type_name_text(type_name))
    lines = ["【SOXL日次】判定なし（実行の誤り） %s=%s" % (label, d),
             "  今朝は結果を出していません。条件未達ではありません。",
             "  理由コード: %s" % reason]
    return Notice(ERROR, d, "\n".join(lines), None, code)
