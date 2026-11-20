"""Values of the S4-A morning run: the outcome words, the run error and the immutable run report.

No file, clock, network, environment variable or store is touched here. A RunReport is made only by run_morning; it
holds fixed identifiers, dates taken from the session list and the preview text -- never a path, an exception text, a
URL or a secret -- and its repr never shows the text."""
from v2_core.errors import CoreError

DONE, STALE, STOPPED = "DONE", "STALE", "STOPPED"
OUTCOMES = (DONE, STALE, STOPPED)
EXIT_OK, EXIT_NOT_OK = 0, 1

ARGS_INVALID = "run_args_invalid"
NO_CLOSED_SESSION = "run_no_closed_session"
TARGET_BEFORE_HEAD = "run_target_before_head"
SESSION_UNCONFIRMED = "run_session_unconfirmed"
PUBLISH_UNCERTAIN = "run_publish_uncertain"
PUBLISH_NOT_PUBLISHED = "run_publish_not_published"
PUBLISH_CONFLICT = "run_publish_conflict"


HEADLINE_MAX = 80


def _headline_ok(text):
    """A headline is one non-empty line of printable characters (no line break of any kind), at most HEADLINE_MAX long."""
    return (type(text) is str and 0 < len(text) <= HEADLINE_MAX and text.isprintable() and text == text.strip()
            and len(text.splitlines()) == 1)


class RunError(CoreError):
    """The call itself is wrong (an argument, or no session has closed yet). Raised before the store is touched."""


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


class ConsumedDay(_Immutable):
    """A day this run published: its date, the day status of the preparation (always PREPARED), and the core
    transition's gap and skipped_sessions (the sessions without a decision between the previous day and this one)."""

    _NAMES = ("d", "status", "gap", "skipped_sessions")
    __slots__ = _NAMES

    def __init__(self, d, status, gap, skipped_sessions):
        for name, value in (("d", d), ("status", status), ("gap", bool(gap)),
                            ("skipped_sessions", tuple(skipped_sessions))):
            object.__setattr__(self, name, value)

    def __repr__(self):
        return "ConsumedDay(d=%s, gap=%s, skipped=%d)" % (self.d, self.gap, len(self.skipped_sessions))


class RunReport(_Immutable):
    """What one morning run did. outcome DONE (exit 0), STALE or STOPPED (exit 1).

    consumed: the days this run saved, oldest first. target_status: the day status of the target session when it was
    evaluated (None when it was not). message: the preview text (DONE: the core text; otherwise a plain notice that no
    result was produced). code / field / rule / detail: why the run stopped (None for DONE). history_digest: the digest
    of the last history that was read or saved. headline: the ratio part of the notice's first line (a DONE report of a
    day with a signal; otherwise None). It is one line and is made by run_morning from the same judgment as the text."""

    _NAMES = ("outcome", "exit_code", "target_d", "consumed", "target_status", "message", "code", "field", "rule",
              "detail", "history_digest", "headline")
    __slots__ = _NAMES

    def __init__(self, outcome, target_d, consumed, target_status, message, code=None, field=None, rule=None,
                 detail=None, history_digest=None, headline=None):
        if outcome not in OUTCOMES:
            raise ValueError("outcome")
        if headline is not None and (outcome != DONE or not _headline_ok(headline)):
            raise ValueError("headline")
        values = {"outcome": outcome, "exit_code": EXIT_OK if outcome == DONE else EXIT_NOT_OK,
                  "target_d": target_d, "consumed": tuple(consumed), "target_status": target_status,
                  "message": message, "code": code, "field": field, "rule": rule, "detail": detail,
                  "history_digest": history_digest, "headline": headline}
        for name in self._NAMES:
            object.__setattr__(self, name, values[name])

    def __repr__(self):
        return "RunReport(outcome=%s, exit_code=%d, target_d=%s, consumed=%d, target_status=%s, code=%s)" % (
            self.outcome, self.exit_code, self.target_d, len(self.consumed), self.target_status, self.code)
