"""V2 history, stage S3-B-5a: a read-only diagnosis of the raw bytes of a stored history (schema 2) or snapshot
(schema 1).

One pure function over bytes: it reads strictly, runs the unchanged checkers and reports what is verified, what would be
discarded and why. It writes nothing, returns no History, takes no ledger, sessions or series, and never repairs or
adopts anything. No files, paths, stores, clock, network, notification, credentials, threads or randomness. Depends on
the standard library (copy, hashlib) and on v2_core, v2_persistence, v2_recovery and v2_history (all unchanged).
Draft, not adopted for production.
"""
from .diagnose import diagnose_history_bytes
from .values import NO_VALID_PREFIX, PREFIX_ONLY, UNREADABLE, VALID, HistoryDiagnosis

__all__ = ["diagnose_history_bytes", "HistoryDiagnosis", "VALID", "PREFIX_ONLY", "NO_VALID_PREFIX", "UNREADABLE"]
