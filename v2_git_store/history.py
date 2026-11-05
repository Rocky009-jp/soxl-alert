"""GitHistoryStore: the schema-2 history kept as one file, history.json, on one ref (refs/heads/<ref>) of a git remote,
with the read / publish / reconcile / initialize of the C-3 store (HistoryFileStore) and the same results and codes.

Compare and swap is the check of the unchanged C-2 check_publication on the bytes fetched just now, and then a
fast-forward push of one commit whose parent is the fetched head. Nothing is forced, retried or remembered: after an
uncertain push, `reconcile` fetches again and judges by content only (reconcile_publication); it knows nothing about what
this process pushed. A push that the remote refused is read by what the ref did after the refusal: the head moved since it
was read (another run saved first) -> publication_stale, the head did not move (a rule, a hook, a permission) -> store_io_error.
Only the codes of the C-3 store are used. The output of git is not kept anywhere (git.py)."""
from v2_core.errors import CoreError
from v2_history_local import INITIALIZED, PUBLISHED, HistoryStoreResult
from v2_history_publish import (APPEND, CREATE, GENESIS, HistoryPublication, check_publication, history_bytes,
                                read_history_bytes, reconcile_publication)
from v2_persistence.local.errors import LocalStoreError

from .git import ARGS_INVALID, OK, REJECTED, Git, GitError, check_clock, check_ref

NAME = "history.json"
PERSISTENCE_LEVEL = "git_remote_ref"
_PUBLICATION_CODES = ("publication_invalid", "publication_stale")


def _publication(value):
    """The value itself, before git is touched: only the exact class is taken (as in C-3)."""
    if type(value) is not HistoryPublication:
        raise LocalStoreError("store_publication_invalid", "publication", "args", rule="type")
    return value


def _kind(publication):
    """(mode, source) of a publication, read so that no exception can leave (a hand-made value without them is a form error)."""
    mode = source = None
    try:
        mode, source = publication.mode, publication.source
    except Exception:
        mode = None
    if mode is None:
        raise LocalStoreError("store_publication_invalid", "publication", "args", rule="shape")
    return mode, source


def _checked(current, publication):
    """check_publication on the bytes fetched just now: its refusals for the publication and the current state pass
    through (P-01 of the C-2 review); any other error is about the candidate the value carries."""
    refusal = None
    try:
        return check_publication(current, publication)
    except CoreError as e:
        if e.code in _PUBLICATION_CODES:
            refusal = e
    if refusal is not None:
        raise refusal
    raise LocalStoreError("store_candidate_invalid", "publication", "candidate")


class GitHistoryStore(object):
    """git: a Git. ref: the name of the ref that holds history.json (and nothing else is changed on it). clock: a callable
    that returns the time (with a time zone) of a new commit."""

    def __init__(self, git, ref, clock):
        if not isinstance(git, Git):
            raise GitError(ARGS_INVALID, "git")
        self._git, self._ref, self._clock = git, check_ref(ref), check_clock(clock)

    def __repr__(self):
        return "GitHistoryStore()"

    persistence_level = property(lambda self: PERSISTENCE_LEVEL)

    # --- the remote ---------------------------------------------------------------------------------------------------------
    def _head(self):
        """The head SHA of the ref (None when the remote has no such ref). A failure of git is store_io_error."""
        head, failed = None, False
        try:
            head = self._git.fetch(self._ref)
        except GitError:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", "history", "read")
        return head

    def _bytes(self, head):
        """The bytes of history.json at the head (None for no head). A ref without history.json is a layout we do not know."""
        if head is None:
            return None
        data, failed = None, False
        try:
            data = self._git.blob(head, NAME)
        except GitError:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", "history", "read")
        if data is None:
            raise LocalStoreError("store_layout_unsupported", "history", "read")
        return data

    def _push(self, parent, candidate, publication_hash):
        """Make the commit (parent = the head that was read) and push it. Returns OK / REJECTED / UNCERTAIN; a git failure
        before the push is store_io_error (nothing was sent)."""
        how, failed = None, False
        try:
            commit = self._git.commit_with(parent, NAME, history_bytes(candidate), "v2 history " + publication_hash[:12],
                                           self._clock())
        except GitError:
            commit, failed = None, True
        if failed:
            raise LocalStoreError("store_io_error", "history", "replace")
        try:
            how = self._git.push(commit, self._ref)
        except GitError:
            failed = True
        if failed:
            raise LocalStoreError("store_io_error", "history", "replace")
        return how

    # --- the store ----------------------------------------------------------------------------------------------------
    def read(self):
        """The validated History at the head of the ref."""
        head = self._head()
        if head is None:
            raise LocalStoreError("store_uninitialized", "store", "read")
        history, _check = read_history_bytes(self._bytes(head))
        return history

    def initialize(self, publication):
        """Only the CREATE publication of a GENESIS (publish_genesis), onto a ref that does not exist."""
        pub = _publication(publication)
        mode, source = _kind(pub)
        if mode != CREATE or source != GENESIS:
            raise LocalStoreError("store_operation_unsupported", "publication", "args", rule="not_genesis")
        if self._head() is not None:
            raise LocalStoreError("already_initialized", "store", "read")
        candidate = _checked(None, pub)
        how = self._push(None, candidate, pub.publication_hash)
        if how == OK:
            return HistoryStoreResult(INITIALIZED, True, candidate, PERSISTENCE_LEVEL, pub.publication_hash)
        if how == REJECTED:                         # created by someone else in the meantime, or refused by a rule
            if self._head() is not None:
                raise LocalStoreError("already_initialized", "store", "read")
            raise LocalStoreError("store_io_error", "history", "replace")
        raise LocalStoreError("store_commit_uncertain", "history", "replace")

    def publish(self, publication):
        """Only an APPEND publication (DAILY, RESOLUTION, RESTART, RESTORE)."""
        pub = _publication(publication)
        mode, _source = _kind(pub)
        if mode != APPEND:
            raise LocalStoreError("store_operation_unsupported", "publication", "args", rule="not_append")
        head = self._head()
        if head is None:
            raise LocalStoreError("store_uninitialized", "store", "read")
        current = self._bytes(head)
        read_history_bytes(current)                 # a broken current file is reported as it is, first
        candidate = _checked(current, pub)
        how = self._push(head, candidate, pub.publication_hash)
        if how == OK:
            return HistoryStoreResult(PUBLISHED, True, candidate, PERSISTENCE_LEVEL, pub.publication_hash)
        if how == REJECTED:
            moved = self._head() != head            # a failed fetch here is store_io_error
            if moved:
                raise LocalStoreError("publication_stale", "history", "cas")
            raise LocalStoreError("store_io_error", "history", "replace")
        raise LocalStoreError("store_commit_uncertain", "history", "replace")

    def reconcile(self, publication):
        """After store_commit_uncertain: fetch again and return C-2's Reconciliation of the bytes now on the ref (read-only;
        by content only, no memory of what was pushed)."""
        pub = _publication(publication)
        return reconcile_publication(self._bytes(self._head()), pub)
