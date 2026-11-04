"""An in-memory store with the C-3 read/publish/reconcile shape (review probes only)."""
from v2_history_publish import check_publication, reconcile_publication, history_bytes, read_history_bytes
from v2_core.errors import CoreError


class Res(object):
    def __init__(self, history):
        self.history = history


class MemStore(object):
    def __init__(self, history, faults=None):
        self.data = history_bytes(history)
        self.calls = []
        self.faults = dict(faults or {})      # {(method, n): action}

    def _hit(self, name):
        n = sum(1 for c in self.calls if c == name)
        self.calls.append(name)
        return self.faults.get((name, n))

    def read(self):
        act = self._hit("read")
        if isinstance(act, CoreError):
            raise act
        return read_history_bytes(self.data)[0]

    def publish(self, pub):
        act = self._hit("publish")
        if isinstance(act, CoreError) and act.code != "store_commit_uncertain":
            raise act
        cand = check_publication(self.data, pub)
        if act == "uncertain_not_written":
            raise CoreError("store_commit_uncertain", "store")
        self.data = history_bytes(cand)
        if isinstance(act, CoreError):
            raise act
        return Res(cand)

    def reconcile(self, pub):
        act = self._hit("reconcile")
        if isinstance(act, CoreError):
            raise act
        return reconcile_publication(self.data, pub)
