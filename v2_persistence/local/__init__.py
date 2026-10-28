"""V2 persistence domain, stage S2: a local, file-based test adapter for the S1 Snapshot.

Standard library plus v2_persistence / v2_core only. Not a production store; no network, clock or credentials.
"""
from .errors import LocalStoreError
from .results import (COMMITTED, FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, INITIALIZED, LocalCommitResult,
                      LocalInitResult)
from .store import FILE_SYNC_ONLY_MODE, STRICT, LocalFileStore

__all__ = ["LocalFileStore", "LocalCommitResult", "LocalInitResult", "LocalStoreError", "STRICT",
           "FILE_SYNC_ONLY_MODE", "COMMITTED", "INITIALIZED", "FILE_AND_DIRECTORY_SYNC", "FILE_SYNC_ONLY"]
