"""The only place of the maintenance package that touches the OS: the unchanged S2 FileOps plus two more calls.

Tests substitute a subclass (recording or fault-injecting) through HistoryMaintenance's private `_ops` argument. The
default instance does exactly what the names say; nothing here decides policy, retries or reads a clock."""
import os

from v2_persistence.local.fsops import FileOps


class MaintenanceOps(FileOps):
    def mkdir(self, path):
        """A new directory, owner-only. Fails with FileExistsError if anything is at the path."""
        os.mkdir(path, 0o700)

    def rename(self, src, dst):
        """Move within one file system; the content and the inode stay as they are."""
        os.rename(src, dst)
