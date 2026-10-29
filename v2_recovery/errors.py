"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def resolution_invalid(field, rule, detail=None):
    return PersistenceError("resolution_invalid", field, detail=detail, rule=rule)


def request_conflict():
    return PersistenceError("resolution_request_conflict", "request_id")


def plan_mismatch():
    return PersistenceError("resolution_plan_mismatch", "plan")


def plan_stale():
    return PersistenceError("resolution_plan_stale", "plan")
