"""Read-only bounded review probes for B-5a; no repository files are changed."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--repo', required=True)
args = ap.parse_args()
root = Path(args.repo).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests/v2_history_restore'))
import r4_helpers as R
from v2_history_diagnose import diagnose_history_bytes
from v2_history import History, validate_history
from v2_history.values import history_dict
from v2_persistence.codec import Snapshot, canonical_json
from v2_persistence.events import snapshot_dict
from v2_persistence.recompute import validate_snapshot
from v2_core.errors import CoreError

CANARY = 'https://review-canary.invalid/private/path'
VALUES = (None, True, False, -1, 0, 1.5, '', CANARY, '\ud800', [], {}, [None], {'unexpected': CANARY})
b = R.H.HB()
b.apply(R.D[1], 27.0)
b.apply(R.D[2], 28.0)
base = history_dict(b.events)
checks = 0
statuses = {}

def expected_count(doc, sv):
    records = doc.get('events')
    if not isinstance(records, list):
        return None
    # Independent exhaustive selection in ascending order; no call to B-5a helpers.
    good = []
    for k in range(1, len(records) + 1):
        try:
            if sv == 2:
                validate_history(History.from_dict(history_dict(records[:k])))
            else:
                validate_snapshot(Snapshot.from_dict(snapshot_dict(records[:k])))
            good.append(k)
        except (CoreError, KeyError, TypeError, ValueError, AttributeError, IndexError, OverflowError, RecursionError):
            pass
    return max(good) if good else None

def check(doc):
    global checks
    raw = canonical_json(doc).encode('utf-8')
    diag = diagnose_history_bytes(raw)
    d = diag.to_dict()
    assert d == diagnose_history_bytes(raw).to_dict()
    assert d['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert d['raw_size'] == len(raw)
    assert diag.digest == hashlib.sha256(canonical_json(d).encode('utf-8')).hexdigest()
    serialized = canonical_json(d)
    assert CANARY not in serialized
    assert CANARY not in repr(diag) + diag.summary()
    # Unsupported schema/core stops before any prefix is offered.
    sv = doc.get('schema_version')
    compatible = type(sv) is int and sv in (1, 2) and doc.get('core_sha') == base['core_sha']
    if not compatible:
        assert d['status'] == 'UNREADABLE'
        assert d['verified'] is None
    elif d['status'] in ('PREFIX_ONLY', 'NO_VALID_PREFIX'):
        expected = expected_count(doc, sv)
        actual = None if d['verified'] is None else d['verified']['count']
        assert actual == expected, (d['failure'], actual, expected)
    else:
        assert d['status'] == 'VALID'
        if sv == 2:
            validate_history(History.from_dict(doc))
        else:
            validate_snapshot(Snapshot.from_dict(doc))
    statuses[d['status']] = statuses.get(d['status'], 0) + 1
    checks += 1

for sv in (1, 2):
    doc = copy.deepcopy(base)
    doc['schema_version'] = sv
    check(doc)
    for key in sorted(doc):
        for value in VALUES:
            altered = copy.deepcopy(doc)
            altered[key] = copy.deepcopy(value)
            check(altered)
    for index in (0, 1, 2):
        for key in sorted(doc['events'][index]):
            for value in VALUES:
                altered = copy.deepcopy(doc)
                altered['events'][index][key] = copy.deepcopy(value)
                check(altered)

for maker, expected in ((lambda: R.H.example_m()[0].history(), 2),
                        (lambda: R.H.migrate(*R.H.example_m_empty_world()), 3)):
    doc = maker().to_dict()
    migration = next(e for e in doc['events'] if e['kind'] == 'SCHEMA_MIGRATION')
    migration['event_hash'] = '0' * 64
    diag = diagnose_history_bytes(canonical_json(doc).encode('utf-8'))
    assert diag.status == 'PREFIX_ONLY' and diag.verified['count'] == expected
print('JSON substitutions checked:', checks, 'statuses:', json.dumps(statuses, sort_keys=True))
print('Determinism, hashes, safe display and independent maximum-prefix checks: OK')
print('Migration counterexamples: count=2 and count=3, OK')

# Count all checker calls for the same damage position as D5-16, using a small
# history so the review does not rebuild the slow 260-APPLY fixture again.
from unittest.mock import patch
from v2_history_diagnose import diagnose as GD
counted = []
original_check = GD.validate_history
def counting_check(history):
    counted.append(len(history.events))
    return original_check(history)
damaged = copy.deepcopy(base)
damaged['events'][1]['event_hash'] = '0' * 64
with patch.object(GD, 'validate_history', counting_check):
    diag = diagnose_history_bytes(canonical_json(damaged).encode('utf-8'))
assert diag.verified['count'] == 1
assert counted == [3, 3, 2, 1], counted
print('Checker calls with n=3 and damage at index1:', counted,
      '(whole=1, prefix=3; failed prefixes=2). For n=261: total=262, prefix=261, failed prefixes=260.')
