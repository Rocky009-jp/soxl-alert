"""The publish_* builders. Each runs the confirming step itself with the inputs it is given and builds a publication
only from its positive outcome (PREPARED for a day, CONFIRMED_IN_MEMORY for a plan). NO_CHANGE never makes one.

There is no builder that takes a History, a confirm result or a dict. HistoryPublication._make is called in this file
only."""
from v2_history import CONFIRMED_IN_MEMORY as MIGRATION_CONFIRMED
from v2_history import confirm_migration_plan, make_history_genesis, validate_history
from v2_history_adopt import CONFIRMED_IN_MEMORY as ADOPTION_CONFIRMED
from v2_history_adopt import confirm_prefix_adoption
from v2_history_ops import CONFIRMED_IN_MEMORY as RESOLUTION_CONFIRMED
from v2_history_ops import PREPARED, check_append_batch, confirm_history_resolution_plan, prepare_history_day
from v2_history_restart import CONFIRMED_IN_MEMORY as RESTART_CONFIRMED
from v2_history_restart import confirm_restart_plan
from v2_history_restore import CONFIRMED_IN_MEMORY as RESTORE_CONFIRMED
from v2_history_restore import confirm_restore_plan
from v2_persistence.codec import canonical_json, decode_snapshot, sha256_text
from v2_persistence.errors import snapshot_invalid
from v2_persistence.recompute import validate_snapshot

from .errors import candidate_invalid, publication_refused
from .read import prefix_digest, raw_identity
from .values import (ADOPTION, APPEND, CREATE, DAILY, GENESIS, MIGRATION, OPERATION, REPLACE, RESOLUTION, RESTART,
                     RESTORE, HistoryPublication)


def _candidate_fields(candidate):
    check = validate_history(candidate)
    return {"candidate_head_seq": check.head_seq, "candidate_head_hash": check.head_hash,
            "candidate_digest": check.history_digest,
            "candidate_state_digest": sha256_text(canonical_json(candidate.current_state))}


def _append(history, candidate, source, d, request_id, plan_hash):
    """The records that turn `history` into `candidate`; the candidate must be the physical extension of `history`."""
    check = validate_history(history)
    old, new = history.events, candidate.events
    n = len(old)
    if len(new) <= n or prefix_digest(new, n) != check.history_digest:
        raise candidate_invalid()
    body = {"operation": OPERATION, "mode": APPEND, "source": source, "d": d, "request_id": request_id,
            "plan_hash": plan_hash,
            "expected": {"head_seq": check.head_seq, "head_hash": check.head_hash,
                         "history_digest": check.history_digest},
            "source_v1": None, "records": new[n:], "candidate_history": None}
    body.update(_candidate_fields(candidate))
    return HistoryPublication._make(body)


def _whole(mode, source, candidate, expected, source_v1, request_id, plan_hash):
    """A publication that carries the whole candidate (a new file, or the replacement of the bytes that are there)."""
    body = {"operation": OPERATION, "mode": mode, "source": source, "d": None, "request_id": request_id,
            "plan_hash": plan_hash, "expected": expected, "source_v1": source_v1, "records": None,
            "candidate_history": candidate.to_dict()}
    body.update(_candidate_fields(candidate))
    return HistoryPublication._make(body)


def publish_day(history, d, series, sessions, raw_observations):
    res = prepare_history_day(history, d, series, sessions, raw_observations)
    if res.status != PREPARED or res.batch is None:
        raise publication_refused("not_prepared")
    candidate = check_append_batch(history, res.batch)
    return _append(history, candidate, DAILY, d, None, None)


def publish_resolution(plan, confirmed_plan_hash, history, sessions, raw_observations):
    res = confirm_history_resolution_plan(plan, confirmed_plan_hash, history, sessions, raw_observations)
    if res.status != RESOLUTION_CONFIRMED or res.batch is None:
        raise publication_refused("no_change")
    candidate = check_append_batch(history, res.batch)
    if candidate != res.history:
        raise candidate_invalid()
    return _append(history, candidate, RESOLUTION, None, plan.basis["request_id"], plan.plan_hash)


def publish_restart(plan, confirmed_plan_hash, history, sessions, raw_observations):
    res = confirm_restart_plan(plan, confirmed_plan_hash, history, sessions, raw_observations)
    if res.status != RESTART_CONFIRMED:
        raise publication_refused("no_change")
    return _append(history, res.history, RESTART, None, plan.basis["request_id"], plan.plan_hash)


def publish_restore(plan, confirmed_plan_hash, history, sessions, raw_observations, series):
    res = confirm_restore_plan(plan, confirmed_plan_hash, history, sessions, raw_observations, series)
    if res.status != RESTORE_CONFIRMED:
        raise publication_refused("no_change")
    return _append(history, res.history, RESTORE, None, plan.basis["request_id"], plan.plan_hash)


def publish_genesis(start_after, sessions):
    candidate = make_history_genesis(start_after, sessions)
    return _whole(CREATE, GENESIS, candidate, None, None, None, None)


def _snapshot_of(data):
    """The v1 snapshot from its raw bytes, as S2 reads snapshot.json (UTF-8, decode_snapshot, validate_snapshot)."""
    if type(data) is not bytes:
        raise snapshot_invalid("type")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise snapshot_invalid("utf8") from None
    snapshot = decode_snapshot(text)
    validate_snapshot(snapshot)
    return snapshot


def publish_migration(plan, confirmed_plan_hash, snapshot_data, resolutions, sessions, raw_observations):
    """snapshot_data: the raw bytes of the v1 snapshot.json. The identity that the publication names is computed from
    these bytes, so the bytes that C-4 sets aside are tied to the plan by it."""
    snapshot = _snapshot_of(snapshot_data)
    res = confirm_migration_plan(plan, confirmed_plan_hash, snapshot, resolutions, sessions, raw_observations)
    if res.status != MIGRATION_CONFIRMED:
        raise publication_refused("no_change")
    return _whole(CREATE, MIGRATION, res.history, None, raw_identity(snapshot_data), plan.basis["request_id"],
                  plan.plan_hash)


def publish_adoption(plan, confirmed_plan_hash, data):
    """data: the raw bytes of history.json that the plan names. Only CONFIRMED_IN_MEMORY (the original bytes) makes a
    publication; the expected identity is computed from `data`, and the identity in the plan is only compared."""
    res = confirm_prefix_adoption(plan, confirmed_plan_hash, data)
    if res.status != ADOPTION_CONFIRMED:
        raise publication_refused("no_change")
    raw = raw_identity(data)
    basis = plan.basis
    if (basis["raw_sha256"], basis["raw_size"]) != (raw["raw_sha256"], raw["raw_size"]):
        raise candidate_invalid()
    return _whole(REPLACE, ADOPTION, res.history, raw, None, basis["request_id"], plan.plan_hash)
