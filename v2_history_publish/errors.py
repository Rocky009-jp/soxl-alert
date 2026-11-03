"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def publication_invalid(rule):
    """The publication value itself is wrong (form, hash, mode, integer range, records, candidate), or an argument of
    the check is misused (the type of the current bytes, the v1 bytes)."""
    return PersistenceError("publication_invalid", "publication", rule=rule)


def publication_stale(rule):
    """The current bytes are not what the publication expects (another write came first, or the file is absent)."""
    return PersistenceError("publication_stale", "current", rule=rule)


def publication_refused(rule):
    """The confirming step gave nothing to publish (NO_CHANGE, a day that is not PREPARED)."""
    return PersistenceError("publication_refused", "source", rule=rule)


def history_unreadable(rule):
    """Bytes that are not a fully valid schema-2 history (the same code and rule family as the history checker)."""
    return PersistenceError("history_invalid", "history", rule=rule)


def candidate_invalid():
    """The candidate this package built is not what it must be: an internal inconsistency, never a caller mistake."""
    return PersistenceError("history_invalid", "history", rule="publication_candidate")
