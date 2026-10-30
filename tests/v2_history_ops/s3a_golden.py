"""Fixed S3-A inputs whose outputs must not change with the API-1 edit of v2_recovery (design 3.3, B2-02).

compute() runs a set of fixed S3-A requests (prepare, confirm, and make_records called directly) and returns a dict of
hashes. The expected values in test_b02 were produced by running this on the base commit adfdf765 (before any edit
of v2_recovery) and are pinned there. Test-only helper; the runtime never imports it.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (ROOT, os.path.join(ROOT, "tests", "v2_history"), os.path.join(ROOT, "tests", "v2_recovery"),
           os.path.join(ROOT, "tests", "v2_persistence")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import h_helpers as H  # noqa: E402  (read-only reuse of the existing helper)
import r_helpers as RH  # noqa: E402
from v2_persistence.codec import canonical_json, sha256_text  # noqa: E402
from v2_recovery.commands import make_records  # noqa: E402
from v2_recovery.common import basis_request_hash  # noqa: E402
from v2_recovery.project import Ctx  # noqa: E402

P = H.P
D = H.D


def _h(x):
    return sha256_text(canonical_json(x))


def _direct_make_records(snap, rs, cmds, ledger, check_d, rid):
    """make_records called as prepare_resolution_plan does, with a fixed basis."""
    ctx = Ctx(snap, rs, H.P.World().sessions, ledger, check_d)
    norm = [RH.R.common.normalize_command(c, "commands") for c in cmds]
    reason = RH.reason_for(norm)
    basis = {"request_id": rid, "commands": norm, "check_d": check_d, "reason_code": reason,
             "requested_at": "2026-06-01T00:00:00Z"}
    return make_records(ctx, ctx.records, norm, basis, basis_request_hash(basis))


def compute():
    out = {}
    # S3-A example M (ADDED, DECLARE, LATE by declaration reference) and M2 (CHANGED, ROW_REMOVED, DECLARE,
    # LATE by declaration reference, LATE by APPLY reference): every step is a real prepare + confirm
    for name, fn in (("m", H.example_m_world), ("m2", H.example_m2_world)):
        w, snap, rs, ledger, check_d = fn()
        out["%s_resolutions_digest" % name] = rs.digest
        out["%s_records" % name] = _h(rs.to_dict())
        eff = RH.R.resolve_observations(snap, rs, w.sessions, ledger, check_d)
        out["%s_effective_digest" % name] = eff.effective_digest
        # a further fixed request on the final state: ADDED against the first APPLY
        extra = P.obs("Z9", D[1], 44.0, hour=21)
        ledger2 = list(ledger) + [extra]
        cmds = [RH.ack(snap, "ADDED", D[1], [RH.fp(extra)])]
        plan = RH.plan_for(w, rs, cmds, ledger2, check_d, rid="g-1", snapshot=snap)
        out["%s_extra_plan_hash" % name] = plan.plan_hash
        out["%s_extra_make_records" % name] = _h(_direct_make_records(snap, rs, cmds, ledger2, check_d, "g-2"))
    # a world with no resolutions: CHANGED then ROW_REMOVED+ADDED batch, and a DECLARE
    w = RH.world(2)
    snap = w.snap()
    rs = RH.R.empty_resolutions()
    changed = P.obs("R1", D[1], 31.0, hour=21)
    other = P.obs("X1", D[2], 40.0, hour=21)
    ledger = [changed, w.ledger[1], other]
    cmds = [RH.ack(snap, "CHANGED", D[1], [RH.fp(changed)]), RH.ack(snap, "ADDED", D[2], [RH.fp(other)], seq=2)]
    out["w2_batch_plan_hash"] = RH.plan_for(w, rs, cmds, ledger, D[2], rid="g-3", snapshot=snap).plan_hash
    out["w2_batch_make_records"] = _h(_direct_make_records(snap, rs, cmds, ledger, D[2], "g-4"))
    w3 = RH.world(1)
    snap3 = w3.snap()
    cmds = [RH.declare(D[2])]
    out["w1_declare_plan_hash"] = RH.plan_for(w3, rs, cmds, list(w3.ledger), D[3], rid="g-5",
                                              snapshot=snap3).plan_hash
    out["w1_declare_make_records"] = _h(_direct_make_records(snap3, rs, cmds, list(w3.ledger), D[3], "g-6"))
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(compute(), indent=1, sort_keys=True))
