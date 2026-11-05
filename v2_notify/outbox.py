"""A local outbox in one explicit, already existing directory: the record of "this notice may be sent" (the claim) and of
"this is how the send ended" (the result), for the send right of S4-B.

A claim and a result are only ever created, with O_EXCL, through the unchanged S2 FileOps: nothing is replaced, renamed
or deleted, so the first creator of a name is the only one that has the right. Order of one write: create_exclusive ->
every byte -> flush -> fsync_file -> close -> fsync_dir. Reading never creates or changes a file.

durability (the same two words as the C-3 history store): "strict" (the default) ends each write with the directory sync
above; "file_sync_only" writes the same bytes in the same steps and skips only the directory sync, for a host that cannot
sync a directory (Windows). As in C-3, "strict" is checked when the outbox is made and before anything is written: on
Windows, or when one directory sync of the root fails, the outbox is refused (outbox_durability_unsupported) instead of
failing later at every claim. A directory sync that fails during a write in strict mode is still an outbox_io_error.

Names: <d>-<kind>.claim.json / .result.json and, for a manual resend, <d>-<kind>.resend-<id>.claim.json / .result.json.
Nothing else is read or created. A claim without a result reads as UNKNOWN (it may have been sent); anything that does
not read back as a claim or result of exactly this shape reads as DAMAGED, and neither is sent again."""
import json
import os
import secrets
import stat

from v2_core.errors import CoreError
from v2_persistence.local.fsops import FileOps
from v2_persistence.local.store import FILE_SYNC_ONLY_MODE, STRICT

from .values import (ARGS_INVALID, CLAIM_SCHEMA, DAMAGED, KINDS, NONE, OUTBOX_DURABILITY_UNSUPPORTED, OUTBOX_IO_ERROR,
                     OUTBOX_ROOT_INVALID, RESULT_STATUSES, UNKNOWN, NotifyError, OutboxEntry, date_text, hex32,
                     request_id_text, sha256_text)

_CLAIM_KEYS = frozenset(("schema", "kind", "d", "claim_id", "text", "text_sha256", "run_outcome", "code", "claimed_at",
                         "resend_of"))
_RESULT_KEYS = frozenset(("claim_id", "status", "recorded_at"))
_ABSENT, _BAD, _OK = "absent", "bad", "ok"
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
_IO_ERRORS = (OSError, CoreError, ValueError)
_MODES = (STRICT, FILE_SYNC_ONLY_MODE)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _optional_text(value):
    return value is None or isinstance(value, str)


def _text_hash_matches(text, digest):
    try:
        return sha256_text(text) == digest
    except UnicodeError:
        return False


def _claim_is_valid(obj, d, kind, resend_request_id):
    if type(obj) is not dict or set(obj) != _CLAIM_KEYS:
        return False
    resend_of = obj["resend_of"]
    return (obj["schema"] == CLAIM_SCHEMA and obj["kind"] == kind and obj["d"] == d and hex32(obj["claim_id"])
            and isinstance(obj["text"], str) and isinstance(obj["text_sha256"], str)
            and _text_hash_matches(obj["text"], obj["text_sha256"])
            and _optional_text(obj["run_outcome"]) and _optional_text(obj["code"])
            and isinstance(obj["claimed_at"], str)
            and (resend_of is None) == (resend_request_id is None) and (resend_of is None or hex32(resend_of)))


def _result_is_valid(obj, claim):
    return (type(obj) is dict and set(obj) == _RESULT_KEYS and obj["claim_id"] == claim["claim_id"]
            and obj["status"] in RESULT_STATUSES and isinstance(obj["recorded_at"], str))


class LocalOutbox(object):
    """root: an absolute path of an existing directory that is not a link (it is never created). _ops: the S2 FileOps
    (a test may pass a subclass that records or fails). durability: "strict" (default) or "file_sync_only". The repr
    never shows the path."""

    def __init__(self, root, durability=STRICT, *, _ops=None):
        if type(durability) is not str or durability not in _MODES:
            raise NotifyError(ARGS_INVALID, "durability")
        ops = FileOps() if _ops is None else _ops
        valid = False
        if isinstance(root, str) and root and os.path.isabs(root):
            try:
                st = ops.lstat(root)
            except _IO_ERRORS:
                st = None
            if st is not None:
                link = stat.S_ISLNK(st.st_mode) or bool(_REPARSE and getattr(st, "st_file_attributes", 0) & _REPARSE)
                valid = stat.S_ISDIR(st.st_mode) and not link
        if not valid:
            raise NotifyError(OUTBOX_ROOT_INVALID, "root")
        if durability == STRICT:                # as in C-3: refuse before anything is written
            if ops.is_windows():
                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, "durability")
            supported = True
            try:
                ops.probe_dir_sync(root)
            except _IO_ERRORS:
                supported = False
            if not supported:
                raise NotifyError(OUTBOX_DURABILITY_UNSUPPORTED, "durability")
        self._root, self._ops, self._durability = root, ops, durability

    def __repr__(self):
        return "LocalOutbox()"

    # --- names -----------------------------------------------------------------------------------------------------
    @staticmethod
    def _check(d, kind, resend_request_id=None):
        if date_text(d) is None:
            raise NotifyError(ARGS_INVALID, "d")
        if kind not in KINDS:
            raise NotifyError(ARGS_INVALID, "kind")
        if resend_request_id is not None and request_id_text(resend_request_id) is None:
            raise NotifyError(ARGS_INVALID, "resend_request_id")

    @staticmethod
    def _base(d, kind, resend_request_id=None):
        return "%s-%s" % (d, kind) + ("" if resend_request_id is None else ".resend-%s" % resend_request_id)

    # --- reading (never creates or changes a file) ---------------------------------------------------------------------
    def _read(self, name):
        try:
            data, _st = self._ops.read_file(os.path.join(self._root, name))
        except FileNotFoundError:
            return _ABSENT, None
        except _IO_ERRORS:
            return _BAD, None
        try:
            return _OK, json.loads(data.decode("utf-8"))
        except Exception:                       # not UTF-8, not JSON, or too deep: a damaged file
            return _BAD, None

    def load(self, d, kind, resend_request_id=None):
        """(OutboxEntry, claim object) of one key (the original, or one resend of it). The claim object is the parsed
        claim only when the entry has a claim_id (the claim read back as a valid claim)."""
        self._check(d, kind, resend_request_id)
        base = self._base(d, kind, resend_request_id)
        how, claim = self._read(base + ".claim.json")
        if how == _ABSENT:
            how_result, _ = self._read(base + ".result.json")        # a result without a claim is not a clean key
            return OutboxEntry(kind, d, resend_request_id, NONE if how_result == _ABSENT else DAMAGED), None
        if how == _BAD or not _claim_is_valid(claim, d, kind, resend_request_id):
            return OutboxEntry(kind, d, resend_request_id, DAMAGED), None
        known = dict(claim_id=claim["claim_id"], claimed_at=claim["claimed_at"], text_sha256=claim["text_sha256"])
        how, result = self._read(base + ".result.json")
        if how == _ABSENT:
            return OutboxEntry(kind, d, resend_request_id, UNKNOWN, **known), claim     # a claim without a result
        if how == _BAD or not _result_is_valid(result, claim):
            return OutboxEntry(kind, d, resend_request_id, DAMAGED, **known), claim
        return OutboxEntry(kind, d, resend_request_id, result["status"], recorded_at=result["recorded_at"],
                           **known), claim

    def status(self, d, kind, resend_request_id=None):
        """The OutboxEntry of one key."""
        return self.load(d, kind, resend_request_id)[0]

    def resend_ids(self, d, kind):
        """The resend_request_ids that have a claim or a result file for this key, sorted."""
        self._check(d, kind)
        prefix, ids, failed = self._base(d, kind) + ".resend-", set(), False
        try:
            names = list(self._ops.listdir(self._root))
        except _IO_ERRORS:
            names, failed = (), True
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        for name in names:
            if not isinstance(name, str) or not name.startswith(prefix):
                continue
            for suffix in (".claim.json", ".result.json"):
                if name.endswith(suffix) and request_id_text(name[len(prefix):-len(suffix)]) is not None:
                    ids.add(name[len(prefix):-len(suffix)])
        return sorted(ids)

    # --- creating (never replaces) ------------------------------------------------------------------------------------
    def _create(self, name, obj):
        """True when this call created the file with all its bytes; False when something was already at the name.
        Another failure is raised as NotifyError(outbox_io_error) after the handlers (no __context__ is kept)."""
        data, ops = _canonical(obj), self._ops
        path = os.path.join(self._root, name)
        exists = failed = False
        fd = writer = None
        try:
            fd = ops.create_exclusive(path)
        except FileExistsError:
            exists = True                       # the name is taken: this call does not hold the right
        except _IO_ERRORS:
            failed = True
        if exists:
            return False
        if not failed:
            try:
                writer = ops.open_writer(fd)
                fd = None                       # the writer owns the descriptor now
                view = data
                while len(view):
                    n = ops.write(writer, view)
                    if type(n) is not int or n <= 0 or n > len(view):
                        raise OSError("short or invalid write")
                    view = view[n:]
                ops.flush(writer)
                ops.fsync_file(writer)
                ops.close(writer)
                writer = None                   # closed; the clean-up below closes it again only if close failed
                if self._durability == STRICT:
                    ops.fsync_dir(self._root)
            except _IO_ERRORS:
                failed = True
            finally:
                for closer, handle in ((ops.close, writer), (ops.close_fd, fd)):
                    if handle is not None:
                        try:
                            closer(handle)
                        except _IO_ERRORS:
                            pass
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        return True

    def claim(self, notice, now, resend_request_id=None, resend_of=None):
        """Create the claim of a notice. Returns its claim_id, or None when the claim already exists (this call does
        not hold the right). Raises NotifyError(outbox_io_error) when the file could not be created."""
        self._check(notice.d, notice.kind, resend_request_id)
        claim_id = secrets.token_hex(16)
        body = {"schema": CLAIM_SCHEMA, "kind": notice.kind, "d": notice.d, "claim_id": claim_id, "text": notice.text,
                "text_sha256": notice.text_sha256, "run_outcome": notice.run_outcome, "code": notice.code,
                "claimed_at": now.isoformat(), "resend_of": resend_of}
        created = self._create(self._base(notice.d, notice.kind, resend_request_id) + ".claim.json", body)
        return claim_id if created else None

    def record(self, d, kind, claim_id, status, now, resend_request_id=None):
        """Create the result of a claim. True when created, False when a result already exists."""
        self._check(d, kind, resend_request_id)
        if status not in RESULT_STATUSES:
            raise NotifyError(ARGS_INVALID, "status")
        return self._create(self._base(d, kind, resend_request_id) + ".result.json",
                            {"claim_id": claim_id, "status": status, "recorded_at": now.isoformat()})
