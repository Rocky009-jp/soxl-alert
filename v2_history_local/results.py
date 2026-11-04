"""Result value of the history file store. Immutable; the History inside is itself immutable (copies on access)."""
from dataclasses import dataclass
from typing import Any

PUBLISHED = "PUBLISHED"
INITIALIZED = "INITIALIZED"


@dataclass(frozen=True)
class HistoryStoreResult:
    """Only a normal completion returns this: published, synchronised as `persistence_level` says, lock released.
    Not a guarantee against power loss of the whole machine, and not a right to notify."""
    status: str
    committed: bool
    history: Any
    persistence_level: str
    publication_hash: str
