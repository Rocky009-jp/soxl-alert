"""LocalFileStore: the S1 Snapshot saved as one file, snapshot.json, in an explicit dedicated directory.

A test adapter for the local machine, not an adopted production store. One writer at a time through an exclusively
created write.lock (never expired, never taken over); every read re-reads and fully re-validates the file; a commit
re-reads under the lock, compares the expected head, validates the whole candidate and publishes it with one
os.replace of a temporary file written in the same directory. Market logic and history checks stay in S1.

No network, clock, environment variable, notification, retry, automatic repair or unlock exists here.
"""
import os
import secrets
import stat

from ..codec import Snapshot, decode_snapshot, encode_snapshot
from ..errors import snapshot_invalid
from ..events import append_event
from ..plan import AppendPlan
from ..recompute import validate_snapshot
from .errors import (CLEANUP_LOCK_FOREIGN, CLEANUP_LOCK_LEFT, CLEANUP_TMP_LEFT, CLEANUP_TMP_UNCONFIRMED,
                     LocalStoreError)
from .fsops import FileOps
from .results import (COMMITTED, FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY, INITIALIZED, LocalCommitResult,
                      LocalInitResult)

SNAPSHOT_NAME = "snapshot.json"
LOCK_NAME = "write.lock"
TMP_PREFIX = ".snapshot."
TMP_SUFFIX = ".tmp"
LOCK_MAGIC = b"v2_persistence.local.lock\n"

STRICT = "strict"
FILE_SYNC_ONLY_MODE = "file_sync_only"
_MODES = (STRICT, FILE_SYNC_ONLY_MODE)


class _Lock:
    __slots__ = ("path", "dev", "ino", "marker")

    def __init__(self, path, dev, ino, marker):
        self.path, self.dev, self.ino, self.marker = path, dev, ino, marker


class _Ctx:
    """Set by a body once the replace has been called: from then on a failure is store_commit_uncertain."""
    __slots__ = ("published",)

    def __init__(self):
        self.published = False


class LocalFileStore:
    def __init__(self, root, writable=False, durability=STRICT, *, _ops=None):
        # `_ops` is a test seam (recording / fault-injecting FileOps). It is not part of the contract.
        self._ops = FileOps() if _ops is None else _ops
        self._root_arg = root
        if durability not in _MODES:
            raise LocalStoreError("store_config_invalid", "durability", "args")
        if type(writable) is not bool:
            raise LocalStoreError("store_config_invalid", "writable", "args")
        self._writable = writable
        self._durability = durability
        self._dir = self._check_root()

    def __repr__(self):
        return "LocalFileStore(writable=%s, durability=%s)" % (self._writable, self._durability)

    @property
    def writable(self):
        return self._writable

    @property
    def durability(self):
        return self._durability

    @property
    def persistence_level(self):
        return FILE_AND_DIRECTORY_SYNC if self._durability == STRICT else FILE_SYNC_ONLY

    # --- public API ----------------------------------------------------------------------------------------
    def read(self):
        """The validated Snapshot, read from disk under the lock every time. Takes the lock even though it writes
        nothing; a missing lock-creation right is an I/O error, not read-only mode."""
        self._dir = self._check_root()

        def body(lock, ctx):
            self._scan()
            return self._load()
        return self._locked(body)

    def initialize(self, genesis):
        validate_snapshot(genesis)
        if len(genesis.events) != 1:
            raise snapshot_invalid("initialize_not_genesis_only")
        self._require_writable()
        self._dir = self._check_root()

        def body(lock, ctx):
            self._scan()
            if self._load(missing_ok=True) is not None:
                raise LocalStoreError("already_initialized", "store", "read")
            self._publish(lock, ctx, genesis)
            return LocalInitResult(INITIALIZED, True, genesis, self.persistence_level)
        return self._locked(body)

    def commit(self, plan):
        if not isinstance(plan, AppendPlan):
            raise snapshot_invalid("plan_type")
        self._require_writable()
        self._dir = self._check_root()

        def body(lock, ctx):
            self._scan()
            current = self._load()
            if plan.expected_head_seq != current.head_seq or plan.expected_head_hash != current.head_hash:
                raise LocalStoreError("cas_conflict", "head", "cas")
            candidate = append_event(current, plan.event)
            validate_snapshot(candidate)
            self._publish(lock, ctx, candidate)
            return LocalCommitResult(COMMITTED, True, candidate, self.persistence_level)
        return self._locked(body)

    # --- configuration and root ----------------------------------------------------------------------------
    def _require_writable(self):
        if not self._writable:
            raise LocalStoreError("store_read_only", "store", "args")

    def _check_root(self):
        """The resolved root directory: an existing, absolute, dedicated directory that is not itself a link."""
        ops = self._ops
        try:
            raw = os.fspath(self._root_arg)
        except TypeError:
            raw = None
        ok, real = False, None
        if isinstance(raw, str) and raw and "\0" not in raw and os.path.isabs(raw):
            path = os.path.abspath(raw)
            try:
                st = ops.lstat(path)
                ok = stat.S_ISDIR(st.st_mode) and not ops.is_link_like(st)
                if ok:
                    real = os.path.realpath(path)
            except Exception:
                ok = False
        if not ok or real is None:
            raise LocalStoreError("store_root_invalid", "root", "root")
        return real

    def _managed(self, name):
        path = os.path.join(self._dir, name)
        if os.path.dirname(path) != self._dir:
            raise LocalStoreError("store_root_invalid", "root", "root")
        return path

    # --- lock ----------------------------------------------------------------------------------------------
    def _write_all(self, writer, data):
        ops = self._ops
        view = memoryview(data)
        done = 0
        while done < len(view):
            n = ops.write(writer, view[done:])
            if type(n) is not int or n <= 0 or n > len(view) - done:
                raise OSError("bad write count")
            done += n

    def _acquire(self):
        ops = self._ops
        path = self._managed(LOCK_NAME)
        marker = LOCK_MAGIC + secrets.token_hex(16).encode("ascii") + b"\n"
        err, fd = None, None
        try:
            fd = ops.create_exclusive(path)
        except FileExistsError:
            err = LocalStoreError("store_busy", "lock", "lock_acquire")
        except Exception:
            err = LocalStoreError("store_io_error", "lock", "lock_acquire")
        if err is not None:
            raise err
        st, writer, failed = None, None, False
        try:
            st = ops.fstat(fd)
            writer = ops.open_writer(fd)
            fd = None
            self._write_all(writer, marker)
            ops.close(writer)
            writer = None
        except Exception:
            failed = True
        if failed:
            tokens = self._discard_own(path, st, writer, fd, CLEANUP_LOCK_LEFT)
            raise LocalStoreError("store_io_error", "lock", "lock_acquire", cleanup=tokens)
        return _Lock(path, st.st_dev, st.st_ino, marker)

    def _owns(self, lock):
        """Still our lock file: same inode and our marker. Anything unreadable counts as not confirmed."""
        ops = self._ops
        try:
            st = ops.lstat(lock.path)
            if ops.is_link_like(st) or not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (lock.dev, lock.ino):
                return False
            data, st2 = ops.read_file(lock.path)
            return data == lock.marker and (st2.st_dev, st2.st_ino) == (lock.dev, lock.ino)
        except Exception:
            return False

    def _release(self, lock):
        """None when released, "lost" when the file is no longer ours (left untouched), "failed" when unlink failed."""
        if not self._owns(lock):
            return "lost"
        try:
            self._ops.unlink(lock.path)
        except Exception:
            return "failed"
        return None

    def _locked(self, body):
        lock = self._acquire()
        ctx, exc, value = _Ctx(), None, None
        try:
            value = body(lock, ctx)
        except Exception as e:
            exc = e
        rel = self._release(lock)
        if rel is None:
            if exc is not None:
                raise exc
            return value
        token = CLEANUP_LOCK_FOREIGN if rel == "lost" else CLEANUP_LOCK_LEFT
        phase = "lock_ownership" if rel == "lost" else "lock_release"
        if ctx.published:
            if isinstance(exc, LocalStoreError) and exc.code == "store_commit_uncertain":
                raise exc.add_cleanup(token)
            raise LocalStoreError("store_commit_uncertain", "snapshot", phase, cleanup=(token,),
                                  primary=getattr(exc, "code", None))
        if isinstance(exc, LocalStoreError) and exc.code == "store_lock_ownership_lost" and rel == "lost":
            raise exc.add_cleanup(token)
        code = "store_lock_ownership_lost" if rel == "lost" else "store_io_error"
        raise LocalStoreError(code, "lock", phase, cleanup=(token,), primary=getattr(exc, "code", None))

    # --- reading -------------------------------------------------------------------------------------------
    def _scan(self):
        """Any leftover temporary file of this store stops the operation; nothing is adopted or removed."""
        try:
            names = self._ops.listdir(self._dir)
        except Exception:
            names = None
        if names is None:
            raise LocalStoreError("store_io_error", "root", "scan")
        for name in names:
            if name.startswith(TMP_PREFIX) and name.endswith(TMP_SUFFIX):
                raise LocalStoreError("store_artifact_present", "store", "scan")

    def _load(self, missing_ok=False):
        ops = self._ops
        path = self._managed(SNAPSHOT_NAME)
        code = None
        st = data = st2 = None
        try:
            st = ops.lstat(path)
        except FileNotFoundError:
            code = "missing"
        except Exception:
            code = "io"
        if code == "missing":
            if missing_ok:
                return None
            raise LocalStoreError("store_uninitialized", "store", "read")
        if code is None and (ops.is_link_like(st) or not stat.S_ISREG(st.st_mode)):
            code = "root"
        if code is None:
            try:
                data, st2 = ops.read_file(path)
            except Exception:
                code = "io"
        if code is None and (st.st_dev, st.st_ino) != (st2.st_dev, st2.st_ino):
            code = "root"
        if code == "io":
            raise LocalStoreError("store_io_error", "snapshot", "read")
        if code == "root":
            raise LocalStoreError("store_root_invalid", "root", "read")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is None:
            raise snapshot_invalid("utf8")
        snapshot = decode_snapshot(text)
        validate_snapshot(snapshot)
        return snapshot

    # --- publishing ----------------------------------------------------------------------------------------
    def _discard_own(self, path, st, writer, fd, left_token):
        """Close what is still open, then remove `path` only if it is the very file we created. Returns the fixed
        tokens of what stays behind (empty when everything is clean)."""
        ops = self._ops
        if writer is not None:
            try:
                ops.close(writer)
            except Exception:
                pass
        elif fd is not None:
            try:
                ops.close_fd(fd)
            except Exception:
                pass
        if st is None:
            return (left_token,)
        try:
            now = ops.lstat(path)
        except FileNotFoundError:
            return ()
        except Exception:
            return (left_token,)
        if (now.st_dev, now.st_ino) != (st.st_dev, st.st_ino):
            return (CLEANUP_TMP_UNCONFIRMED,) if left_token == CLEANUP_TMP_LEFT else (left_token,)
        try:
            ops.unlink(path)
        except Exception:
            return (left_token,)
        return ()

    def _publish(self, lock, ctx, snapshot):
        """Section 6.3: sync-mode check, temporary file, full write, flush, file fsync, close, ownership check,
        one os.replace, directory fsync (strict), in this order. The lock is released by the caller."""
        ops = self._ops
        strict = self._durability == STRICT
        if strict:
            if ops.is_windows():
                raise LocalStoreError("store_durability_unsupported", "durability", "durability_probe",
                                      rule="windows_strict")
            try:
                ops.probe_dir_sync(self._dir)
                supported = True
            except Exception:
                supported = False
            if not supported:
                raise LocalStoreError("store_durability_unsupported", "durability", "durability_probe",
                                      rule="directory_sync")
        data = encode_snapshot(snapshot).encode("utf-8")
        target = self._managed(SNAPSHOT_NAME)
        tmp = self._managed(TMP_PREFIX + secrets.token_hex(16) + TMP_SUFFIX)

        phase, fd, st, writer, failed = "tmp_create", None, None, None, False
        try:
            fd = ops.create_exclusive(tmp)
            st = ops.fstat(fd)
            writer = ops.open_writer(fd)
            fd = None
            phase = "write"
            self._write_all(writer, data)
            phase = "flush"
            ops.flush(writer)
            phase = "file_sync"
            ops.fsync_file(writer)
            phase = "close"
            ops.close(writer)
            writer = None
        except Exception:
            failed = True
        if failed:
            created = st is not None or fd is not None or writer is not None or phase != "tmp_create"
            tokens = self._discard_own(tmp, st, writer, fd, CLEANUP_TMP_LEFT) if created else ()
            raise LocalStoreError("store_io_error", "snapshot", phase, cleanup=tokens)

        if not self._owns(lock):
            tokens = self._discard_own(tmp, st, None, None, CLEANUP_TMP_LEFT)
            raise LocalStoreError("store_lock_ownership_lost", "lock", "lock_ownership", cleanup=tokens)

        ctx.published = True
        failed = False
        try:
            ops.replace(tmp, target)
        except Exception:
            failed = True
        if failed:
            tokens = self._discard_own(tmp, st, None, None, CLEANUP_TMP_LEFT)
            raise LocalStoreError("store_commit_uncertain", "snapshot", "replace", cleanup=tokens)
        if strict:
            try:
                ops.fsync_dir(self._dir)
            except Exception:
                failed = True
            if failed:
                raise LocalStoreError("store_commit_uncertain", "snapshot", "dir_sync")
