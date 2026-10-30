"""make_history_genesis: a schema-2 history holding only GENESIS, built with the same checks as S1 make_genesis."""
from v2_core.fixture import parse_iso_date
from v2_persistence.errors import PersistenceError
from v2_persistence.events import make_genesis_event, session_dict
from v2_recovery.ledger import copy_sessions

from .validate import validate_history
from .values import History, history_dict


def make_history_genesis(start_after, sessions):
    """GENESIS-only History. start_after is an explicit, confirmed session: the excluded lower bound of processing."""
    parse_iso_date(start_after, "start_after")
    sl = copy_sessions(sessions)
    s = sl.get(start_after)
    if s is None:
        raise PersistenceError("genesis_boundary_missing", "start_after")
    if not s.confirmed:
        raise PersistenceError("genesis_boundary_unconfirmed", "start_after")
    history = History.from_dict(history_dict([make_genesis_event(start_after, session_dict(s))]))
    validate_history(history)
    return history
