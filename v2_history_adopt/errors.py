"""Error helper. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def adoption_invalid(field, rule):
    return PersistenceError("adoption_invalid", field, rule=rule)


def candidate_failure():
    """The package's own inconsistency (a verified prefix or its candidate did not pass): not a caller's mistake."""
    return PersistenceError("history_invalid", "history", rule="adoption_candidate")
