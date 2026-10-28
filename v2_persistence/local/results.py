"""Result values of the local file store. Immutable; the Snapshot inside is itself immutable (copies on access)."""
from dataclasses import dataclass
from typing import Any

FILE_AND_DIRECTORY_SYNC = "FILE_AND_DIRECTORY_SYNC"
FILE_SYNC_ONLY = "FILE_SYNC_ONLY"

COMMITTED = "COMMITTED"
INITIALIZED = "INITIALIZED"


@dataclass(frozen=True)
class LocalCommitResult:
    """Only a normal completion returns this: published, synchronised as `persistence_level` says, lock released.

    It is not a guarantee against power loss of the whole machine; see the design (7) and the result document.
    """
    status: str
    committed: bool
    snapshot: Any
    persistence_level: str


@dataclass(frozen=True)
class LocalInitResult:
    status: str
    initialized: bool
    snapshot: Any
    persistence_level: str
