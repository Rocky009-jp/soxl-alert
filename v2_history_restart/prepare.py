"""prepare_restart_plan: a READY plan that holds the checked candidate History and its fingerprint, in memory only."""
from .build import build_restart, requested_at_of
from .values import RestartPlan


def prepare_restart_plan(history, resume_after, sessions, raw_observations, check_d, request_id, requested_at):
    """Check the request and the whole candidate; return the READY plan. Inputs are copied, never changed. check_d
    and resume_after are explicit; requested_at is an injected aware datetime (no clock is read). The reason code is
    fixed inside. Nothing is stored or applied: committed is always False."""
    basis, _candidate = build_restart(history, resume_after, sessions, raw_observations, check_d, request_id,
                                      lambda: requested_at_of(requested_at))
    return RestartPlan.make(basis)
