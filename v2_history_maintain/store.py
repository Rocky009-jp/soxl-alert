"""HistoryMaintenance: the person's steps that bring a stopped C-3 root back to a normal state (C-4).

Six operations over one dedicated root: inspect (no lock), read_original and read_set_aside (under the lock), and unlock,
migrate and adopt (under the lock, or, for an unlock whose plan names the left lock, with that lock as the exclusion).
Every byte that is moved or replaced is first kept under quarantine/<key>/ with a MANIFEST that is a pure function of what
the operation is about; nothing in quarantine/ is ever deleted here. The lock, scan, read and publish steps follow C-3
(v2_history_local/store.py) one by one over the S2 FileOps plus mkdir and rename (ops.py); the C-3 and S2 stores are not
imported. Only a C-2 publication that a builder made is accepted (`type(p) is HistoryPublication`); this package never
builds, copies or forges one. A failure that leaves the root in an in-between state is reported with fixed words and
the list of what is left is read again by `inspect`, never guessed from a clean-up word. No network, clock, environment
variable, notification, retry, automatic repair or deletion exists here."""
import os
import secrets
import stat

from v2_core.errors import CoreError
from v2_history.common import is_hex64
from v2_history_publish import (ADOPTION, CREATE, MIGRATION, PUBLISHED, PUBLISHED_THEN_EXTENDED, REPLACE,
                                HistoryPublication, check_publication, history_bytes, raw_identity,
                                read_history_bytes, reconcile_publication)
from v2_persistence.local.errors import (CLEANUP_LOCK_FOREIGN, CLEANUP_LOCK_LEFT, CLEANUP_TMP_LEFT,
                                         CLEANUP_TMP_UNCONFIRMED, LocalStoreError)
from v2_persistence.local.results import FILE_AND_DIRECTORY_SYNC, FILE_SYNC_ONLY
from v2_persistence.local.store import FILE_SYNC_ONLY_MODE, STRICT

from .ops import MaintenanceOps
from .values import (ADOPTED, EMPTY, HISTORY_NAME, KIND_LOCK, KIND_TMP, LOCK_MAGIC, LOCK_NAME, MANIFEST_NAME, MIGRATED,
                     OP_ADOPTION, OP_MIGRATION, QUARANTINE_NAME, Q_TMP_PREFIX, TMP_PREFIX, TMP_SUFFIX, UNLOCKED,
                     V1_AND_V2, V1_NAME, V1_ONLY, V2, MaintenanceResult, RootReport, check_plan, is_q_tmp,
                     is_root_tmp, lock_owner, maintenance_error, manifest_bytes, manifest_dict, read_manifest,
                     safe_name, unlock_manifest)

_MODES = (STRICT, FILE_SYNC_ONLY_MODE)
_PUBLICATION_CODES = ("publication_invalid", "publication_stale")
_QUARANTINE_FIELD = "quarantine"


class _Lock:
    __slots__ = ("path", "dev", "ino", "marker")

    def __init__(self, path, dev, ino, marker):
        self.path, self.dev, self.ino, self.marker = path, dev, ino, marker


class _Ctx:
    """changed: a change to the root was begun (set just before the first call that may change it, so an uncertain call
    counts); published: the replace of history.json was begun (C-3's meaning)."""
    __slots__ = ("changed", "published")

    def __init__(self):
        self.changed = False
        self.published = False


def _publication(publication):
    """The value itself, before any lock: only the exact class is taken."""
    if type(publication) is not HistoryPublication:
        raise LocalStoreError("store_publication_invalid", "publication", "args", rule="type")
    return publication


def _kind(publication):
    """(mode, source, hash) of a publication, read so that no exception can leave: a hand-made value whose body lacks
    `mode` or `source`, or whose hash is not a 64-digit hex string (it names a directory), is a form error of the value
    (rule shape), seen before the lock is taken."""
    try:
        view = publication.to_dict()
        mode, source, key = view["body"]["mode"], view["body"]["source"], view["publication_hash"]
        shaped = is_hex64(key)
    except Exception:
        shaped = False
    if not shaped:
        raise LocalStoreError("store_publication_invalid", "publication", "args", rule="shape")
    return mode, source, key


def _checked(current, publication, source_v1=None):
    """check_publication after the current bytes were read under the lock: its refusals for the publication and the
    current state pass through; any other error is about the candidate the value carries (an internal inconsistency of a
    hand-made value), never a broken current file."""
    try:
        return check_publication(current, publication, source_v1)
    except CoreError as e:
        if e.code in _PUBLICATION_CODES:
            raise
        raise LocalStoreError("store_candidate_invalid", "publication", "candidate") from None


def _incomplete(exc, ctx):
    """A failure of a quarantine step after a change was begun is `maintenance_incomplete` (primary: the code that
    arose); the person looks at the root with `inspect` and calls the same operation again."""
    if (ctx.changed and isinstance(exc, LocalStoreError) and exc.code == "store_io_error"
            and exc.field == _QUARANTINE_FIELD):
        return maintenance_error("maintenance_incomplete", _QUARANTINE_FIELD, exc.phase, cleanup=exc.cleanup,
                                 primary=exc.code)
    return exc


class HistoryMaintenance:
    def __init__(self, root, writable=False, durability=STRICT, *, _ops=None):
        self._ops = MaintenanceOps() if _ops is None else _ops
        self._root_arg = root
        if durability not in _MODES:
            raise LocalStoreError("store_config_invalid", "durability", "args")
        if type(writable) is not bool:
            raise LocalStoreError("store_config_invalid", "writable", "args")
        self._writable = writable
        self._durability = durability
        self._dev = None
        self._dir = self._check_root()

    def __repr__(self):
        return "HistoryMaintenance(writable=%s, durability=%s)" % (self._writable, self._durability)

    writable = property(lambda self: self._writable)
    durability = property(lambda self: self._durability)

    @property
    def persistence_level(self):
        return FILE_AND_DIRECTORY_SYNC if self._durability == STRICT else FILE_SYNC_ONLY

    # ==== public API ============================================================================================
    def inspect(self):
        """What the root holds, read without the lock (a left lock is reported, not obeyed). Changes nothing."""
        self._dir = self._check_root()
        names = set(self._names())
        history = self._entry(HISTORY_NAME, names, True)
        v1 = self._entry(V1_NAME, names, False)
        layout = V1_AND_V2 if (history and v1) else V2 if history else V1_ONLY if v1 else EMPTY
        artifacts = [self._artifact(n, KIND_TMP) for n in sorted(n for n in names if is_root_tmp(n))]
        if LOCK_NAME in names:
            artifacts.append(self._artifact(LOCK_NAME, KIND_LOCK))
        artifacts = [a for a in artifacts if a is not None]
        return RootReport._make({"layout": layout, "history": history, "v1": v1, "artifacts": artifacts,
                                 "quarantine": self._quarantine_report(names)})

    def read_original(self, name):
        """The raw bytes of history.json or snapshot.json, read under the lock. Nothing is checked or changed."""
        if name not in (HISTORY_NAME, V1_NAME):
            raise LocalStoreError("store_config_invalid", "name", "args")
        self._dir = self._check_root()

        def body(lock, ctx):
            got = self._read(self._managed(name), "history" if name == HISTORY_NAME else "snapshot", "read")
            if got is None:
                raise LocalStoreError("store_uninitialized", "store", "read")
            return got[0]
        return self._locked(body)

    def read_set_aside(self, key, name):
        """Bytes kept under quarantine/<key>/, returned only when they are what the MANIFEST says."""
        if not is_hex64(key):
            raise LocalStoreError("store_config_invalid", "key", "args")
        if not (safe_name(name) and (name in (HISTORY_NAME, V1_NAME, LOCK_NAME) or is_root_tmp(name))):
            raise LocalStoreError("store_config_invalid", "name", "args")
        self._dir = self._check_root()

        def body(lock, ctx):
            kpath = self._q_find(key)
            if kpath is None:
                raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "quarantine",
                                        rule="missing")
            entries = self._q_list(kpath)
            manifest = self._q_read_manifest(kpath, entries, key)
            allowed = {t["name"] for t in manifest["targets"]}
            self._q_check_names(entries, allowed)
            target = [t for t in manifest["targets"] if t["name"] == name]
            if not target:
                raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "read", rule="target")
            got = self._read_regular(os.path.join(kpath, name), _QUARANTINE_FIELD, "read")
            if got is None or got is False:
                raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "read", rule="missing")
            if raw_identity(got[0]) != {"raw_sha256": target[0]["raw_sha256"], "raw_size": target[0]["raw_size"]}:
                raise maintenance_error("maintenance_set_aside_mismatch", _QUARANTINE_FIELD, "read")
            return got[0]
        return self._locked(body)

    def unlock(self, plan, confirmed_plan_hash):
        """Move the left lock and temporary files that a confirmed plan names into quarantine/<plan_hash>/."""
        body, plan_hash = check_plan(plan)
        if type(confirmed_plan_hash) is not str or confirmed_plan_hash != plan_hash:
            raise maintenance_error("maintenance_plan_unconfirmed", "plan", "args")
        self._require_writable()
        self._dir = self._check_root()
        if body["targets"][-1]["kind"] == KIND_LOCK:
            return self._exclusive_by_plan_lock(lambda ctx: self._unlock_body(body, plan_hash, None, ctx))
        if LOCK_NAME in self._names():                    # a lock appeared after the plan: it is old
            raise maintenance_error("maintenance_plan_stale", "store", "scan")
        return self._locked(lambda lock, ctx: self._unlock_body(body, plan_hash, lock, ctx))

    def migrate(self, publication, writers_stopped):
        """v1 -> v2 by a MIGRATION publication, the writers declared stopped: snapshot.json is set aside."""
        pub = _publication(publication)
        mode, source, key = _kind(pub)
        if mode != CREATE or source != MIGRATION:
            raise LocalStoreError("store_operation_unsupported", "publication", "args", rule="not_migration")
        if writers_stopped is not True:
            raise maintenance_error("maintenance_declaration_missing", "writers_stopped", "args")
        self._require_writable()
        self._dir = self._check_root()
        return self._locked(lambda lock, ctx: self._migrate_body(pub, key, lock, ctx))

    def adopt(self, publication):
        """Prefix adoption by an ADOPTION publication: the original history.json is kept, then replaced."""
        pub = _publication(publication)
        mode, source, key = _kind(pub)
        if mode != REPLACE or source != ADOPTION:
            raise LocalStoreError("store_operation_unsupported", "publication", "args", rule="not_adoption")
        self._require_writable()
        self._dir = self._check_root()
        return self._locked(lambda lock, ctx: self._adopt_body(pub, key, lock, ctx))

    # ==== configuration and root (S2) ===========================================================================
    def _require_writable(self):
        if not self._writable:
            raise LocalStoreError("store_read_only", "store", "args")

    def _check_root(self):
        ops = self._ops
        try:
            raw = os.fspath(self._root_arg)
        except TypeError:
            raw = None
        ok, real, dev = False, None, None
        if isinstance(raw, str) and raw and "\0" not in raw and os.path.isabs(raw):
            path = os.path.abspath(raw)
            try:
                st = ops.lstat(path)
                ok = stat.S_ISDIR(st.st_mode) and not ops.is_link_like(st)
                if ok:
                    real = os.path.realpath(path)
                    dev = st.st_dev
            except Exception:
                ok = False
        if not ok or real is None:
            raise LocalStoreError("store_root_invalid", "root", "root")
        self._dev = dev
        return real

    def _managed(self, name):
        path = os.path.join(self._dir, name)
        if os.path.dirname(path) != self._dir:
            raise LocalStoreError("store_root_invalid", "root", "root")
        return path

    # ==== lock (C-3) ============================================================================================
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
            if self._exists(path):
                err = LocalStoreError("store_busy", "lock", "lock_acquire")
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

    def _exists(self, path):
        try:
            self._ops.lstat(path)
        except Exception:
            return False
        return True

    def _owns(self, lock):
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
        exc = _incomplete(exc, ctx)
        rel = self._release(lock)
        if rel is None:
            if exc is not None:
                raise exc
            return value
        token = CLEANUP_LOCK_FOREIGN if rel == "lost" else CLEANUP_LOCK_LEFT
        phase = "lock_ownership" if rel == "lost" else "lock_release"
        earlier = tuple(getattr(exc, "cleanup", ())) if isinstance(exc, LocalStoreError) else ()
        cleanup = earlier + tuple(t for t in (token,) if t not in earlier)
        if ctx.published:
            if isinstance(exc, LocalStoreError) and exc.code == "store_commit_uncertain":
                raise exc.add_cleanup(token)
            raise LocalStoreError("store_commit_uncertain", "history", phase, cleanup=cleanup,
                                  primary=getattr(exc, "code", None))
        if isinstance(exc, LocalStoreError) and exc.code == "store_lock_ownership_lost" and rel == "lost":
            raise exc.add_cleanup(token)
        if rel == "lost":
            raise LocalStoreError("store_lock_ownership_lost", "lock", phase, cleanup=cleanup,
                                  primary=getattr(exc, "code", None))
        if ctx.changed:
            raise maintenance_error("maintenance_incomplete", "lock", phase, cleanup=cleanup,
                                    primary=getattr(exc, "code", None))
        raise LocalStoreError("store_io_error", "lock", phase, cleanup=cleanup, primary=getattr(exc, "code", None))

    def _exclusive_by_plan_lock(self, body):
        """An unlock whose plan names the left lock: that lock is the exclusion, no new lock is taken, and it is the last
        thing moved."""
        ctx, exc, value = _Ctx(), None, None
        try:
            value = body(ctx)
        except Exception as e:
            exc = e
        exc = _incomplete(exc, ctx)
        if exc is not None:
            raise exc
        return value

    # ==== reading ===============================================================================================
    def _names(self):
        try:
            names = self._ops.listdir(self._dir)
        except Exception:
            names = None
        if names is None:
            raise LocalStoreError("store_io_error", "root", "scan")
        return names

    def _lstat(self, path, field, phase):
        """lstat, or None when the path is absent."""
        st, code = None, None
        try:
            st = self._ops.lstat(path)
        except FileNotFoundError:
            code = "missing"
        except Exception:
            code = "io"
        if code == "io":
            raise LocalStoreError("store_io_error", field, phase)
        return st

    def _read_regular(self, path, field, phase):
        """(bytes, st) of a regular file read without following a link; None when absent; False when it is not a
        regular file or changed identity while it was read."""
        ops = self._ops
        st = self._lstat(path, field, phase)
        if st is None:
            return None
        if ops.is_link_like(st) or not stat.S_ISREG(st.st_mode):
            return False
        data = st2 = None
        code = None
        try:
            data, st2 = ops.read_file(path)
        except FileNotFoundError:
            code = "missing"
        except Exception:
            code = "io"
        if code == "io":
            raise LocalStoreError("store_io_error", field, phase)
        if code == "missing":
            return None
        if (st.st_dev, st.st_ino) != (st2.st_dev, st2.st_ino):
            return False
        return data, st2

    def _read(self, path, field, phase):
        got = self._read_regular(path, field, phase)
        if got is False:
            raise LocalStoreError("store_root_invalid", "root", phase)
        return got

    def _matches(self, path, identity, dev_ino=None):
        """The file at `path` is a regular file whose bytes (and, when given, st_dev and st_ino) are the identity."""
        got = self._read_regular(path, _QUARANTINE_FIELD, "scan")
        if got is None or got is False:
            return False
        data, st = got
        if dev_ino is not None and (st.st_dev, st.st_ino) != dev_ino:
            return False
        return raw_identity(data) == {"raw_sha256": identity["raw_sha256"], "raw_size": identity["raw_size"]}

    # ---- inspect --------------------------------------------------------------------------------------------
    def _entry(self, name, names, with_readable):
        if name not in names:
            return None
        got = self._read_regular(self._managed(name), "root", "scan")
        if got is None:
            return None
        if got is False:
            out = {"regular": False, "raw_sha256": None, "raw_size": None}
            if with_readable:
                out["readable"] = False
            return out
        data = got[0]
        out = dict(raw_identity(data), regular=True)
        if with_readable:
            readable = True
            try:
                read_history_bytes(data)
            except Exception:
                readable = False
            out["readable"] = readable
        return out

    def _artifact(self, name, kind):
        got = self._read_regular(self._managed(name), "root", "scan")
        if got is None:
            return None
        out = {"name": name, "kind": kind, "owner": None, "regular": False, "raw_sha256": None, "raw_size": None,
               "st_dev": None, "st_ino": None}
        if got is False:
            return out
        data, st = got
        out.update(raw_identity(data))
        out.update(regular=True, st_dev=st.st_dev, st_ino=st.st_ino)
        if kind == KIND_LOCK:
            out["owner"] = lock_owner(data)
        else:
            out["owner"] = "S2" if name.startswith(".snapshot.") else "C3"
        return out

    def _quarantine_report(self, names):
        report = {"state": "absent", "keys": []}
        if QUARANTINE_NAME not in names:
            return report
        qpath = self._managed(QUARANTINE_NAME)
        if not self._is_real_dir(qpath):
            report["state"] = "invalid"
            return report
        report["state"] = "dir"
        for key in sorted(n for n in self._list(qpath) if is_hex64(n)):
            kpath = os.path.join(qpath, key)
            item = {"key": key, "state": "invalid", "manifest_state": "absent", "manifest": None, "entries": []}
            if self._is_real_dir(kpath):
                entries = self._list(kpath)
                item["state"] = "dir"
                item["entries"] = sorted(entries)
                if MANIFEST_NAME in entries:
                    got = self._read_regular(os.path.join(kpath, MANIFEST_NAME), _QUARANTINE_FIELD, "scan")
                    manifest = read_manifest(got[0]) if got else None
                    item["manifest_state"] = "valid" if manifest else "invalid"
                    if manifest:
                        item["manifest"] = {"operation": manifest["operation"], "request_id": manifest["request_id"],
                                            "targets": [t["name"] for t in manifest["targets"]]}
            report["keys"].append(item)
        return report

    def _is_real_dir(self, path):
        st = self._lstat(path, _QUARANTINE_FIELD, "scan")
        return (st is not None and stat.S_ISDIR(st.st_mode) and not self._ops.is_link_like(st)
                and st.st_dev == self._dev)

    def _list(self, path):
        try:
            names = self._ops.listdir(path)
        except Exception:
            names = None
        if names is None:
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, "scan")
        return names

    # ==== quarantine ============================================================================================
    def _q_dir(self, path):
        """None when absent; the path when it is a real directory of the root's device; refusal otherwise."""
        st = self._lstat(path, _QUARANTINE_FIELD, "quarantine")
        if st is None:
            return None
        if (not stat.S_ISDIR(st.st_mode) or self._ops.is_link_like(st) or st.st_dev != self._dev):
            raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "quarantine", rule="type")
        return path

    def _q_find(self, key):
        """quarantine/<key>/ if both directories exist (read-only), else None."""
        q = self._q_dir(self._managed(QUARANTINE_NAME))
        return None if q is None else self._q_dir(os.path.join(q, key))

    def _q_make(self, key, ctx):
        """Find or create quarantine/ and quarantine/<key>/; returns (path of the key directory, existed)."""
        qpath = self._managed(QUARANTINE_NAME)
        if self._q_dir(qpath) is None:
            self._mkdir(qpath, self._dir, ctx)
        kpath = os.path.join(qpath, key)
        if self._q_dir(kpath) is None:
            self._mkdir(kpath, qpath, ctx)
            return kpath, False
        return kpath, True

    def _mkdir(self, path, parent, ctx):
        failed = False
        ctx.changed = True
        try:
            self._ops.mkdir(path)
        except Exception:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, "quarantine")
        self._sync(parent, "dir_sync")

    def _sync(self, path, phase):
        if self._durability != STRICT:
            return
        failed = False
        try:
            self._ops.fsync_dir(path)
        except Exception:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, phase)

    def _q_list(self, kpath):
        return set(self._list(kpath))

    def _q_check_names(self, entries, allowed):
        for n in entries:
            if n != MANIFEST_NAME and n not in allowed and not is_q_tmp(n):
                raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "quarantine",
                                        rule="entries")

    def _q_read_manifest(self, kpath, entries, key):
        """The valid MANIFEST of this key directory, or a refusal."""
        got = None
        if MANIFEST_NAME in entries:
            got = self._read_regular(os.path.join(kpath, MANIFEST_NAME), _QUARANTINE_FIELD, "read")
        manifest = read_manifest(got[0]) if got else None
        if manifest is None or manifest["key"] != key:
            raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "read", rule="manifest")
        return manifest

    def _q_manifest(self, kpath, entries, expected, ctx):
        """The MANIFEST must be the bytes this operation writes now: an existing one is compared byte for byte, a missing
        one is written (temporary file, fsync, one replace). Called only after the bytes read under the lock were
        checked against the publication or the plan (rule 4 of the policy)."""
        if MANIFEST_NAME in entries:
            got = self._read_regular(os.path.join(kpath, MANIFEST_NAME), _QUARANTINE_FIELD, "manifest")
            if got is None or got is False or got[0] != expected:
                raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "manifest",
                                        rule="manifest")
            return
        self._put(kpath, MANIFEST_NAME, expected, "manifest", ctx)

    def _put(self, kpath, name, data, phase, ctx):
        """data -> kpath/.q.<hex>.tmp -> fsync -> one replace to kpath/<name> -> (STRICT) fsync of kpath."""
        ops = self._ops
        target = os.path.join(kpath, name)
        tmp = os.path.join(kpath, Q_TMP_PREFIX + secrets.token_hex(16) + TMP_SUFFIX)
        ctx.changed = True
        st, failed_phase, tokens = self._fill(tmp, data)
        if failed_phase is not None:
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, phase, cleanup=tokens)
        failed = False
        try:
            ops.replace(tmp, target)
        except Exception:
            failed = True
        if failed:
            tokens = self._discard_own(tmp, st, None, None, CLEANUP_TMP_LEFT)
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, phase, cleanup=tokens)
        self._sync(kpath, phase)

    def _move(self, src, dst, identity, dev_ino, ctx, on_stale):
        """rename src -> dst, after the bytes and the inode at src are what was named and nothing is at dst."""
        if not self._matches(src, identity, dev_ino):
            raise on_stale()
        if self._lstat(dst, _QUARANTINE_FIELD, "move") is not None:
            raise maintenance_error("maintenance_quarantine_invalid", _QUARANTINE_FIELD, "move", rule="target")
        ctx.changed = True
        failed = False
        try:
            self._ops.rename(src, dst)
        except Exception:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", _QUARANTINE_FIELD, "move")

    # ==== durability and publishing (C-3) =======================================================================
    def _check_durability(self):
        ops = self._ops
        if self._durability == STRICT:
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

    def _discard_own(self, path, st, writer, fd, left_token):
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

    def _fill(self, tmp, data):
        """Create `tmp` exclusively, write, flush, fsync and close `data`. Returns (st, failed phase or None, cleanup)."""
        ops = self._ops
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
        if not failed:
            return st, None, ()
        created = st is not None or fd is not None or writer is not None or phase != "tmp_create"
        tokens = self._discard_own(tmp, st, writer, fd, CLEANUP_TMP_LEFT) if created else ()
        return st, phase, tokens

    def _publish(self, lock, ctx, data):
        """history.json from `data`: C-3's order (temporary file, fsync, ownership, one replace, directory fsync)."""
        ops = self._ops
        strict = self._durability == STRICT
        self._check_durability()
        target = self._managed(HISTORY_NAME)
        tmp = self._managed(TMP_PREFIX + secrets.token_hex(16) + TMP_SUFFIX)
        ctx.changed = True
        st, failed_phase, tokens = self._fill(tmp, data)
        if failed_phase is not None:
            raise LocalStoreError("store_io_error", "history", failed_phase, cleanup=tokens)
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
            raise LocalStoreError("store_commit_uncertain", "history", "replace", cleanup=tokens)
        if strict:
            try:
                ops.fsync_dir(self._dir)
            except Exception:
                failed = True
            if failed:
                raise LocalStoreError("store_commit_uncertain", "history", "dir_sync")

    # ==== unlock (5.1) ==========================================================================================
    def _unlock_body(self, body, plan_hash, own, ctx):
        targets = body["targets"]
        target_names = {t["name"] for t in targets}
        names = self._names()
        # 1 what is in the root now is a subset of the plan (our own lock excepted)
        for n in names:
            if (n == LOCK_NAME and own is None) or is_root_tmp(n):
                if n not in target_names:
                    raise maintenance_error("maintenance_plan_stale", "store", "scan")
        present = [t for t in targets if t["name"] in names]
        absent = [t for t in targets if t["name"] not in names]
        stale = lambda: maintenance_error("maintenance_plan_stale", "store", "scan")  # noqa: E731
        # 2 what is still in the root is what was named (inode, bytes); the lock goes last, so a missing lock with
        #   temporary files still in place is not a state this operation leaves
        for t in present:
            if not self._matches(self._managed(t["name"]), t, (t["st_dev"], t["st_ino"])):
                raise stale()
        if own is None and any(t["kind"] == KIND_LOCK for t in absent) and any(t["kind"] == KIND_TMP for t in present):
            raise stale()
        # 3 what is gone from the root was set aside by an earlier attempt, same inode and bytes
        kpath = self._q_find(plan_hash)
        for t in absent:
            if kpath is None or not self._matches(os.path.join(kpath, t["name"]), t, (t["st_dev"], t["st_ino"])):
                raise stale()
        self._check_durability()
        expected = manifest_bytes(unlock_manifest(body, plan_hash))
        kpath, existed = self._q_make(plan_hash, ctx)
        entries = self._q_list(kpath)
        self._q_check_names(entries, target_names)
        self._q_manifest(kpath, entries, expected, ctx)
        for t in targets:
            if t["name"] in names:
                self._move(self._managed(t["name"]), os.path.join(kpath, t["name"]), t,
                           (t["st_dev"], t["st_ino"]), ctx, stale)
        self._sync(kpath, "dir_sync")
        self._sync(self._dir, "dir_sync")
        return MaintenanceResult(UNLOCKED, plan_hash, existed, None, self.persistence_level)

    # ==== migrate (5.2) =========================================================================================
    def _migrate_body(self, pub, key, lock, ctx):
        names = set(self._names())
        if any(is_root_tmp(n) for n in names):
            raise LocalStoreError("store_artifact_present", "store", "scan")
        has_h, has_v = HISTORY_NAME in names, V1_NAME in names
        if has_v and not has_h:
            return self._migrate_fresh(pub, key, lock, ctx)
        if not has_v and not has_h:
            raise maintenance_error("maintenance_state_unexpected", "store", "scan", rule="empty")
        return self._migrate_resume(pub, key, has_v, ctx)

    def _migrate_fresh(self, pub, key, lock, ctx):
        v1 = self._read(self._managed(V1_NAME), "snapshot", "read")
        if v1 is None:
            raise maintenance_error("maintenance_state_unexpected", "store", "scan", rule="v1_and_v2")
        candidate = _checked(None, pub, v1[0])                      # the bytes read under the lock, checked first
        info = self._info(pub)
        self._check_durability()
        kpath, existed = self._q_make(key, ctx)
        entries = self._q_list(kpath)
        self._q_check_names(entries, {V1_NAME})
        self._q_manifest(kpath, entries, self._manifest_for(info, OP_MIGRATION), ctx)
        self._publish(lock, ctx, history_bytes(candidate))
        self._set_aside_v1(kpath, info, ctx)
        return MaintenanceResult(MIGRATED, key, existed, candidate, self.persistence_level)

    def _migrate_resume(self, pub, key, has_v, ctx):
        """history.json is there: finish the rename (both files), or recognise a completed migration (v2 only)."""
        rule = "v1_and_v2" if has_v else "v2_present"
        unexpected = maintenance_error("maintenance_state_unexpected", "store", "scan", rule=rule)
        got = self._read(self._managed(HISTORY_NAME), "history", "read")
        if got is None:                                   # history.json is not there under the lock (it was seen in the listing)
            raise unexpected
        outcome = reconcile_publication(got[0], pub).outcome
        wanted = (PUBLISHED,) if has_v else (PUBLISHED, PUBLISHED_THEN_EXTENDED)
        if outcome not in wanted:
            raise unexpected
        info = self._info(pub)
        kpath = self._q_find(key)
        if kpath is None:
            raise unexpected
        entries = self._q_list(kpath)
        self._q_check_names(entries, {V1_NAME})
        if MANIFEST_NAME not in entries:
            raise unexpected
        self._q_manifest(kpath, entries, self._manifest_for(info, OP_MIGRATION), ctx)
        if has_v:
            if not self._matches(self._managed(V1_NAME), info["identity"]):
                raise unexpected
            self._check_durability()
            self._set_aside_v1(kpath, info, ctx)
        else:
            if not self._matches(os.path.join(kpath, V1_NAME), info["identity"]):
                raise unexpected
        again = self._read(self._managed(HISTORY_NAME), "history", "read")
        if again is None:                                 # gone after the check: the migration is not shown to be complete
            raise maintenance_error("maintenance_state_unexpected", "store", "scan", rule="v2_present")
        history = read_history_bytes(again[0])[0]
        return MaintenanceResult(MIGRATED, key, True, history, self.persistence_level)

    def _set_aside_v1(self, kpath, info, ctx):
        unexpected = lambda: maintenance_error("maintenance_state_unexpected", "store", "move",   # noqa: E731
                                               rule="v1_and_v2")
        self._move(self._managed(V1_NAME), os.path.join(kpath, V1_NAME), info["identity"], None, ctx, unexpected)
        self._sync(kpath, "dir_sync")
        self._sync(self._dir, "dir_sync")

    # ==== adopt (5.3) ===========================================================================================
    def _adopt_body(self, pub, key, lock, ctx):
        names = set(self._names())
        if V1_NAME in names:
            raise LocalStoreError("store_layout_unsupported", "store", "scan",
                                  rule="v1_and_v2" if HISTORY_NAME in names else "v1_only")
        if any(is_root_tmp(n) for n in names):
            raise LocalStoreError("store_artifact_present", "store", "scan")
        got = self._read(self._managed(HISTORY_NAME), "history", "read")
        if got is None:
            raise LocalStoreError("store_uninitialized", "store", "read")
        data = got[0]
        refusal, candidate = None, None
        try:
            candidate = _checked(data, pub)
        except CoreError as e:
            refusal = e
        if refusal is not None:
            history = self._adopt_completed(pub, key, data) if self._raw_stale(refusal) else None
            if history is None:
                raise refusal
            return MaintenanceResult(ADOPTED, key, True, history, self.persistence_level)
        info = self._info(pub)
        self._check_durability()
        kpath, existed = self._q_make(key, ctx)
        entries = self._q_list(kpath)
        self._q_check_names(entries, {HISTORY_NAME})
        self._q_manifest(kpath, entries, self._manifest_for(info, OP_ADOPTION), ctx)
        if HISTORY_NAME not in entries:
            self._put(kpath, HISTORY_NAME, data, "copy", ctx)
        if not self._matches(os.path.join(kpath, HISTORY_NAME), info["identity"]):    # the copy, read back
            raise maintenance_error("maintenance_copy_mismatch", _QUARANTINE_FIELD, "copy")
        self._publish(lock, ctx, history_bytes(candidate))
        return MaintenanceResult(ADOPTED, key, existed, candidate, self.persistence_level)

    @staticmethod
    def _raw_stale(error):
        return error.code == "publication_stale" and getattr(error, "rule", None) == "raw"

    def _adopt_completed(self, pub, key, data):
        """The History held now when history.json is the candidate (or the candidate and more) and the set-aside copy of
        the original is in place; None when this is not a finished adoption of this publication."""
        outcome = reconcile_publication(data, pub).outcome
        if outcome not in (PUBLISHED, PUBLISHED_THEN_EXTENDED):
            return None
        info = self._info(pub)
        refused = False
        try:
            kpath = self._q_find(key)
            entries = self._q_list(kpath) if kpath is not None else set()
            self._q_check_names(entries, {HISTORY_NAME})
            done = (kpath is not None and MANIFEST_NAME in entries and HISTORY_NAME in entries
                    and self._q_manifest_equal(kpath, self._manifest_for(info, OP_ADOPTION))
                    and self._matches(os.path.join(kpath, HISTORY_NAME), info["identity"]))
        except LocalStoreError:
            refused = True
        if refused or not done:
            return None
        return read_history_bytes(data)[0]

    def _q_manifest_equal(self, kpath, expected):
        got = self._read_regular(os.path.join(kpath, MANIFEST_NAME), _QUARANTINE_FIELD, "manifest")
        return bool(got) and got[0] == expected

    # ==== what a publication says about itself (after check_publication / reconcile_publication validated it) =====
    @staticmethod
    def _info(pub):
        view = pub.to_dict()
        body = view["body"]
        identity = body["source_v1"] if body["source"] == MIGRATION else body["expected"]
        return {"key": view["publication_hash"], "request_id": body["request_id"], "plan_hash": body["plan_hash"],
                "identity": {"raw_sha256": identity["raw_sha256"], "raw_size": identity["raw_size"]}}

    @staticmethod
    def _manifest_for(info, operation):
        kind, name = ("v1", V1_NAME) if operation == OP_MIGRATION else ("history", HISTORY_NAME)
        target = dict(info["identity"], name=name, kind=kind)
        return manifest_bytes(manifest_dict(operation, info["key"], info["request_id"], info["plan_hash"],
                                            info["key"], operation == OP_MIGRATION, [target]))
