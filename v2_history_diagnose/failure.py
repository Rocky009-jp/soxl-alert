"""The failure record: {stage, code, field, rule}, fixed identifiers only. No exception text, raw value or chain."""
from v2_core.errors import CoreError
from v2_persistence.errors import PersistenceError

STAGE_UTF8 = "utf8"
STAGE_JSON = "json"
STAGE_SCHEMA = "schema"
STAGE_VALIDATE = "validate"

# The exceptions the unchecked parts of a checker may raise (the same set validate_history turns into `malformed`).
CAUGHT = (CoreError, KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError)

_MAX_IDENT = 96
_EXTRA = "_:.-"


def failure(stage, code, field, rule):
    return {"stage": stage, "code": code, "field": field, "rule": rule}


def _ident(x):
    """The text when it is a short ASCII identifier, otherwise None (nothing free-form ever reaches a report)."""
    if not isinstance(x, str) or not 0 < len(x) <= _MAX_IDENT:
        return None
    for c in x:
        if not (c.isascii() and (c.isalnum() or c in _EXTRA)):
            return None
    return x


def from_exception(stage, exc, version):
    """PersistenceError and CoreError give their code/field/rule (a CoreError has no rule); anything else is
    `malformed` of the version in use (schema 1 -> snapshot_invalid, otherwise history_invalid)."""
    if isinstance(exc, CoreError):
        code = _ident(exc.code)
        if code is not None:
            rule = _ident(exc.rule) if isinstance(exc, PersistenceError) else None
            return failure(stage, code, _ident(exc.field), rule)
    if version == 1:
        return failure(stage, "snapshot_invalid", "snapshot", "malformed")
    return failure(stage, "history_invalid", "history", "malformed")
