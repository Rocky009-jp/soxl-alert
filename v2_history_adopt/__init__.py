"""V2 history, stage S3-B-5b: the plan and the in-memory confirmation of one RECOVERY_PREFIX_ADOPTION record, which keeps
the verified first records of a damaged schema-2 history and names the raw bytes whose remainder is discarded.

Pure functions over bytes. The diagnosis of S3-B-5a is made once and the candidate History (verified prefix plus the
adoption record) is checked by the history checker of B-1. No files, paths, stores, clock, network,
notification, credentials, threads or randomness; no ledger, sessions or series are taken. Depends on the standard
library (copy), v2_core, v2_persistence, v2_recovery, v2_history, v2_history_ops and v2_history_diagnose. The result is a
candidate History, an in-memory verification value: committed is always False. Saving the raw bytes aside,
publishing, comparing with the original file and consuming a day are not here (S3-C and later). Draft, not adopted
for production.
"""
from .confirm import confirm_prefix_adoption
from .prepare import prepare_prefix_adoption
from .values import CONFIRMED_IN_MEMORY, NO_CHANGE, READY, AdoptionConfirmResult, AdoptionPlan

__all__ = ["prepare_prefix_adoption", "confirm_prefix_adoption", "AdoptionPlan", "AdoptionConfirmResult", "READY",
           "CONFIRMED_IN_MEMORY", "NO_CHANGE"]
