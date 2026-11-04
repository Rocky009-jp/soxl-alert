"""V2 S4-B, the notification: the text of a morning notice, a local outbox that holds the send right (one send at most
per key, claim and result created and never replaced), the morning job and the manual resend. The sender is injected
and is only a test double here: no real destination, HTTP, URL, secret, environment variable, entry script, workflow,
clock (the time is passed in), automatic resend, retry, cleanup or git outbox exists here. Draft, not adopted for
production."""
from .compose import compose_error_notice, compose_notice
from .job import morning_job, resend
from .outbox import LocalOutbox
from .values import (CLAIM_FAILED, DAMAGED, ERROR, HALT, KINDS, MORNING, NONE, NOT_SENT, REFUSED_ALREADY_SENT, REFUSED_DAMAGED,
                     REFUSED_NO_ORIGINAL, RESULT_NOT_RECORDED, SENT, SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS, UNKNOWN,
                     JobReport, Notice, NotifyError, OutboxEntry, ResendReport)


def outbox_status(outbox, d, kind=None):
    """Read-only: the OutboxEntry of every key of the date d (the morning, halt and error keys, or only `kind`) and of
    every resend of each. A key that has no file is listed with the status NONE. Nothing is created or changed."""
    if not isinstance(outbox, LocalOutbox):
        raise NotifyError("notify_args_invalid", "outbox")
    if kind is not None and kind not in KINDS:
        raise NotifyError("notify_args_invalid", "kind")
    entries = []
    for k in KINDS if kind is None else (kind,):
        entries.append(outbox.status(d, k))
        entries.extend(outbox.status(d, k, rid) for rid in outbox.resend_ids(d, k))
    return tuple(entries)


__all__ = ["morning_job", "resend", "outbox_status", "compose_notice", "compose_error_notice", "LocalOutbox", "Notice",
           "JobReport", "ResendReport", "OutboxEntry", "NotifyError", "MORNING", "HALT", "ERROR", "KINDS", "NONE",
           "SENT", "NOT_SENT", "UNKNOWN", "DAMAGED", "SKIPPED_CLAIMED", "SKIPPED_JUDGMENT_EXISTS", "CLAIM_FAILED",
           "RESULT_NOT_RECORDED", "REFUSED_NO_ORIGINAL", "REFUSED_DAMAGED", "REFUSED_ALREADY_SENT"]
