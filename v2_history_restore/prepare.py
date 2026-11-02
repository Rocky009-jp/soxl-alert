"""prepare_restore_plan: a READY plan that holds the checked candidate History and its fingerprint, in memory only."""
from .build import build_restore, requested_at_of
from .values import RestorePlan


def prepare_restore_plan(history, restore_point, ops, sessions, raw_observations, series, check_d, request_id,
                         requested_at):
    """Check the request and the whole candidate; return the READY plan. Inputs are copied, never changed. restore_point
    ({seq, event_hash}), the ordered ops and check_d are explicit; requested_at is an injected aware datetime (no clock
    is read). The reason code is fixed inside. Nothing is stored or applied: committed is always False."""
    basis, _candidate = build_restore(history, restore_point, ops, sessions, raw_observations, series, check_d,
                                      request_id, lambda: requested_at_of(requested_at))
    return RestorePlan.make(basis)
