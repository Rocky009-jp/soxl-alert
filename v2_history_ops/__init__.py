"""V2 history operations, stage S3-B-2: the ledger projection over every effective segment, the day preparation on a
checked schema-2 history, the plan and confirmation of new acknowledgements / missing-session declarations, and the
append batch value with its pure re-check -- all in memory.

Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
randomness. Depends on the standard library, v2_core, v2_persistence, v2_recovery and v2_history. A candidate History
or a HistoryAppendBatch is an in-memory verification value, not something any store reads or writes: committed and
committable are always False, no value is an AppendPlan, and nothing is stored, published, locked or compared and
swapped. Restoring, restarting, damage diagnosis and publication are not here. Draft, not adopted for production.
"""
from v2_persistence.plan import ALREADY_APPLIED, NO_COMMIT, PREPARED

from .batch import DAILY, RESOLUTION, HistoryAppendBatch, check_append_batch
from .daily import HistoryDayResult, prepare_history_day
from .plan import (CONFIRMED_IN_MEMORY, NO_CHANGE, READY, HistoryResolutionConfirmResult, HistoryResolutionPlan,
                   confirm_history_resolution_plan, prepare_history_resolution_plan)
from .read import project_history_ledger, read_effective
from .values import EffectiveView, HistoryLedger

__all__ = ["read_effective", "project_history_ledger", "prepare_history_day", "prepare_history_resolution_plan",
           "confirm_history_resolution_plan", "check_append_batch", "HistoryAppendBatch", "EffectiveView",
           "HistoryLedger", "HistoryDayResult", "HistoryResolutionPlan", "HistoryResolutionConfirmResult",
           "PREPARED", "NO_COMMIT", "ALREADY_APPLIED", "READY", "NO_CHANGE", "CONFIRMED_IN_MEMORY", "DAILY",
           "RESOLUTION"]
