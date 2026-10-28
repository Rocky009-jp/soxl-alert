"""The only place of the local store that touches the OS: thin wrappers over os calls.

Tests substitute a subclass (recording or fault-injecting) through LocalFileStore's private `_ops` argument. The
default instance does exactly what the names say; nothing here decides policy, retries or reads a clock.
"""
import os
import stat
import sys

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FileOps:
    def is_windows(self):
        return sys.platform == "win32"

    # --- metadata ------------------------------------------------------------------------------------------
    def lstat(self, path):
        return os.lstat(path)

    def fstat(self, fd):
        return os.fstat(fd)

    def listdir(self, path):
        return os.listdir(path)

    def is_link_like(self, st):
        """A symbolic link, or (Windows) any reparse point. Never followed."""
        if stat.S_ISLNK(st.st_mode):
            return True
        return bool(_REPARSE and getattr(st, "st_file_attributes", 0) & _REPARSE)

    # --- exclusive creation (lock and temporary file) --------------------------------------------------------
    def create_exclusive(self, path):
        """O_CREAT|O_EXCL: fails with FileExistsError if anything (even a dangling link) is at the path."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY | _O_CLOEXEC
        return os.open(path, flags, 0o600)

    def open_writer(self, fd):
        """An unbuffered binary writer over fd (write may be short). Closing it closes fd."""
        return os.fdopen(fd, "wb", buffering=0)

    def close_fd(self, fd):
        os.close(fd)

    # --- writing ---------------------------------------------------------------------------------------------
    def write(self, writer, data):
        return writer.write(data)

    def flush(self, writer):
        writer.flush()

    def fsync_file(self, writer):
        os.fsync(writer.fileno())

    def close(self, writer):
        writer.close()

    def replace(self, src, dst):
        os.replace(src, dst)

    def probe_dir_sync(self, path):
        """Can this directory be opened and fsynced? Done before anything is published."""
        _sync_directory(path)

    def fsync_dir(self, path):
        _sync_directory(path)

    def unlink(self, path):
        os.unlink(path)

    # --- reading ---------------------------------------------------------------------------------------------
    def read_file(self, path):
        """Whole content of a regular file, opened without following a final link. Returns (bytes, st)."""
        fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW | _O_BINARY | _O_CLOEXEC)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise OSError("not a regular file")
            chunks = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks), st
        finally:
            os.close(fd)
