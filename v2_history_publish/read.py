"""The byte form of a stored schema-2 history: written as the canonical text in UTF-8 (no BOM, no newline), read
strictly (UTF-8, the unchanged decode_history and validate_history). A valid text that is not canonical is read (as S2
and the damage diagnosis do) and is identified by the digest of its canonical form. This is the only file that uses a
hash function of the standard library, for the identity of raw bytes."""
import copy
import hashlib

from v2_history import History, decode_history, encode_history, validate_history
from v2_history.values import history_dict

from .errors import history_unreadable


def history_bytes(history):
    """The canonical text of a History as UTF-8. A value that is not a History is refused by the encoder."""
    return encode_history(history).encode("utf-8")


def raw_identity(data):
    """{raw_sha256, raw_size} of exactly `bytes`, computed here (never copied from a plan)."""
    if type(data) is not bytes:
        raise history_unreadable("type")
    return {"raw_sha256": hashlib.sha256(data).hexdigest(), "raw_size": len(data)}


def read_history_bytes(data):
    """bytes -> (History, HistoryCheck). Raises on anything that is not a fully valid schema-2 history. A byte order
    mark is not removed, a text that is not canonical is accepted when it is valid."""
    if type(data) is not bytes:
        raise history_unreadable("type")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise history_unreadable("utf8") from None
    history = decode_history(text)
    return history, validate_history(history)


def prefix_digest(events, n):
    """Digest of the history made of the first n physical records (what a reader of that prefix would compute)."""
    return History.from_dict(history_dict(copy.deepcopy(events[:n]))).digest
