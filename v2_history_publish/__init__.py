"""V2 history publication, stage C-2: the value that a later store (C-3, C-4) may write, built only from a confirmed
result, and its pure compare-and-swap check and read-only reconciliation.
Pure functions over values and bytes passed in. No files, paths, stores, locks, clock, network, notification,
credentials, threads or randomness. Depends on the standard library (copy, hashlib) and on v2_core, v2_persistence,
v2_recovery, v2_history, v2_history_ops, v2_history_restart, v2_history_restore and v2_history_adopt (all unchanged).
Every builder runs the confirming step itself with the inputs it is given; there is no builder that takes a History, a
confirm result or a dict, so a history that only passed the history checker is never published. check_publication is
not a confirmation: it checks the form of a value that a builder made and the current bytes. committed is always False.
Draft, not adopted for production.
"""
from .build import (publish_adoption, publish_day, publish_genesis, publish_migration, publish_resolution,
                    publish_restart, publish_restore)
from .check import check_publication, reconcile_publication
from .read import history_bytes, raw_identity, read_history_bytes
from .values import (ADOPTION, APPEND, CONFLICT, CREATE, DAILY, GENESIS, MIGRATION, NOT_PUBLISHED, PUBLISHED,
                     PUBLISHED_THEN_EXTENDED, REPLACE, RESOLUTION, RESTART, RESTORE, HistoryPublication,
                     Reconciliation)

__all__ = ["publish_day", "publish_resolution", "publish_restart", "publish_restore", "publish_genesis",
           "publish_migration", "publish_adoption", "check_publication", "reconcile_publication", "history_bytes",
           "read_history_bytes", "raw_identity", "HistoryPublication", "Reconciliation", "APPEND", "CREATE",
           "REPLACE", "DAILY", "RESOLUTION", "RESTART", "RESTORE", "GENESIS", "MIGRATION", "ADOPTION", "PUBLISHED",
           "PUBLISHED_THEN_EXTENDED", "NOT_PUBLISHED", "CONFLICT"]
