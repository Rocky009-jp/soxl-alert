"""V2 recovery, stage S3-A: acknowledgement / missing-session declarations as in-memory values, their projection
onto a ledger, and a confirmable (never persisted) plan.

Pure functions over values passed in. No files, paths, stores, clock, network, notification, credentials, threads or
randomness. Depends on the standard library, v2_core and v2_persistence (both unchanged). A ResolutionSet is an
in-memory verification value, not a storage format. Draft, not adopted for production.
"""
from .daily import SimulationDayResult, prepare_resolved_day
from .plan import (CONFIRMED_IN_MEMORY, NO_CHANGE, READY, ConfirmResult, ResolutionPlan, confirm_resolution_plan,
                   prepare_resolution_plan)
from .project import EffectiveLedger, resolve_observations
from .values import ResolutionSet, decode_resolutions, empty_resolutions, encode_resolutions
from .validate import ResolutionCheck, validate_resolutions

__all__ = ["empty_resolutions", "validate_resolutions", "resolve_observations", "prepare_resolution_plan",
           "confirm_resolution_plan", "prepare_resolved_day", "encode_resolutions", "decode_resolutions",
           "ResolutionSet", "ResolutionCheck", "EffectiveLedger", "ResolutionPlan", "ConfirmResult",
           "SimulationDayResult", "READY", "NO_CHANGE", "CONFIRMED_IN_MEMORY"]
