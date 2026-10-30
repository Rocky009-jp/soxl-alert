"""Error helpers. The persistence error type is reused: a fixed code, field and rule, never a raw value."""
from v2_persistence.errors import PersistenceError


def history_invalid(rule):
    return PersistenceError("history_invalid", "history", rule=rule)


def unsupported_schema(field):
    return PersistenceError("unsupported_schema", field)


def unsupported_event():
    return PersistenceError("unsupported_event", "kind")


def migration_request_conflict():
    return PersistenceError("migration_request_conflict", "request_id")


def migration_plan_mismatch():
    return PersistenceError("migration_plan_mismatch", "plan")


def migration_plan_stale():
    return PersistenceError("migration_plan_stale", "plan")
