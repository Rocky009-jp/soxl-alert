"""V2 history restore, stage S3-B-4: the plan and the in-memory confirmation of one RECOVERY_RESTORE record, with the
records it makes, on a checked schema-2 history.

Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
randomness. Depends on the standard library, v2_core, v2_persistence, v2_recovery, v2_history and v2_history_ops (all
unchanged). The result is a candidate History, an in-memory verification value: committed and committable are always
False, there is no batch, and nothing is stored, published, locked or compared and swapped. Four operations only
(REAPPLY, REPLAY, DROP, RETIRE); a day that would have to be consumed anew is refused. Consuming, damage diagnosis and
publication are not here. Draft, not adopted for production.
"""
from .confirm import confirm_restore_plan
from .prepare import prepare_restore_plan
from .values import CONFIRMED_IN_MEMORY, NO_CHANGE, READY, RestoreConfirmResult, RestorePlan

__all__ = ["prepare_restore_plan", "confirm_restore_plan", "RestorePlan", "RestoreConfirmResult", "READY",
           "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
