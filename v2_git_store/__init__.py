"""V2 S4-C, the git store: the history (v2-state) and the notification outbox (v2-outbox) kept on refs of a git remote.
Three parts: Git (the only place that runs git; commits are made with plumbing commands, the remote is changed by
fast-forward pushes only, never forced), GitHistoryStore (the read / publish / reconcile / initialize of the C-3 store,
over a ref) and GitOutbox (the S4-B LocalOutbox over a local mirror of a ref, where a claim or a result is decided by the
push of a commit that adds exactly that file). The tests use local bare repositories only: no network remote, no GitHub,
no credential, no entry script, no workflow, no clock (the time is passed in). Draft, not adopted for production."""
from .git import OK, REJECTED, UNCERTAIN, Git, GitError
from .history import GitHistoryStore
from .outbox import GitOutbox

__all__ = ["Git", "GitError", "GitHistoryStore", "GitOutbox", "OK", "REJECTED", "UNCERTAIN"]
