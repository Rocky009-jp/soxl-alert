"""V2 history, stage C-3: the schema-2 history saved as one file, history.json, in an explicit dedicated
directory, written only from a C-2 publication made in the same process.
A test adapter for the local machine, not an adopted production store. One writer at a time through an exclusively
created write.lock (the same name as S2, so S2 and C-3 writers exclude each other; never expired, never taken over);
every operation re-reads and fully re-validates the file under the lock; a publication is checked by the unchanged
check_publication and published with one os.replace of a temporary file written in the same directory. The OS calls
are the unchanged S2 FileOps. No network, clock, environment variable, notification, retry, automatic repair, unlock,
migration or adoption exists here (C-4). Draft, not adopted for production.
"""
from v2_persistence.local import FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, FILE_SYNC_ONLY_MODE, STRICT, LocalStoreError

from .results import INITIALIZED, PUBLISHED, HistoryStoreResult
from .store import HistoryFileStore

__all__ = ["HistoryFileStore", "HistoryStoreResult", "LocalStoreError", "STRICT", "FILE_SYNC_ONLY_MODE", "PUBLISHED",
           "INITIALIZED", "FILE_AND_DIRECTORY_SYNC", "FILE_SYNC_ONLY"]
