"""Error type of the local file store. Codes, fields and phases are fixed identifiers; no path, raw OSError text or
input value is ever put into an error (the OS exception is dropped, not chained)."""
from ..errors import PersistenceError

# Fixed `phase` values (where in the operation the error arose).
PHASES = frozenset([
    "args", "root", "lock_acquire", "scan", "read", "validate", "cas", "candidate", "durability_probe",
    "tmp_create", "write", "flush", "file_sync", "close", "lock_ownership", "replace", "dir_sync", "lock_release",
    "tmp_cleanup",
])

# Fixed `cleanup` entries (what a failed or skipped clean-up left behind).
CLEANUP_TMP_LEFT = "tmp_left"
CLEANUP_TMP_UNCONFIRMED = "tmp_ownership_unconfirmed"
CLEANUP_LOCK_LEFT = "lock_left"
CLEANUP_LOCK_FOREIGN = "lock_not_ours_left_untouched"


class LocalStoreError(PersistenceError):
    """PersistenceError plus `phase` (fixed identifier) and `cleanup` (fixed identifiers of leftovers, usually empty).

    `primary` is the code of the error that was already being raised when a clean-up failure replaced it, else None.
    """

    def __init__(self, code, field, phase, rule=None, cleanup=(), primary=None):
        super().__init__(code, field, rule=rule)
        self.phase = phase
        self.cleanup = tuple(cleanup)
        self.primary = primary

    def add_cleanup(self, *items):
        self.cleanup = self.cleanup + tuple(i for i in items if i not in self.cleanup)
        return self
