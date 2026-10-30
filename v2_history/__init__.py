"""V2 history, stage S3-B1: the schema-2 history value, its checker and the explicit migration plan, all in memory.

Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
randomness. Depends on the standard library, v2_core, v2_persistence and v2_recovery (all unchanged). A History is an
in-memory verification value, not a storage format that any store reads or writes. Restoring and restarting are only
*checked* here (records written by a later stage); no plan to restore, restart, project a ledger or run a day exists.
Draft, not adopted for production.
"""
from .genesis import make_history_genesis
from .migrate import (CONFIRMED_IN_MEMORY, READY, MigrationConfirmResult, MigrationPlan, confirm_migration_plan,
                      migrated_sources, prepare_migration_plan)
from .validate import Boundary, HistoryCheck, validate_history
from .values import (ACK, APPLY, DECLARE_MISSING, GENESIS, KINDS, RECOVERY_RESTORE, RESTART_UNKNOWN,
                     SCHEMA_MIGRATION, SCHEMA_VERSION_V2, History, decode_history, encode_history)

__all__ = ["History", "encode_history", "decode_history", "validate_history", "make_history_genesis",
           "migrated_sources", "prepare_migration_plan", "confirm_migration_plan", "HistoryCheck", "Boundary",
           "MigrationPlan", "MigrationConfirmResult", "SCHEMA_VERSION_V2", "KINDS", "GENESIS", "APPLY", "ACK",
           "DECLARE_MISSING", "RESTART_UNKNOWN", "RECOVERY_RESTORE", "SCHEMA_MIGRATION", "READY",
           "CONFIRMED_IN_MEMORY"]
