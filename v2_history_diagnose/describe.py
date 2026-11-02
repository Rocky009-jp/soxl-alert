"""The reported parts of a diagnosis: claimed (what the file says), verified (what a checker accepted) and discarded
(what lies after the verified part). Built from checker outcomes and from fixed-shape reads of the parsed JSON.

Nothing here carries a market value, a decision, a F&G value, a resume_after or free text."""
from v2_history import KINDS
from v2_history.common import is_date, is_hex64, is_int
from v2_persistence.codec import CORE_SHA, canonical_json, sha256_text
from v2_recovery.common import valid_request_id

V1_KINDS = ("GENESIS", "APPLY")


def claimed_of(data):
    """The header's own statements, each only when its type is right. Not checked values."""
    sv = data.get("schema_version")
    core = data.get("core_sha")
    head_seq = data.get("head_seq")
    head_hash = data.get("head_hash")
    events = data.get("events")
    return {"schema_version": sv if is_int(sv) else None,
            "core_sha_matches": (core == CORE_SHA) if isinstance(core, str) else None,
            "head_seq": head_seq if is_int(head_seq) else None,
            "head_hash": head_hash if is_hex64(head_hash) else None,
            "event_count": len(events) if isinstance(events, list) else None}


def verified_v2(check):
    """From a HistoryCheck (schema 2)."""
    b = check.current_boundary
    return {"count": check.record_count, "head_seq": check.head_seq, "head_hash": check.head_hash,
            "state_digest": check.state_digest, "document_digest": check.history_digest,
            "boundary": {"kind": b.kind, "seq": b.seq, "after": b.after}, "latest_apply_d": check.latest_apply_d,
            "processing_after": check.processing_after, "effective_count": len(check.effective_seqs),
            "superseded_count": len(check.superseded_seqs), "migrated": check.migrated}


def verified_v1(valid, count, document_text):
    """From a ValidatedSnapshot (schema 1). `document_text` is the canonical text of the document that was checked."""
    state = valid.state
    applies = valid.applies
    return {"count": count, "head_seq": valid.head_seq, "head_hash": valid.head_hash,
            "state_digest": sha256_text(canonical_json(state.to_dict())),
            "document_digest": sha256_text(document_text),
            "boundary": {"kind": "GENESIS", "seq": 0, "after": valid.start_after},
            "latest_apply_d": applies[-1].d if applies else None,
            "processing_after": state.as_of_d if state.as_of_d is not None else valid.start_after,
            "effective_count": count, "superseded_count": 0, "migrated": None}


def _item(index, ev, kinds):
    if not isinstance(ev, dict):
        return {"index": index, "kind": "?", "seq": None, "d": None, "request_id": None}
    kind = ev.get("kind")
    seq = ev.get("seq")
    d = ev.get("d")
    rid = ev.get("request_id")
    return {"index": index, "kind": kind if isinstance(kind, str) and kind in kinds else "?",
            "seq": seq if is_int(seq) else None, "d": d if is_date(d) else None,
            "request_id": rid if valid_request_id(rid) else None}


def discarded_of(events, from_index, version):
    """{from_index, count, items} for the records from `from_index` on; None when `events` is not a list."""
    if not isinstance(events, list):
        return None
    kinds = V1_KINDS if version == 1 else KINDS
    items = [_item(i, ev, kinds) for i, ev in enumerate(events) if i >= from_index]
    return {"from_index": from_index, "count": len(items), "items": items}
