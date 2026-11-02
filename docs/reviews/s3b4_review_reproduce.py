"""Read-only S3-B-4 review reproduction against --repo.

Uses only synthetic data; never edits repository files. --mutations executes the
exact four published single-deletion/substitution variants in isolated in-memory
module namespaces. --expect-fixed verifies the runtime R-01/R-02 observations.
"""
import argparse
import ast
import importlib
import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
ap.add_argument('--expect-fixed', action='store_true')
ap.add_argument('--mutations', action='store_true')
args = ap.parse_args()
root = Path(args.repo).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests' / 'v2_history_restore'))
import r4_helpers as R
from v2_core.errors import CoreError
Z, H, P, D = R.Z, R.H, R.P, R.D

def outcome(fn):
    try:
        got = fn()
        return ('OK', getattr(got, 'status', None))
    except CoreError as exc:
        return ('ERR', exc.code, exc.field, getattr(exc, 'rule', None))

observed = []

def ref_case(kind):
    b = H.HB()
    if kind == 'applied_ref':
        b.apply(D[1], 27.0)
        b.restart(D[1], 'review-source-r')
        extra = P.obs('review-extra', D[1], 41.0, hour=21)
        b.ack('ADDED', D[1], [H.fp(extra)], 'review-source-q', applied=1)
        point = 1
    else:
        b.apply(D[3], 27.0)
        b.restart(D[3], 'review-source-r')
        extra = P.obs('review-late', D[1], 21.0)
        b.ack('LATE', D[1], [H.fp(extra)], 'review-source-q', missing=('APPLY', 1))
        point = 1
    b.w.ledger.append(extra)
    plan = R.prep(b, point, {2:'DROP', 3:'REPLAY'}, D[5], 'review-r1')
    result = R.confirm(plan, b.history(), b.w)
    change = next(c for c in plan.basis['changes'] if c['op'] == 'REPLAY')
    old, new = b.events[change['from_seq']], result.history.events[change['to_seq']]
    actual = sorted(k for k in ('applied_ref', 'missing_ref', 'state_after') if R.cj(old[k]) != R.cj(new[k]))
    assert old[kind] == new[kind], kind
    good = change['changed_fields'] == actual
    observed.append(('R-01 '+kind, good))
    print('R-01', kind, 'reported=', change['changed_fields'], 'actual=', actual, 'fixed=', good)

ref_case('applied_ref')
ref_case('missing_ref')

b = R.ex_restart_between()
h, w = b.history(), b.w
plan = R.prep(b, 1, {2:'DROP',3:'REAPPLY'}, D[3], 'review-shape')
valid_result = R.confirm(plan, h, w)
assert valid_result.status == 'CONFIRMED_IN_MEMORY'
assert R.confirm(plan, valid_result.history, w).status == 'NO_CHANGE'
for replacement in ([{}], [{'op': []}], [{'op':'REAPPLY', 'from_seq': True}]):
    bad = R.refreshed(plan, lambda bs, v=replacement: bs.__setitem__('changes', v))
    assert outcome(lambda: R.confirm(bad, h, w))[1] == 'history_plan_mismatch'
    for branch, current in (('A', h), ('B', valid_result.history)):
        got = outcome(lambda: Z.confirm_restore_plan(bad, bad.plan_hash, current, None, w.ledger, w.series))
        good = got[1] == 'history_plan_mismatch'
        observed.append(('R-02 changes '+branch+' '+repr(replacement), good))
        print('R-02 malformed changes + sessions=None', branch, ':', got, 'fixed=', good)
bad_ops = R.refreshed(plan, lambda bs: bs['ops'][-1].__setitem__('from_seq', -1))
for branch, current in (('A', h), ('B', valid_result.history)):
    got = outcome(lambda: Z.confirm_restore_plan(bad_ops, bad_ops.plan_hash, current, None, w.ledger, w.series))
    good = got[1] == 'history_plan_mismatch'
    observed.append(('R-02 negative from_seq '+branch, good))
    print('R-02 negative from_seq + sessions=None', branch, ':', got, 'fixed=', good)

def calendar_added(with_restart, with_decision):
    b2 = H.HB()
    full = b2.w.sessions
    b2.w.sessions = R.sessions_with(dates=[d for d in D if d != D[1]])
    b2.apply(D[3], 27.0)
    if with_restart:
        b2.restart(D[3], 'review-old-r')
    R.V.validate_history(b2.history())
    b2.w.sessions = full
    if with_decision:
        b2.w.ledger.append(P.obs('review-new-session', D[1], 26.0))
    mapping = {1:'REAPPLY'}
    if with_restart:
        mapping[2] = 'DROP'
    return b2, mapping

def prepare_added(with_restart=True, with_decision=True):
    c, mapping = calendar_added(with_restart, with_decision)
    return R.prep(c, 0, mapping, D[5], 'review-calendar')

def prepare_frontier():
    c = H.HB()
    c.declare(D[1], 'review-declare-1')
    c.declare(D[2], 'review-declare-2')
    R.V.validate_history(c.history())
    c.w.sessions = R.sessions_with(dates=[d for d in D if d != D[1]])
    return R.prep(c, 0, {1:'DROP',2:'REPLAY'}, D[4], 'review-frontier')

controls = {
    'M09c': outcome(lambda: prepare_added(True, True)),
    'M12b': outcome(prepare_frontier),
    'M17c': outcome(lambda: prepare_added(False, False)),
}
assert controls['M09c'][1] == 'restore_requires_consume', controls
assert controls['M12b'] == ('OK','READY'), controls
assert controls['M17c'] == ('OK','READY'), controls
frontier_plan = prepare_frontier()
assert frontier_plan.basis['candidate_records'][-1]['frontier_before'] == D[0]
no_drop_plan = prepare_added(False, False)
assert not any(c['op'] == 'DROP' for c in no_drop_plan.basis['changes'])
assert no_drop_plan.basis['changes'][0]['same_as_superseded'] is False
assert no_drop_plan.basis['candidate_records'][-1]['skipped_sessions'] == [D[1],D[2]]
print('calendar controls:', json.dumps(controls, ensure_ascii=False))
calendar_builder, calendar_ops = calendar_added(False, False)
calendar_plan = R.prep(calendar_builder, 0, calendar_ops, D[5], 'review-calendar-confirm')
calendar_result = R.confirm(calendar_plan, calendar_builder.history(), calendar_builder.w)
assert calendar_result.status == 'CONFIRMED_IN_MEMORY'
assert R.confirm(calendar_plan, calendar_result.history, calendar_builder.w).status == 'NO_CHANGE'
print('no-DROP calendar-change plan: confirmation A and B OK; changed_fields=',
      calendar_plan.basis['changes'][0]['changed_fields'])
bad_tail = R.refreshed(plan, lambda bs: bs.__setitem__('candidate_records', [{}]))
def tail_probe():
    return Z.confirm_restore_plan(bad_tail, bad_tail.plan_hash, h, None, w.ledger, w.series)
controls['M16d'] = outcome(tail_probe)
assert controls['M16d'][1] == 'history_plan_mismatch'

if args.mutations:
    text = (root / 'tests/v2_history_restore/r4_sensitivity.py').read_text(encoding='utf-8')
    tree = ast.parse(text)
    wanted = {'M09c','M12b','M16d','M17c'}
    variants = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Tuple) and len(node.elts) >= 2 and isinstance(node.elts[0], ast.Constant)
                and node.elts[0].value in wanted):
            variants[node.elts[0].value] = node.elts[1]
    constants = {'BUILD':'v2_history_restore/build.py', 'RECORDS':'v2_history_restore/records.py',
                 'CONFIRM':'v2_history_restore/confirm.py'}
    @contextmanager
    def mutant(mid):
        # Only evaluate the published replacement list: constant paths/strings,
        # never the script's runner, probes, or arbitrary source from a plan.
        changes = eval(compile(ast.Expression(variants[mid]), '<published-mutation>', 'eval'), {'__builtins__':{}}, constants)
        assert len(changes) == 1
        relative, before, after = changes[0]
        src = (root / relative).read_text(encoding='utf-8')
        assert src.count(before) == 1, (mid, 'mutation pattern missing')
        ns = {'__name__':'v2_history_restore.'+Path(relative).stem, '__package__':'v2_history_restore'}
        exec(compile(src.replace(before,after), '<review-'+mid+'>', 'exec'), ns)
        with ExitStack() as stack:
            if Path(relative).stem == 'build':
                stack.enter_context(patch('v2_history_restore.prepare.build_restore', ns['build_restore']))
            elif Path(relative).stem == 'records':
                stack.enter_context(patch('v2_history_restore.build.plan_records', ns['plan_records']))
            else:
                stack.enter_context(patch.object(Z, 'confirm_restore_plan', ns['confirm_restore_plan']))
            yield
    callbacks = {'M09c':lambda:prepare_added(True,True), 'M12b':prepare_frontier,
                 'M17c':lambda:prepare_added(False,False), 'M16d':tail_probe}
    for mid in sorted(wanted):
        with mutant(mid):
            altered = outcome(callbacks[mid])
        assert altered != controls[mid], (mid, altered)
        print('single mutation', mid, 'baseline=', controls[mid], 'mutant=', altered, 'DISTINGUISHED')

issues = sum(not good for _,good in observed)
print('runtime observations:', len(observed), 'unresolved:', issues)
if args.expect_fixed and issues:
    raise SystemExit(1)
