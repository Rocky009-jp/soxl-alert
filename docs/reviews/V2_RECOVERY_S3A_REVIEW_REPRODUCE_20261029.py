"""Read-only reproduction for S3-A review R-01/R-02 at 3b71816.

Run: python -B this_script.py --repo PATH [--expect-fixed]
Uses synthetic fixtures. No market, notification, network or store operations.
The existing fixture import disables Python sockets; this is not OS-level isolation.
"""
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--expect-fixed", action="store_true")
args = parser.parse_args()
root = Path(args.repo).resolve()
sys.path[:0] = [str(root), str(root / "tests" / "v2_recovery")]
import r_helpers as H
from v2_recovery import ResolutionPlan, confirm_resolution_plan
from v2_persistence.errors import PersistenceError

w = H.world(1)
snapshot, resolutions = w.snap(), H.R.empty_resolutions()
extra = H.P.obs("B1", H.D[1], 40.0, hour=21)
ledger = list(w.ledger) + [extra]
commands = [H.ack(snapshot, "ADDED", H.D[1], [H.fp(extra)])]
plan = H.plan_for(w, resolutions, commands, ledger, H.D[1])
marker = "https://example.invalid/SYNTHETIC_REVIEW_MARKER"

def accepted_rejection(error):
    return (isinstance(error, PersistenceError)
            and error.code in ("resolution_invalid", "resolution_plan_mismatch")
            and error.field == "plan"
            and marker not in str(error) + repr(error))

def observe(label, action, expect_defect=True):
    try:
        defect = bool(action())
        exception = None
    except Exception as error:
        defect = not accepted_rejection(error)
        exception = type(error).__name__
    print(json.dumps({"probe": label, "defect_observed": defect, "exception": exception}))
    expected = False if args.expect_fixed else expect_defect
    return defect == expected

def bad_plan():
    data = plan.to_dict()
    data["basis"]["status"] = marker
    data["basis"]["request_id"] = marker
    data["basis"]["commands"][0]["d"] = marker
    return ResolutionPlan.from_dict(data)

def bad_summary():
    return marker in repr(bad_plan().summary())

def missing_summary():
    value = ResolutionPlan.from_dict({"basis": {}, "plan_hash": "a" * 64})
    value.summary()
    return False

def numeric_plan():
    data = plan.to_dict()
    data["basis"]["request_id"] = 10 ** 5000
    value = ResolutionPlan.from_dict(data)
    confirm_resolution_plan(value, value.plan_hash, snapshot, resolutions, w.sessions, ledger)
    return False

def deep_plan():
    data = plan.to_dict()
    node = {}
    data["basis"] = node
    for _ in range(1200):
        node["x"] = {}
        node = node["x"]
    value = ResolutionPlan.from_dict(data)
    confirm_resolution_plan(value, value.plan_hash, snapshot, resolutions, w.sessions, ledger)
    return False

checks = [
    observe("R1_repr", lambda: marker in repr(bad_plan())),
    observe("R1_summary", bad_summary),
    observe("R1_missing_keys", missing_summary),
    observe("R2_deep_input", deep_plan),
]
# Old Python versions without an integer conversion limit do not have this ValueError.
digit_limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
if digit_limit and digit_limit < 5001:
    checks.append(observe("R2_numeric_serialization", numeric_plan))
else:
    print(json.dumps({"probe": "R2_numeric_serialization", "not_applicable": True}))
good = confirm_resolution_plan(plan, plan.plan_hash, snapshot, resolutions, w.sessions, ledger)
control_ok = good.status == "CONFIRMED_IN_MEMORY" and not good.committed
print(json.dumps({"control_valid_plan": control_ok, "expected_observations": all(checks),
                  "mode": "expect-fixed" if args.expect_fixed else "expect-original-defects"}))
sys.exit(0 if all(checks) and control_ok else 1)
