"""Read-only B-5 design review probes against the unchanged ac21980 code.

Only existing test builders and validators; no B-5 runtime or file writes.
"""
import argparse
import copy
from pathlib import Path
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
args = ap.parse_args()
root = Path(args.repo).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests/v2_history_restore'))
import r4_helpers as R
from v2_core.errors import CoreError
from v2_history import History, decode_history, validate_history
from v2_history.values import history_dict

def check_prefixes(events):
    results = []
    for k in range(len(events), 0, -1):
        try:
            chk = validate_history(History.from_dict(history_dict(events[:k])))
            results.append((k, 'PASS', chk.migrated))
        except CoreError as e:
            results.append((k, e.code, getattr(e, 'rule', None)))
    return results

b, _ = R.H.example_m()
validate_history(b.history())
events = copy.deepcopy(b.events)
mi = next(i for i, e in enumerate(events) if e['kind'] == 'SCHEMA_MIGRATION')
events[mi]['event_hash'] = '0' * 64
results = check_prefixes(events)
assert mi == 7
assert [k for k, status, _ in results if status == 'PASS'] == [2, 1], results
assert all(rule == 'origin' for k, status, rule in results if 3 <= k <= 7), results
print('MIGRATION corrupt, earlier migrated ACK: migration_seq=7; trial outcomes:', results)
print('Maximum verified prefix: count=2, head_seq=1, migrated=False; discarded indices=2..7')

w, snap, resolutions, ledger, check_d = R.H.example_m_empty_world()
h = R.H.migrate(w, snap, resolutions, ledger, check_d)
validate_history(h)
events = copy.deepcopy(h.events)
mi = next(i for i, e in enumerate(events) if e['kind'] == 'SCHEMA_MIGRATION')
events[mi]['event_hash'] = '0' * 64
results = check_prefixes(events)
assert mi == 3
assert [k for k, status, _ in results if status == 'PASS'] == [3, 2, 1], results
print('MIGRATION corrupt, no earlier ACK: trial outcomes:', results)
print('Maximum verified prefix: count=3, head_seq=2, migrated=False; discarded index=3')

assert decode_history('[]').to_dict() == []
print('Top-level [] passes strict JSON decoding; rejection belongs to schema stage.')
print('B-5a does not exist yet: these are existing-validator probes, not diagnosis API tests.')
