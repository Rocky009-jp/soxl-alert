"""GitOutbox: the S4-B LocalOutbox kept on one ref (refs/heads/<ref>) of a git remote. The remote is the record: a claim or a
result is a file that is added by one fast-forward commit, and the right to a name is decided by the push of that commit
(the first to add a name wins; a second commit that would add it is refused by the remote, or is not made because the name
is already in the tree it would build on).

It is a subclass of LocalOutbox so that morning_job, resend and outbox_status (which check the type) work unchanged. The
base class works on a local mirror directory that is made here, inside `parent`, and rebuilt from the remote before every
use; only the public methods load, resend_ids, claim and record (and __init__, __repr__) are overridden, and no private
name of the base class is used. The mirror is never the record: a name that the mirror has but the remote does not is
never sent, and what the remote already has is never replaced.

load never raises for a failure of git: it reads as DAMAGED, so nothing is sent. A claim or a result is tried at most four
times (right away, no waiting); a refusal by a rule or hook (the head did not move) is not repeated."""
import os
import shutil
import stat
import tempfile

from v2_notify import DAMAGED, KINDS, LocalOutbox, NotifyError, OutboxEntry
from v2_notify.values import ARGS_INVALID, OUTBOX_IO_ERROR, date_text, request_id_text

from .git import (ARGS_INVALID as GIT_ARGS_INVALID, FAILED, OK, REJECTED, REGULAR_MODES, Git, GitError, check_clock,
                  check_ref, is_absolute_dir, valid_name)

MARKER_NAME = "v2-outbox-init"
MARKER_BYTES = b"v2-outbox\n"
ALREADY_INITIALIZED = "already_initialized"
TRIES = 4
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)


def _unlinked_dir(path):
    """GitError unless `path` is an absolute, existing directory that is not a link."""
    if not is_absolute_dir(path):
        raise GitError(GIT_ARGS_INVALID, "parent")
    st = os.lstat(path)
    link = stat.S_ISLNK(st.st_mode) or bool(_REPARSE and getattr(st, "st_file_attributes", 0) & _REPARSE)
    if link or not stat.S_ISDIR(st.st_mode):
        raise GitError(GIT_ARGS_INVALID, "parent")


def _check_key(d, kind, resend_request_id):
    if date_text(d) is None:
        raise NotifyError(ARGS_INVALID, "d")
    if kind not in KINDS:
        raise NotifyError(ARGS_INVALID, "kind")
    if resend_request_id is not None and request_id_text(resend_request_id) is None:
        raise NotifyError(ARGS_INVALID, "resend_request_id")


def _slurp(path):
    with open(path, "rb") as f:
        return f.read()


class GitOutbox(LocalOutbox):
    """git: a Git. ref: the name of the ref. parent: an absolute path of an existing directory (not a link) in which the
    mirror directory is made (and only there). clock: returns the time (with a time zone) of a new commit. _ops: for the
    tests, passed to the base class (the S2 FileOps used on the mirror)."""

    def __init__(self, git, ref, parent, clock, *, _ops=None):
        if not isinstance(git, Git):
            raise GitError(GIT_ARGS_INVALID, "git")
        check_ref(ref)
        check_clock(clock)
        _unlinked_dir(parent)
        mirror, made = None, False
        try:
            mirror = tempfile.mkdtemp(prefix="v2gitoutbox_", dir=parent)
            made = True
        except OSError:
            made = False
        if not made:
            raise GitError(FAILED, "mirror")
        refused = None
        try:
            super().__init__(mirror, "file_sync_only", _ops=_ops)
        except NotifyError as e:
            refused = e
        if refused is not None:
            shutil.rmtree(mirror, True)             # the mirror is ours and holds nothing yet
            raise refused
        self._git, self._ref, self._mirror, self._clock = git, ref, mirror, clock

    def __repr__(self):
        return "GitOutbox()"

    # --- the mirror ---------------------------------------------------------------------------------------------------------
    def _rebuild(self):
        """Fetch the ref and make the mirror the same files as its tree. Returns the head SHA. A failure of git or of the
        mirror, a ref that does not exist, or an entry that is not a plain file with a plain name is NotifyError
        (outbox_io_error): nothing is skipped."""
        head, files, failed = None, {}, False
        try:
            head = self._git.fetch(self._ref)
            if head is not None:
                for name, (mode, kind, sha) in self._git.tree(head).items():
                    if kind != "blob" or mode not in REGULAR_MODES or not valid_name(name):
                        raise GitError(FAILED, "tree")
                    files[name] = self._git.blob_of(sha)
                for name in os.listdir(self._mirror):
                    os.unlink(os.path.join(self._mirror, name))
                for name, data in files.items():
                    with open(os.path.join(self._mirror, name), "xb") as f:
                        f.write(data)
        except (GitError, OSError):
            failed = True
        if failed or head is None:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        return head

    # --- reading --------------------------------------------------------------------------------------------------------
    def load(self, d, kind, resend_request_id=None):
        _check_key(d, kind, resend_request_id)
        failed = False
        try:
            self._rebuild()
        except NotifyError:
            failed = True
        if failed:                                  # the job reads the state without a handler: never raise, never send
            return OutboxEntry(kind, d, resend_request_id, DAMAGED), None
        return super().load(d, kind, resend_request_id)

    def resend_ids(self, d, kind):
        _check_key(d, kind, None)
        self._rebuild()
        return super().resend_ids(d, kind)

    # --- creating (decided by the push of a commit that adds exactly that file) --------------------------------------------
    def _decide(self, make, absent):
        """make() creates one file in the mirror through the base class and returns its value (a claim_id, or True), or
        `absent` (None / False) when the name was already in the mirror. Returns the value only when this call added the
        file to the remote ref; `absent` when somebody else has that name."""
        for _attempt in range(TRIES):
            head = self._rebuild()
            before = set(os.listdir(self._mirror))
            value = make()
            if not value:
                return absent                       # the name is taken: this call does not hold the right
            added = set(os.listdir(self._mirror)) - before
            if len(added) != 1:
                raise NotifyError(OUTBOX_IO_ERROR, "outbox")
            name = added.pop()
            data = _slurp(os.path.join(self._mirror, name))
            when = self._clock()
            how, commit, failed = None, None, False
            try:
                commit = self._git.commit_with(head, name, data, "v2 outbox " + name, when, replace=False)
                if commit is not None:
                    how = self._git.push(commit, self._ref)
            except GitError:
                failed = True
            if commit is None and not failed:       # the remote has the name although the mirror had not: not ours
                return absent
            if how == OK:
                return value
            now_head = self._rebuild()              # refused or uncertain: what does the remote say now?
            path = os.path.join(self._mirror, name)
            if os.path.exists(path):
                return value if _slurp(path) == data else absent
            if how == REJECTED and now_head == head:    # not there and the ref did not move: a rule or hook refused it
                raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        raise NotifyError(OUTBOX_IO_ERROR, "outbox")

    def claim(self, notice, now, resend_request_id=None, resend_of=None):
        _check_key(notice.d, notice.kind, resend_request_id)
        return self._decide(lambda: LocalOutbox.claim(self, notice, now, resend_request_id, resend_of), None)

    def record(self, d, kind, claim_id, status, now, resend_request_id=None):
        _check_key(d, kind, resend_request_id)
        return self._decide(lambda: LocalOutbox.record(self, d, kind, claim_id, status, now, resend_request_id), False)

    # --- the first commit ---------------------------------------------------------------------------------------------------
    def initialize(self):
        """Create the ref with one commit that holds only a marker file. A ref that exists is refused
        (NotifyError already_initialized); an outbox without its ref is never read as an empty outbox (load reads DAMAGED,
        claim and record raise NotifyError), so this is explicit."""
        head, failed = None, False
        try:
            head = self._git.fetch(self._ref)
        except GitError:
            failed = True
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        if head is not None:
            raise NotifyError(ALREADY_INITIALIZED, "outbox")
        when = self._clock()
        how, commit = None, None
        try:
            commit = self._git.commit_with(None, MARKER_NAME, MARKER_BYTES, "v2 outbox init", when, replace=False)
            how = self._git.push(commit, self._ref)
        except GitError:
            failed = True
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        if how == OK:
            return None
        now_head = self._probe_head()               # refused or uncertain: does the ref exist now?
        if how == REJECTED and now_head is not None:
            raise NotifyError(ALREADY_INITIALIZED, "outbox")
        if how != REJECTED and now_head is not None and self._marker_is_there(now_head):
            return None
        raise NotifyError(OUTBOX_IO_ERROR, "outbox")

    def _probe_head(self):
        head, failed = None, False
        try:
            head = self._git.fetch(self._ref)
        except GitError:
            failed = True
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        return head

    def _marker_is_there(self, head):
        data, failed = None, False
        try:
            data = self._git.blob(head, MARKER_NAME)
        except GitError:
            failed = True
        if failed:
            raise NotifyError(OUTBOX_IO_ERROR, "outbox")
        return data == MARKER_BYTES
