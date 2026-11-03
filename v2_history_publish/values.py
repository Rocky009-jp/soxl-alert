"""HistoryPublication and Reconciliation: immutable, text-backed values (the _Frozen pattern of v2_history_ops)."""
import copy

from v2_history.common import is_date, is_hex64, is_int
from v2_history_ops.values import _Frozen, digest_of
from v2_recovery.common import valid_request_id

from .errors import publication_invalid

OPERATION = "soxl-v2-history-publication/1"
APPEND, CREATE, REPLACE = "APPEND", "CREATE", "REPLACE"
DAILY, RESOLUTION, RESTART, RESTORE = "DAILY", "RESOLUTION", "RESTART", "RESTORE"
GENESIS, MIGRATION, ADOPTION = "GENESIS", "MIGRATION", "ADOPTION"
MODE_OF = {DAILY: APPEND, RESOLUTION: APPEND, RESTART: APPEND, RESTORE: APPEND, GENESIS: CREATE, MIGRATION: CREATE,
           ADOPTION: REPLACE}
PUBLISHED, PUBLISHED_THEN_EXTENDED = "PUBLISHED", "PUBLISHED_THEN_EXTENDED"
NOT_PUBLISHED, CONFLICT = "NOT_PUBLISHED", "CONFLICT"
OUTCOMES = (PUBLISHED, PUBLISHED_THEN_EXTENDED, NOT_PUBLISHED, CONFLICT)
BODY_KEYS = frozenset([
    "operation", "mode", "source", "d", "request_id", "plan_hash", "expected", "source_v1", "records",
    "candidate_history", "candidate_head_seq", "candidate_head_hash", "candidate_digest", "candidate_state_digest"])
APPEND_EXPECTED_KEYS = frozenset(["head_seq", "head_hash", "history_digest"])
RAW_KEYS = frozenset(["raw_sha256", "raw_size"])


def _error(rule):
    return publication_invalid(rule)


class HistoryPublication(_Frozen):
    """An immutable {body, publication_hash}. Made only by the publish_* builders (build.py): there is no from_dict, so a
    value read back from a message or a file is never a publication. committed is always False."""

    __slots__ = ()

    @classmethod
    def _make(cls, body):
        return cls._wrap({"body": body, "publication_hash": digest_of(body)}, _error)

    @property
    def body(self):
        return copy.deepcopy(self._view["body"])

    @property
    def publication_hash(self):
        return copy.deepcopy(self._view["publication_hash"])

    @property
    def mode(self):
        return copy.deepcopy(self._view["body"]["mode"])

    @property
    def source(self):
        return copy.deepcopy(self._view["body"]["source"])

    @property
    def committed(self):
        return False

    def _display(self):
        try:
            b, h = self._view["body"], self._view["publication_hash"]
            if type(b["source"]) is not str or b["source"] not in MODE_OF or b["mode"] != MODE_OF[b["source"]] \
                    or not is_hex64(h):
                return None
            if not is_int(b["candidate_head_seq"]) or not is_hex64(b["candidate_digest"]):
                return None
            d = b["d"] if b["d"] is not None and is_date(b["d"]) else None
            rid = b["request_id"] if b["request_id"] is not None and valid_request_id(b["request_id"]) else None
            n = len(b["records"]) if isinstance(b["records"], list) else None
            return b["mode"], b["source"], d, rid, n, b["candidate_head_seq"], h
        except (KeyError, TypeError):
            return None

    def summary(self):
        """Whitelist only: mode, source, day, request id, record count, candidate head and the hash."""
        shown = self._display()
        if shown is None:
            raise publication_invalid("shape")
        mode, source, d, rid, n, head, h = shown
        return {"mode": mode, "source": source, "d": d, "request_id": rid, "records": n,
                "candidate_head_seq": head, "committed": False, "publication_hash": h}

    def __repr__(self):
        shown = self._display()
        if shown is None:
            return "HistoryPublication(?)"
        return "HistoryPublication(mode=%s, source=%s, publication_hash=%s)" % (shown[0], shown[1], shown[6][:12])


class Reconciliation(_Frozen):
    """Outcome of reconcile_publication: the outcome and the publication hash. It says nothing about who wrote what and
    gives no right to notify."""

    __slots__ = ()

    @classmethod
    def _of(cls, outcome, publication_hash):
        return cls._wrap({"outcome": outcome, "publication_hash": publication_hash}, _error)

    outcome = property(lambda self: copy.deepcopy(self._view["outcome"]))
    publication_hash = property(lambda self: copy.deepcopy(self._view["publication_hash"]))
    committed = property(lambda self: False)

    def __repr__(self):
        return "Reconciliation(outcome=%s)" % self._view["outcome"]
