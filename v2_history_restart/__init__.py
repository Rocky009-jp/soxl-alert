"""V2 history restart, stage S3-B-3: the plan and the in-memory confirmation of one RESTART_UNKNOWN record on a checked
schema-2 history.

Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
randomness. Depends on the standard library, v2_core, v2_persistence, v2_recovery, v2_history and v2_history_ops
(all unchanged). The result is a candidate History, an in-memory verification value: committed and committable are
always False, there is no batch, and nothing is stored, published, locked or compared and swapped. Restoring, damage
diagnosis and publication are not here. Draft, not adopted for production.
"""
from .confirm import confirm_restart_plan
from .prepare import prepare_restart_plan
from .values import CONFIRMED_IN_MEMORY, NO_CHANGE, READY, RestartConfirmResult, RestartPlan

__all__ = ["prepare_restart_plan", "confirm_restart_plan", "RestartPlan", "RestartConfirmResult", "READY",
           "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
