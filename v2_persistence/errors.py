"""Error type of the persistence domain. Codes, fields and rules are fixed identifiers; no raw input is echoed."""
from v2_core.errors import CoreError


class PersistenceError(CoreError):
    """Same shape as the core errors (code, field, detail) plus `rule`, a fixed identifier for snapshot_invalid.

    Core errors raised for injected inputs (ledger, sessions, series) are not wrapped: they keep their own code.
    """

    def __init__(self, code, field=None, detail=None, rule=None):
        super().__init__(code, field, detail)
        self.rule = rule


def snapshot_invalid(rule):
    return PersistenceError("snapshot_invalid", "snapshot", rule=rule)
