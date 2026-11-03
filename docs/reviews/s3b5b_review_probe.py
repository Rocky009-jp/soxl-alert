"""Independent review checks for S3-B-5b. Synthetic data; no product writes.

Run from a complete pinned checkout:
  python -B docs/reviews/s3b5b_review_probe.py --repo .
After the limited repair, add --expect-fixed (exit 0 means every issue is fixed).
Baseline: 782debc2a901a421a2b5205f9dd8ad4f0b484b01 / Python 3.12.14 Linux.
Only public product APIs are called; existing fixture helpers supply synthetic histories.
"""
import argparse
import copy
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--expect-fixed", action="store_true")
    args = ap.parse_args()
    root = args.repo.resolve()
    sys.path[:0] = [str(root), str(root / "tests/v2_history_adopt")]
    import a5_helpers as Z
    from v2_history import History, encode_history, validate_history
    from v2_history.values import history_dict
    from v2_history_adopt import AdoptionPlan, confirm_prefix_adoption, prepare_prefix_adoption
    from v2_history_diagnose import diagnose_history_bytes
    from v2_persistence.codec import canonical_json, sha256_text
    from v2_persistence.errors import PersistenceError

    mismatch = ("history_plan_mismatch", "plan", None)

    def outcome(plan, data):
        try:
            result = confirm_prefix_adoption(plan, plan.plan_hash, data)
        except PersistenceError as exc:
            return exc.code, exc.field, exc.rule
        return result.status

    _, raw, count = Z.new_world()
    plan = prepare_prefix_adoption(raw, count, "review-adopt", Z.WHEN)
    candidate = encode_history(History.from_dict(plan.basis["candidate_history"])).encode("utf-8")
    block = plan.basis["discarded"]
    changes = {
        "empty": {},
        "negative_count": dict(block, count=-1),
        "bool_count": dict(block, count=True),
        "wrong_start": dict(block, from_index=0),
        "wrong_count": dict(block, count=block["count"] + 1),
        "items_not_list": dict(block, items="wrong"),
        "extra_key": dict(block, extra=0),
        "item_missing_key": dict(block, items=[{}]),
        "wrong_item_index": dict(block, items=[dict(block["items"][0], index=count + 1)]),
        "bool_item_index": dict(block, items=[dict(block["items"][0], index=True)]),
        "bool_item_seq": dict(block, items=[dict(block["items"][0], seq=True)]),
        "invalid_kind": dict(block, items=[dict(block["items"][0], kind="BOGUS")]),
        "invalid_day": dict(block, items=[dict(block["items"][0], d=7)]),
        "invalid_request_id": dict(block, items=[dict(block["items"][0], request_id="has space")]),
    }
    issues = []
    for name, bad in changes.items():
        obj = plan.to_dict()
        obj["basis"]["discarded"] = copy.deepcopy(bad)
        obj["plan_hash"] = sha256_text(canonical_json(obj["basis"]))
        forged = AdoptionPlan.from_dict(obj)
        # Same original raw bytes already reject every malformed plan (control).
        assert outcome(forged, raw) == mismatch, name
        got = outcome(forged, candidate)
        fixed = got == mismatch
        print("R01/" + name, "FIXED" if fixed else "ISSUE", got)
        issues.append(fixed)
        if name in ("empty", "negative_count", "bool_count", "wrong_start", "wrong_count"):
            got = outcome(forged, None)
            fixed = got == mismatch
            print("R01/" + name + "/priority", "FIXED" if fixed else "ISSUE", got)
            issues.append(fixed)

    # Controls: correct results, stale bytes, argument error, exact byte identity.
    assert outcome(plan, raw) == "CONFIRMED_IN_MEMORY"
    assert outcome(plan, candidate) == "NO_CHANGE"
    assert outcome(plan, raw + b" ") == ("history_plan_stale", "plan", None)
    assert outcome(plan, None) == ("adoption_invalid", "data", "type")
    assert outcome(plan, candidate + b"\n") == ("history_plan_stale", "plan", None)
    assert outcome(plan, json.dumps(json.loads(candidate), indent=2).encode()) == ("history_plan_stale", "plan", None)
    print("OUTCOME_CONTROLS 6/6 PASS; ORIGINAL_REJECTION_CONTROLS 14/14 PASS")

    # Different families, every corruption position, header-only damage. Compute
    # the longest prefix independently by enumerating ALL lengths in ascending
    # order, not by using the diagnosis' answer as the expected prefix length.
    grid = 0
    factories = [Z.X.ex_new, Z.X.ex_u, Z.X.ex_r, Z.X.ex_rb, Z.X.ex_m, Z.X.ex_m_empty]
    for factory in factories:
        b = factory()
        n = len(b.events)
        for damage_at in range(1, n + 1):
            doc = Z.H.header(copy.deepcopy(b.events))
            if damage_at == n:
                doc["head_hash"] = Z.ZERO  # records intact, only the header broken
            else:
                doc["events"][damage_at]["event_hash"] = Z.ZERO
            data = canonical_json(doc).encode("utf-8")
            candidates = []
            for k in range(1, n + 1):
                try:
                    check = validate_history(History.from_dict(history_dict(doc["events"][:k])))
                except (PersistenceError, KeyError, TypeError):
                    continue
                candidates.append((k, check))
            k, check = candidates[-1]
            diagnosis = diagnose_history_bytes(data)
            assert diagnosis.to_dict()["verified"]["count"] == k
            tail = doc["events"][k:]
            blocked = not check.migrated and any(
                isinstance(e, dict) and (e.get("kind") == "SCHEMA_MIGRATION" or e.get("origin") is not None)
                for e in tail
            )
            if blocked:
                try:
                    prepare_prefix_adoption(data, k, "review-grid", Z.WHEN)
                except PersistenceError as exc:
                    assert (exc.code, exc.field, exc.rule) == ("adoption_invalid", "data", "migration_discarded")
                else:
                    raise AssertionError("migration trace was discarded")
            else:
                p = prepare_prefix_adoption(data, k, "review-grid", Z.WHEN)
                result = confirm_prefix_adoption(p, p.plan_hash, data)
                assert result.status == "CONFIRMED_IN_MEMORY" and result.committed is False
                assert result.history.events[:-1] == doc["events"][:k]
                assert result.history.current_state == doc["events"][k - 1]["state_after"]
                assert len(result.history.events) == k + 1
                assert outcome(p, encode_history(result.history).encode("utf-8")) == "NO_CHANGE"
            grid += 1
    print("PREFIX_GRID", grid, "PASS")
    print("REVIEW_OBSERVATIONS", len(issues), "fixed", sum(issues), "unfixed", len(issues) - sum(issues))
    return 0 if (all(issues) if args.expect_fixed else not any(issues)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
