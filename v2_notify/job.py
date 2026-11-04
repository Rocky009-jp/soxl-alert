"""The morning job and the manual resend: one send at most per key, through an injected sender, recorded in the outbox.

morning_job: arguments -> the target date D (the same rule as S4-A: the last session with close_at <= now) -> run_morning
-> one notice (MORNING for DONE, HALT for STALE / STOPPED, ERROR for a RunError, another CoreError or a program error) ->
the right to send (a HALT or ERROR notice is not made when a MORNING claim of the same D exists, in any state) ->
claim -> sender.send(text) once -> result. Only the answer "SENT" is SENT and "NOT_STARTED" NOT_SENT; every other answer
and every exception of the sender is UNKNOWN. Nothing is sent twice and nothing is retried. A program error (an
exception that is not a CoreError) is notified, recorded, and then raised again as the same object, whatever the
delivery was. An outbox that cannot create the claim sends nothing; one that cannot create the result leaves the claim
(UNKNOWN). Nothing here reads a clock, an environment variable or the network."""
import datetime

from v2_core.errors import CoreError
from v2_core.sessions import SessionList
from v2_daily_run import RunError, run_morning

from .compose import compose_error_notice, compose_notice
from .outbox import LocalOutbox
from .values import (ARGS_INVALID, CLAIM_FAILED, DAMAGED, ERROR, HALT, KINDS, MORNING, NONE, NOT_SENT, REFUSED_ALREADY_SENT,
                     REFUSED_DAMAGED, REFUSED_NO_ORIGINAL, RESULT_NOT_RECORDED, SENDER_NOT_STARTED, SENDER_SENT, SENT,
                     SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS, UNEXPECTED_ERROR, UNKNOWN, UNKNOWN_ERROR, JobReport,
                     Notice, NotifyError, ResendReport, code_text, date_text, request_id_text)

RESEND_LINE = "【再送】元の通知の送信を確認できなかったため、同じ内容を送ります"


def _check_now(now):
    if not isinstance(now, datetime.datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise NotifyError(ARGS_INVALID, "now")


def _check_parts(outbox, sender):
    if not isinstance(outbox, LocalOutbox):
        raise NotifyError(ARGS_INVALID, "outbox")
    if not callable(getattr(sender, "send", None)):
        raise NotifyError(ARGS_INVALID, "sender")


def _utc_date(now):
    return now.astimezone(datetime.timezone.utc).date().isoformat()


def _target_d(sessions, now):
    """The date of the last session with close_at <= now (the S4-A rule), or None when it cannot be found."""
    try:
        if not isinstance(sessions, SessionList):
            return None
        found = None
        for s in sessions.sessions:
            if s.close_at <= now:
                found = s.date
        return date_text(found)
    except Exception:                           # the key then falls back to the UTC date of the call
        return None


def _send(sender, text):
    """SENT / NOT_SENT / UNKNOWN. The only two answers that mean something are "SENT" and "NOT_STARTED"."""
    try:
        answer = sender.send(text)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return UNKNOWN
    if type(answer) is str and answer == SENDER_SENT:
        return SENT
    if type(answer) is str and answer == SENDER_NOT_STARTED:
        return NOT_SENT
    return UNKNOWN


def _take_and_send(outbox, sender, notice, now, resend_request_id=None, resend_of=None):
    """Claim, send once, record. Returns (delivery, send_status, existing_status)."""
    taken = outbox.status(notice.d, notice.kind, resend_request_id).status     # a result without a claim is DAMAGED
    if taken != NONE:
        return SKIPPED_CLAIMED, None, taken
    failed, claim_id = False, None
    try:
        claim_id = outbox.claim(notice, now, resend_request_id, resend_of)
    except NotifyError:
        failed = True
    if failed:
        return CLAIM_FAILED, None, None
    if claim_id is None:                        # the claim exists already: this call does not hold the right
        return SKIPPED_CLAIMED, None, outbox.status(notice.d, notice.kind, resend_request_id).status
    send_status, recorded = _send(sender, notice.text), False
    try:
        recorded = outbox.record(notice.d, notice.kind, claim_id, send_status, now, resend_request_id)
    except NotifyError:
        recorded = False
    return (send_status if recorded else RESULT_NOT_RECORDED), send_status, None


def morning_job(store, outbox, sender, now, series, sessions, raw_observations):
    """One morning: run, one notice, at most one send. Returns a JobReport; raises NotifyError for a wrong argument
    (before anything is touched) and, after the notice, the original exception of a program error."""
    _check_now(now)
    _check_parts(outbox, sender)
    target_d = _target_d(sessions, now)
    report, error, program_error = None, None, None
    try:
        report = run_morning(store, now, series, sessions, raw_observations)
    except CoreError as e:
        error = (code_text(getattr(e, "code", None)) or UNKNOWN_ERROR, None if isinstance(e, RunError) else type(e).__name__)
    except Exception as e:                      # a program error: notify without its text, then raise it again
        error, program_error = (UNEXPECTED_ERROR, type(e).__name__), e
    if report is not None:
        notice = compose_notice(report, sessions, now)
    else:
        notice = compose_error_notice(target_d or _utc_date(now), error[0], error[1], d_is_target=target_d is not None)
    # a HALT or ERROR notice is not made when a MORNING claim of the same D exists, in any state (DAMAGED included)
    judgment_known = notice.kind == HALT or (notice.kind == ERROR and target_d is not None)
    judgment = outbox.status(notice.d, MORNING).status if judgment_known else NONE
    if judgment != NONE:
        delivery, send_status, existing = SKIPPED_JUDGMENT_EXISTS, None, judgment
    else:
        delivery, send_status, existing = _take_and_send(outbox, sender, notice, now)
    result = JobReport(None if report is None else report.outcome, notice.kind, notice.d, delivery, send_status,
                       existing, notice.code, report)
    if program_error is not None:
        raise program_error
    return result


def _eligible(outbox, d, kind, resend_request_id):
    """(refusal, original entry, original claim, id already used). refusal is None when a resend may go on."""
    original, claim = outbox.load(d, kind)
    if original.status == NONE:
        return REFUSED_NO_ORIGINAL, original, None, False
    if original.status == DAMAGED:
        return REFUSED_DAMAGED, original, None, False
    if original.status == SENT:
        return REFUSED_ALREADY_SENT, original, None, False
    ids = outbox.resend_ids(d, kind)
    for other in ids:
        state = outbox.status(d, kind, other).status
        if state == SENT:
            return REFUSED_ALREADY_SENT, original, None, False
        if state == DAMAGED:
            return REFUSED_DAMAGED, original, None, False
    return None, original, claim, resend_request_id in ids


def resend(outbox, sender, d, kind, resend_request_id, now):
    """Send the text of an earlier notice again, because the user asked (resend_request_id is theirs). Refused when the
    original or any earlier resend of the key is SENT or DAMAGED, or when the original has no claim. The same id is never
    sent twice. Returns a ResendReport; raises NotifyError for a wrong argument before any file is touched."""
    _check_now(now)
    _check_parts(outbox, sender)
    if date_text(d) is None:
        raise NotifyError(ARGS_INVALID, "d")
    if kind not in KINDS:
        raise NotifyError(ARGS_INVALID, "kind")
    if request_id_text(resend_request_id) is None:
        raise NotifyError(ARGS_INVALID, "resend_request_id")
    listing_failed, found = False, None
    try:
        found = _eligible(outbox, d, kind, resend_request_id)
    except NotifyError:
        listing_failed = True
    if listing_failed:
        return ResendReport(kind, d, resend_request_id, CLAIM_FAILED, None, None)
    refusal, original, claim, used = found
    if refusal is not None:
        return ResendReport(kind, d, resend_request_id, refusal, None, original.status)
    if used:
        return ResendReport(kind, d, resend_request_id, SKIPPED_CLAIMED, None, original.status)
    notice = Notice(kind, d, RESEND_LINE + "\n" + claim["text"], claim["run_outcome"], claim["code"])
    delivery, send_status, _existing = _take_and_send(outbox, sender, notice, now, resend_request_id,
                                                      claim["claim_id"])
    return ResendReport(kind, d, resend_request_id, delivery, send_status, original.status)
