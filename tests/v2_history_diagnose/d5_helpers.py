"""Helpers for the v2_history_diagnose tests (never imported by the runtime). Synthetic sessions, series and ledgers.

Sockets are disabled on import (as in the other test packages). The existing helpers ho_helpers / h_helpers / r_helpers /
p_helpers / r4_helpers are only imported, never changed. Histories are written with the independent test-only record
builder HB (h_helpers); a corrupted file is made by editing the builder's event dicts and writing the canonical JSON
with the header the file would have (h_helpers.header), so an expected prefix length is decided from where the file was
changed and never from the code under test.
"""
import copy
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history_ops"), os.path.join(ROOT, "tests", "v2_history_restore")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ho_helpers as T  # noqa: E402  (existing helper; it also disables sockets)
import r4_helpers as R4  # noqa: E402
import v2_history as V  # noqa: E402
import v2_history_diagnose as G  # noqa: E402
from v2_history_diagnose import diagnose as GD  # noqa: E402
from v2_persistence.codec import canonical_json, encode_snapshot  # noqa: E402
from v2_persistence.errors import PersistenceError  # noqa: E402
from v2_persistence.events import snapshot_dict  # noqa: E402

H, P, D, WHEN = T.H, T.P, T.D, T.WHEN
ZERO = "0" * 64
CORE_SHA = H.CORE_SHA


def cj(x):
    return canonical_json(x)


def deep(x):
    return copy.deepcopy(x)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def text_sha(text):
    return sha(text.encode("utf-8"))


# --- bytes of a file ---------------------------------------------------------------------------------------------
def doc_bytes(doc):
    """The canonical bytes of a document dict (what encode_history writes for the same value)."""
    return cj(doc).encode("utf-8")


def file_of(records, **header_edits):
    """The file a store would hold for these records, with optional edits of the header after it is written."""
    doc = H.header(deep(records))
    doc.update(header_edits)
    return doc_bytes(doc)


def history_file(builder):
    return V.encode_history(builder.history()).encode("utf-8")


def indented(data):
    """The same value written with indentation (not the canonical text)."""
    return json.dumps(json.loads(data.decode("utf-8")), indent=2, sort_keys=True).encode("utf-8")


def with_hash(events, index, value=ZERO):
    out = deep(events)
    out[index]["event_hash"] = value
    return out


# --- v1 snapshot files -------------------------------------------------------------------------------------------
def v1_world(applies=4):
    w = P.World()
    for i in range(1, applies + 1):
        w.apply(D[i], 26.0 + i, "R%d" % i)
    return w


def v1_file(snapshot):
    return encode_snapshot(snapshot).encode("utf-8")


def v1_doc_file(records, **header_edits):
    doc = snapshot_dict(deep(records))
    doc.update(header_edits)
    return doc_bytes(doc)


# --- a spy around the checkers the diagnosis really calls ---------------------------------------------------------
class Spy(object):
    """Wraps the checker names that v2_history_diagnose.diagnose really references. Each call is logged as
    (version, record_count, outcome, rule): outcome is "PASS" or the PersistenceError code."""

    def __enter__(self):
        self.calls = []
        self._v2, self._v1 = GD.validate_history, GD.validate_snapshot
        spy = self

        def count_of(value):
            events = value.events
            return len(events) if isinstance(events, list) else None

        def v2(history):
            return spy._log(2, count_of(history), spy._v2, history)

        def v1(snapshot):
            return spy._log(1, count_of(snapshot), spy._v1, snapshot)

        GD.validate_history, GD.validate_snapshot = v2, v1
        return self

    def __exit__(self, *_exc):
        GD.validate_history, GD.validate_snapshot = self._v2, self._v1
        return False

    def _log(self, version, count, fn, arg):
        try:
            out = fn(arg)
        except Exception as exc:
            self.calls.append((version, count, getattr(exc, "code", type(exc).__name__), getattr(exc, "rule", None)))
            raise
        self.calls.append((version, count, "PASS", None))
        return out

    def ks(self, version=None):
        return [c[1] for c in self.calls if version in (None, c[0])]

    def outcome(self, count):
        return [(c[2], c[3]) for c in self.calls if c[1] == count]


def diagnose(data):
    return G.diagnose_history_bytes(data).to_dict()


def full_error(doc_or_events_file):
    """(code, field, rule) the unchanged v2 checker gives for a whole file, decided independently of the diagnosis."""
    doc = json.loads(doc_or_events_file.decode("utf-8"))
    try:
        V.validate_history(V.History.from_dict(doc))
    except PersistenceError as exc:
        return exc.code, exc.field, exc.rule
    return None


def full_error_v1(data):
    from v2_persistence.codec import Snapshot
    from v2_persistence.recompute import validate_snapshot
    doc = json.loads(data.decode("utf-8"))
    try:
        validate_snapshot(Snapshot.from_dict(doc))
    except PersistenceError as exc:
        return exc.code, exc.field, exc.rule
    return None


# --- the examples (existing builders) -------------------------------------------------------------------------------
def ex_new():
    """0 GENESIS, 1..6 APPLY D1..D6: a new schema-2 history without any batch."""
    b = H.HB()
    for i in range(1, 7):
        b.apply(D[i], 26.0 + i)
    return b


def ex_u():
    return H.example_u()


def ex_r():
    return H.example_r()


def ex_rb():
    return H.example_rb()


def ex_m():
    return H.example_m()[0]


def ex_m_empty():
    w, snap, rs, ledger, check_d = H.example_m_empty_world()
    return H.HB(world=w, events=H.migrate(w, snap, rs, ledger, check_d).events)
