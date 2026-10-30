"""B-1 review probes. No product edits. Run with --repo <checkout> [--expect-fixed]."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--expect-fixed', action='store_true')
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    sys.path[:0] = [str(root), str(root / 'tests' / 'v2_history')]
    import h_helpers as H
    V, D = H.V, H.D
    outcomes = []

    def report(name, fixed, **facts):
        outcomes.append(fixed)
        print(json.dumps(dict(probe=name, fixed=fixed, **facts), sort_keys=True))

    def refusal(name, history):
        try:
            V.validate_history(history)
        except H.PersistenceError as error:
            report(name, True, code=error.code, rule=error.rule)
        except Exception as error:
            report(name, False, unexpected_type=type(error).__name__)
        else:
            report(name, False, accepted=True)

    b = H.HB()
    b.apply(D[1], 30.0)
    b.restore(0, {1: 'REAPPLY'}, 'restore-zero')
    V.validate_history(b.history())
    for value in (True, 1.0):
        events = H.deep(b.events)
        events[2]['superseded_seqs'] = [value]
        refusal('R01_superseded_' + type(value).__name__, H.rebuild(events, remap=True))

    world = H.P.World()
    world.apply(D[1], 30.0)
    snapshot, resolutions = world.snap(), H.R.empty_resolutions()
    plan = V.prepare_migration_plan(snapshot, resolutions, world.sessions, world.ledger, D[5], 'mig-probe', H.WHEN)
    history = V.History.from_dict(plan.basis['candidate_history'])
    V.validate_history(history)
    for field in ('schema_version', 'head_seq'):
        for value in (True, 1.0):
            events = H.deep(history.events)
            events[-1]['source'][field] = value
            refusal('R01_source_' + field + '_' + type(value).__name__, H.rebuild(events))

    for field in ('head_seq', 'head_hash', 'schema_version'):
        data = H.example_u().history().to_dict()
        data[field] = {'nested': []}
        history = V.History.from_dict(data)
        before, text, digest = history.to_dict(), V.encode_history(history), history.digest
        getattr(history, field)['nested'].append(7)
        report('R02_history_' + field, history.to_dict() == before,
               view_changed=history.to_dict() != before, text_unchanged=V.encode_history(history) == text,
               digest_unchanged=history.digest == digest)

    plan = V.MigrationPlan.from_dict({'basis': {}, 'plan_hash': {'nested': []}})
    before = plan.to_dict()
    plan.plan_hash['nested'].append(7)
    report('R02_plan_hash', plan.to_dict() == before, view_changed=plan.to_dict() != before)
    print(json.dumps(dict(controls_passed=2, observations=len(outcomes), fixed=sum(outcomes))))
    return 0 if (all(outcomes) if args.expect_fixed else not any(outcomes)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
