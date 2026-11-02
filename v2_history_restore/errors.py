"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def restore_invalid(field, rule):
    """A mistake in what the caller asked for (or a plan that cannot be read), as opposed to a broken history."""
    return PersistenceError("restore_invalid", field, rule=rule)


def candidate_invalid():
    """The candidate this package built is not what it must be: an internal inconsistency, never a caller mistake."""
    return PersistenceError("history_invalid", "history", rule="restore_candidate")


def requires_consume(d):
    """A day would have to be consumed anew; CONSUME is not planned in this stage."""
    return PersistenceError("restore_requires_consume", "ops", detail=d)


def decision_changed(d):
    return PersistenceError("restore_decision_changed", "observations", detail=d)


def market_input_changed(d):
    return PersistenceError("restore_market_input_changed", "series", detail=d)


def no_effect():
    return PersistenceError("restore_no_effect", "ops")
