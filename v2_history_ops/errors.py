"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def history_invalid(rule):
    return PersistenceError("history_invalid", "history", rule=rule)


def history_request_conflict():
    return PersistenceError("history_request_conflict", "request_id")


def history_plan_mismatch():
    return PersistenceError("history_plan_mismatch", "plan")


def history_plan_stale():
    return PersistenceError("history_plan_stale", "plan")


def batch_invalid(rule):
    return PersistenceError("batch_invalid", "batch", rule=rule)


def batch_stale():
    return PersistenceError("batch_stale", "head")
