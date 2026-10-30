"""read_effective and project_history_ledger: a checked history seen through its effective records only."""
from v2_history import validate_history
from v2_recovery.facts import LedgerContext
from v2_recovery.project import resolve_core

from .chain import Chain
from .values import HistoryLedger


def read_effective(history):
    """The effective view of a history. validate_history runs every time; nothing is reused between calls."""
    return Chain(history, validate_history(history)).view()


def ledger_of(history, chain, sessions, raw_observations, check_d, field="resolutions", records=None, ctx=None):
    """The projection over the whole effective chain (design 5.1 steps 3-5). Returns (HistoryLedger, context).
    A context already built for the same chain, sessions, ledger and check_d may be passed."""
    if ctx is None:
        ctx = LedgerContext.from_facts(chain.facts, sessions, raw_observations, check_d)
    eff = resolve_core(ctx, chain.resolutions if records is None else records, history.digest, field)
    return HistoryLedger._make(eff.rows, eff.excluded_fingerprints, eff.supplemented, eff.ledger_digest,
                               eff.effective_digest, history.digest, check_d), ctx


def project_history_ledger(history, sessions, raw_observations, check_d):
    """The final ledger over every effective segment, ACK and declaration. check_d is explicit; the raw ledger, the
    history and the sessions are never changed. The market state is neither read for a rule nor written."""
    chain = Chain(history, validate_history(history))
    return ledger_of(history, chain, sessions, raw_observations, check_d)[0]
