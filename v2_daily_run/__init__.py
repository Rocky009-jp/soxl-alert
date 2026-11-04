"""V2 S4-A, the morning run: one call that catches up on every confirmed session after the history's processing start,
one DAILY publication per day through an injected store, then evaluates the latest closed session and returns the
preview text and a report. Offline: the clock, the store, the market data, the sessions and the ledger are all passed
in. No notification, outbox, retry, unlock, migration, adoption, network, file, environment variable or process here.
Draft, not adopted for production."""
from .run import run_morning
from .values import DONE, STALE, STOPPED, ConsumedDay, RunError, RunReport

__all__ = ["run_morning", "RunReport", "ConsumedDay", "RunError", "DONE", "STALE", "STOPPED"]
