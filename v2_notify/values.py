"""Values of the S4-B notification stage: the words (kinds, outbox statuses, delivery results), the error, the checks of
the plain texts that name files, and the immutable Notice / JobReport / ResendReport / OutboxEntry.

No file, clock, network, environment variable or store is touched here. A value never holds a path, an exception
text, a URL or a secret, and the repr of a value never shows a notice text."""
import hashlib

from v2_core.errors import CoreError

# --- the kinds of notice (the key of the outbox is "<date>-<kind>") -----------------------------------------------
MORNING, HALT, ERROR = "morning", "halt", "error"
KINDS = (MORNING, HALT, ERROR)

# --- the state of one key in the outbox ---------------------------------------------------------------------------
NONE, SENT, NOT_SENT, UNKNOWN, DAMAGED = "NONE", "SENT", "NOT_SENT", "UNKNOWN", "DAMAGED"
RESULT_STATUSES = (SENT, NOT_SENT, UNKNOWN)

# --- what a morning job / a resend did ------------------------------------------------------------------------------
SKIPPED_CLAIMED = "SKIPPED_CLAIMED"
SKIPPED_JUDGMENT_EXISTS = "SKIPPED_JUDGMENT_EXISTS"
CLAIM_FAILED = "CLAIM_FAILED"
RESULT_NOT_RECORDED = "RESULT_NOT_RECORDED"
REFUSED_NO_ORIGINAL = "REFUSED_NO_ORIGINAL"
REFUSED_DAMAGED = "REFUSED_DAMAGED"
REFUSED_ALREADY_SENT = "REFUSED_ALREADY_SENT"
DELIVERIES = (SENT, NOT_SENT, UNKNOWN, SKIPPED_CLAIMED, SKIPPED_JUDGMENT_EXISTS, CLAIM_FAILED, RESULT_NOT_RECORDED)
RESEND_DELIVERIES = (SENT, NOT_SENT, UNKNOWN, SKIPPED_CLAIMED, CLAIM_FAILED, RESULT_NOT_RECORDED, REFUSED_NO_ORIGINAL,
                     REFUSED_DAMAGED, REFUSED_ALREADY_SENT)

# --- the answers of the sender ----------------------------------------------------------------------------------------
SENDER_SENT, SENDER_NOT_STARTED = "SENT", "NOT_STARTED"

EXIT_OK, EXIT_NOT_OK = 0, 1

# --- error codes ----------------------------------------------------------------------------------------------------
ARGS_INVALID = "notify_args_invalid"
OUTBOX_ROOT_INVALID = "outbox_root_invalid"
OUTBOX_IO_ERROR = "outbox_io_error"
OUTBOX_DURABILITY_UNSUPPORTED = "outbox_durability_unsupported"

# --- codes of the earlier stages that the texts react to (kept equal to theirs by a test) ----------------------------
PUBLISH_UNCERTAIN = "run_publish_uncertain"
PUBLISH_CONFLICT = "run_publish_conflict"
TARGET_NOT_AFTER_BOUNDARY = "target_not_after_boundary"
STORE_BUSY = "store_busy"
PUBLICATION_STALE = "publication_stale"
UNEXPECTED_ERROR = "unexpected_error"
UNKNOWN_ERROR = "unknown_error"

CLAIM_SCHEMA = "v2_notify.claim.1"
_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
_CODE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_HEX = frozenset("0123456789abcdef")


class NotifyError(CoreError):
    """The call itself is wrong (an argument, or the outbox directory), or the outbox could not create a file."""


def date_text(text):
    """text when it is exactly YYYY-MM-DD in ASCII digits (a plausible date), otherwise None."""
    ok = isinstance(text, str) and len(text) == 10 and text.isascii() and text[4] == "-" and text[7] == "-" \
        and (text[:4] + text[5:7] + text[8:]).isdigit()
    if not ok:
        return None
    if not (1 <= int(text[5:7]) <= 12 and 1 <= int(text[8:]) <= 31):
        return None
    return text


def request_id_text(text):
    """A resend_request_id: 1 to 64 of A-Z a-z 0-9 - _ ; otherwise None."""
    ok = isinstance(text, str) and 0 < len(text) <= 64 and set(text) <= _ID_CHARS
    return text if ok else None


def code_text(text):
    """A fixed code of an earlier stage (lower case, digits, underscore, at most 64) or None."""
    ok = isinstance(text, str) and 0 < len(text) <= 64 and set(text) <= _CODE_CHARS
    return text if ok else None


def type_name_text(text):
    """The name of an exception type when it is a plain identifier of at most 64 characters, else 'Exception'."""
    ok = isinstance(text, str) and 0 < len(text) <= 64 and set(text) <= _NAME_CHARS
    return text if ok else "Exception"


def hex32(text):
    return isinstance(text, str) and len(text) == 32 and set(text) <= _HEX


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Immutable(object):
    _NAMES = ()
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError("%s is immutable" % type(self).__name__)

    def __delattr__(self, name):
        raise AttributeError("%s is immutable" % type(self).__name__)

    def _fields(self):
        return tuple(getattr(self, n) for n in self._NAMES)

    def __eq__(self, other):
        return type(other) is type(self) and self._fields() == other._fields()

    def __hash__(self):
        return hash(self._fields())

    def _set(self, values):
        for name in self._NAMES:
            object.__setattr__(self, name, values[name])


class Notice(_Immutable):
    """One notification: kind, the date of its key, the text, the sha256 of the text, and (for the record) the outcome
    of the run and the code that the text names. The repr never shows the text."""

    _NAMES = ("kind", "d", "text", "text_sha256", "run_outcome", "code")
    __slots__ = _NAMES

    def __init__(self, kind, d, text, run_outcome=None, code=None):
        if kind not in KINDS:
            raise ValueError("kind")
        if date_text(d) is None:
            raise ValueError("d")
        if not isinstance(text, str) or not text:
            raise ValueError("text")
        self._set({"kind": kind, "d": d, "text": text, "text_sha256": sha256_text(text),
                   "run_outcome": run_outcome, "code": code})

    @property
    def key(self):
        return "%s-%s" % (self.d, self.kind)

    def __repr__(self):
        return "Notice(kind=%s, d=%s, chars=%d, code=%s)" % (self.kind, self.d, len(self.text), self.code)


class JobReport(_Immutable):
    """What one morning job did. run_outcome: DONE / STALE / STOPPED, or None when the run raised. kind, d: the key.
    delivery: one of DELIVERIES. send_status: the sender's result (SENT / NOT_SENT / UNKNOWN) or None when the sender
    was not called. existing_status: the outbox state of the key when it was already taken (for SKIPPED_JUDGMENT_EXISTS: the
    state of the judgment key of the same D). code: the code the text
    names. report: the S4-A RunReport (None when the run raised). exit_code: 0 only for a judgment that was sent."""

    _NAMES = ("run_outcome", "kind", "d", "delivery", "send_status", "existing_status", "code", "exit_code", "report")
    __slots__ = _NAMES

    def __init__(self, run_outcome, kind, d, delivery, send_status, existing_status, code, report):
        if delivery not in DELIVERIES:
            raise ValueError("delivery")
        ok = run_outcome == "DONE" and (delivery == SENT or (delivery == SKIPPED_CLAIMED and existing_status == SENT))
        self._set({"run_outcome": run_outcome, "kind": kind, "d": d, "delivery": delivery, "send_status": send_status,
                   "existing_status": existing_status, "code": code, "exit_code": EXIT_OK if ok else EXIT_NOT_OK,
                   "report": report})

    @property
    def key(self):
        return "%s-%s" % (self.d, self.kind)

    def __repr__(self):
        return "JobReport(run_outcome=%s, key=%s, delivery=%s, exit_code=%d)" % (
            self.run_outcome, self.key, self.delivery, self.exit_code)


class ResendReport(_Immutable):
    """What one manual resend did. delivery: one of RESEND_DELIVERIES. original_status: the state of the original key
    that was read first. exit_code: 0 only when the resend was sent."""

    _NAMES = ("kind", "d", "resend_request_id", "delivery", "send_status", "original_status", "exit_code")
    __slots__ = _NAMES

    def __init__(self, kind, d, resend_request_id, delivery, send_status, original_status):
        if delivery not in RESEND_DELIVERIES:
            raise ValueError("delivery")
        self._set({"kind": kind, "d": d, "resend_request_id": resend_request_id, "delivery": delivery,
                   "send_status": send_status, "original_status": original_status,
                   "exit_code": EXIT_OK if delivery == SENT else EXIT_NOT_OK})

    def __repr__(self):
        return "ResendReport(key=%s-%s, id=%s, delivery=%s, exit_code=%d)" % (
            self.d, self.kind, self.resend_request_id, self.delivery, self.exit_code)


class OutboxEntry(_Immutable):
    """One line of outbox_status: the original (resend_request_id None) or one resend of a key."""

    _NAMES = ("kind", "d", "resend_request_id", "status", "claim_id", "claimed_at", "recorded_at", "text_sha256")
    __slots__ = _NAMES

    def __init__(self, kind, d, resend_request_id, status, claim_id=None, claimed_at=None, recorded_at=None,
                 text_sha256=None):
        self._set({"kind": kind, "d": d, "resend_request_id": resend_request_id, "status": status,
                   "claim_id": claim_id, "claimed_at": claimed_at, "recorded_at": recorded_at,
                   "text_sha256": text_sha256})

    def __repr__(self):
        return "OutboxEntry(%s-%s, resend=%s, status=%s)" % (self.d, self.kind, self.resend_request_id, self.status)
