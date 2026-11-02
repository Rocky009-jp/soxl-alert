"""Independent B-3 review probes. Read-only against --repo; uses its synthetic test helpers.

The final observation concerns only direct construction outside confirm_restart_plan;
it is not a failure of a supported prepare/confirm path. No real credentials or I/O.
"""
import argparse
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
args = parser.parse_args()
root = Path(args.repo).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests' / 'v2_history_restart'))
import r3_helpers as R
from v2_core.errors import CoreError

checks = 0

def expect(code, fn):
    global checks
    try:
        fn()
    except CoreError as exc:
        assert exc.code == code, (exc.code, code)
        checks += 1
    else:
        raise AssertionError('expected ' + code)

b = R.example_u()
h, w, D = b.history(), b.w, R.D
plan = R.prep(h, w, D[3], D[3], 'review-r1')
res = R.confirm(plan, h, w)
assert res.status == 'CONFIRMED_IN_MEMORY'
assert len(res.history.events) == len(h.events) + 1
assert res.history.events[:-1] == h.events
assert not res.committed and not res.committable
checks += 1
again = R.confirm(plan, res.history, w)
assert again.status == 'NO_CHANGE' and again.history is res.history
checks += 1
expect('history_request_conflict', lambda: R.prep(res.history, w, D[3], D[3], 'review-r1'))
expect('restart_invalid', lambda: R.prep(h, w, D[1], D[3], 'review-r2'))
bad = R.refreshed(plan, lambda basis: basis.__setitem__('expected_state_digest', 'f' * 64))
expect('history_plan_mismatch', lambda: R.confirm(bad, res.history, w))
later = R.H.HB(world=w, events=res.history.events)
later.declare(D[4], 'review-q1')
expect('history_plan_stale', lambda: R.confirm(plan, later.history(), w))
expect('sessions_invalid', lambda: R.confirm(plan, h, w, sessions=[]))
expect('target_not_after_boundary', lambda: R.O.project_history_ledger(res.history, w.sessions, w.ledger, D[3]))
expect('ledger_mismatch', lambda: R.prep(h, w, D[3], D[3], 'review-r3', ledger=[]))
assert checks == 9
print('supported-path controls: 9/9 OK')

# Malformed, hash-recomputed plan JSON must fail with a fixed CoreError, never
# leak a raw TypeError/KeyError. This is supplementary, not a contract change.
cases = 0
for key in plan.basis:
    for replacement in (None, False, True, -1, 0, 2.0, [], {}, 'x'):
        if R.cj(plan.basis[key]) == R.cj(replacement):
            continue
        malformed = R.refreshed(plan, lambda basis, k=key, v=replacement: basis.__setitem__(k, v))
        try:
            R.confirm(malformed, h, w)
        except CoreError:
            cases += 1
        else:
            raise AssertionError('accepted malformed plan field: ' + key)
print('malformed-plan cases refused with CoreError:', cases)

# P-01: direct construction has no documented runtime validation. The normal
# confirm path only passes constants, immutable History and a validated str hash.
external = {'items': []}
direct = R.X.RestartConfirmResult('CONFIRMED_IN_MEMORY', h, external)
external['items'].append(1)
assert direct.plan_hash['items'] == [1]
direct.plan_hash['items'].append(2)
assert external['items'] == [1, 2]
synthetic = 'https://example.invalid/synthetic-only'
assert synthetic in repr(R.X.RestartConfirmResult(synthetic, h, '0' * 64))
print('P-01 direct-constructor-only observation: shared malformed hash; unchecked status repr')
