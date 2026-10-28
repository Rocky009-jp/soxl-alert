"""Read-only reprobes for S1 receipt review; no implementation files are changed.

Run from a b9586d6 checkout:
  python -B docs/reviews/V2_PERSISTENCE_DOMAIN_S1_REPRO_20261028.py --repo-root .
Default: report observations (exit 0 means the probe completed, not that S1 passed).
After a fix, add --expect-fixed: exit 1 if any of the three reviewed issues is still observed.
Uses synthetic helpers; importing p_helpers disables sockets.
"""
import argparse
import json
import sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path(__file__).resolve().parents[2])
    ap.add_argument("--expect-fixed",action="store_true")
    args=ap.parse_args()
    root=args.repo_root.resolve()
    sys.path.insert(0,str(root))
    sys.path.insert(0,str(root/"tests"/"v2_persistence"))
    import p_helpers as h
    from v2_core.errors import CoreError
    from v2_persistence.codec import encode_snapshot,decode_snapshot
    from v2_persistence.errors import PersistenceError
    from v2_persistence.events import input_hash_of
    from v2_persistence.recompute import validate_snapshot

    results=[]
    def alias_case(name,mutate):
        w=h.World()
        w.apply(h.DATES[1],27.0)
        before=w.snap().to_dict()
        before_text=encode_snapshot(w.snap())
        rejected=False
        try:
            mutate(w)
        except (AttributeError,TypeError):
            rejected=True
        after=w.snap()
        error=None
        try:
            validate_snapshot(after)
        except CoreError as e:
            error={"code":e.code,"rule":getattr(e,"rule",None)}
        changed=after.to_dict()!=before
        disagrees=decode_snapshot(encode_snapshot(after)).to_dict()!=after.to_dict()
        results.append({"issue":"R-01","case":name,"issue_present":changed or disagrees or error is not None,
            "stored_content_changed_without_commit":changed,"mutation_rejected":rejected,
            "encoded_snapshot_unchanged":encode_snapshot(after)==before_text,
            "encoded_view_disagrees_with_read_view":disagrees,
            "head_unchanged":(after.head_seq,after.head_hash)==(before["head_seq"],before["head_hash"]),
            "validation_after_mutation":error})

    def edit_no_commit(w):
        result=w.prepare(h.DATES[2])
        assert result.status=="NO_COMMIT" and result.plan is None
        result.core_result.next_state.fixed_decision["record_id"]="REVIEW-EDIT"
    alias_case("NO_COMMIT.next_state.fixed_decision",edit_no_commit)
    alias_case("ValidatedSnapshot.boundary_session",
        lambda w:validate_snapshot(w.snap()).boundary_session.update(confirmed=False))
    alias_case("AppliedDay.transition_result",
        lambda w:validate_snapshot(w.snap()).applies[0].transition_result["notes"].append("review_marker"))
    alias_case("AppliedDay.state_after",
        lambda w:validate_snapshot(w.snap()).applies[0].state_after.update(streak=99))

    for field in ("soxx","sma","rsi","shd","prev_rsi"):
        w=h.World(per_date={h.DATES[1]:{field:True}})
        w.ledger.append(h.obs("R1",h.DATES[1],27.0))
        try:
            result=w.prepare(h.DATES[1])
        except CoreError as e:
            results.append({"issue":"R-02","case":"market_bool."+field,"issue_present":False,
                "rejected":True,"code":e.code,"rule":getattr(e,"rule",None)})
        else:
            results.append({"issue":"R-02","case":"market_bool."+field,"issue_present":True,
                "rejected":False,"status":result.status,
                "saved_input":None if result.plan is None else result.plan.event["confirmed_inputs"]["row"][field]})

    w=h.World()
    w.apply(h.DATES[1],27.0)
    events=w.snap().events
    events[1]["confirmed_inputs"]["row"]["soxx"]=10**400
    events[1]["input_hash"]=input_hash_of(events[1]["confirmed_inputs"])
    malformed=h.rehash(events)
    try:
        validate_snapshot(malformed)
    except PersistenceError as e:
        results.append({"issue":"R-03","case":"saved_market_int_10_pow_400",
            "issue_present":e.code!="snapshot_invalid","error":type(e).__name__,"code":e.code,"rule":e.rule})
    except Exception as e:
        results.append({"issue":"R-03","case":"saved_market_int_10_pow_400",
            "issue_present":True,"error":type(e).__name__,"code":getattr(e,"code",None)})
    else:
        results.append({"issue":"R-03","case":"saved_market_int_10_pow_400","issue_present":True,"accepted":True})
    for result in results:
        print(json.dumps(result,sort_keys=True))
    count=sum(bool(x["issue_present"]) for x in results)
    print(json.dumps({"probe_cases":len(results),"issue_observations":count,"expect_fixed":args.expect_fixed}))
    return 1 if args.expect_fixed and count else 0

if __name__=="__main__":
    sys.exit(main())
