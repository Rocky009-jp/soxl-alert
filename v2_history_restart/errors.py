"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def restart_invalid(field, rule):
    """A mistake in what the caller asked for (or a plan that cannot be read), as opposed to a broken history."""
    return PersistenceError("restart_invalid", field, rule=rule)


def candidate_invalid():
    """The candidate this package built is not what it must be: an internal inconsistency, never a caller mistake."""
    return PersistenceError("history_invalid", "history", rule="restart_candidate")
