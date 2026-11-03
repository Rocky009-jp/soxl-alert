"""prepare_prefix_adoption: a READY plan that holds the checked candidate History and its fingerprint, in memory only."""
from v2_history_diagnose import diagnose_history_bytes
from v2_recovery.common import requested_text, valid_request_id

from .build import build_adoption
from .errors import adoption_invalid
from .values import AdoptionPlan


def check_arguments(data, adopt_count, request_id, requested_at):
    """Steps 1-4, in this order: data, adopt_count, requested_at (existing InputError), request_id. Returns the fixed
    UTC text of requested_at. No clock is read."""
    if type(data) is not bytes:
        raise adoption_invalid("data", "type")
    if type(adopt_count) is not int or adopt_count < 1:
        raise adoption_invalid("adopt_count", "type")
    text = requested_text(requested_at)
    if not valid_request_id(request_id):
        raise adoption_invalid("request_id", "request_id")
    return text


def prepare_prefix_adoption(data, adopt_count, request_id, requested_at):
    """Diagnose `data` (the raw bytes of a damaged schema-2 history), and when exactly its first `adopt_count` records are
    the verified prefix, return the READY plan: the prefix plus one RECOVERY_PREFIX_ADOPTION record as a candidate
    History. requested_at is an injected aware datetime. Nothing is read from or written to anywhere: committed is
    always False."""
    text = check_arguments(data, adopt_count, request_id, requested_at)
    basis, _candidate = build_adoption(data, diagnose_history_bytes(data), adopt_count, request_id, text)
    return AdoptionPlan.make(basis)
