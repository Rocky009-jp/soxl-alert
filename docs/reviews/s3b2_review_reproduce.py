"""Offline B-2 review probes. No repository file is changed.

Run: python -B s3b2_review_reproduce.py --repo <checkout> [--expect-fixed]
The fixed flag applies to R-01/R-02. R-03 always demonstrates that B03x is
distinguishable; its new regression and corrected mutation report are reviewed separately.
"""
import argparse
import copy
import pathlib
import sys
from unittest import mock


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()
    root = pathlib.Path(args.repo).resolve()
    sys.path[:0] = [str(root), str(root / "tests" / "v2_history_ops")]
    import ho_helpers as T
    import v2_history_ops as O
    from v2_history_ops.chain import Chain
    from v2_recovery.facts import LedgerContext
    from v2_recovery.project import resolve_core

    issues, controls = [], []

    def observed(name, changed):
        issues.append((name, bool(changed)))
        print(name, "ISSUE" if changed else "FIXED")

    def mutate(value, action):
        try:
            action(value)
        except (AttributeError, TypeError):
            pass  # an immutable result may reject the write instead of copying

    for label, raw in (("dict", {"items": []}), ("list", [])):
        batch = O.HistoryAppendBatch.from_dict({"body": {}, "batch_hash": raw})
        before, old_hash = batch.to_dict(), hash(batch)
        got = batch.batch_hash
        mutate(got, lambda x: x["items"].append("changed") if isinstance(x, dict) else x.append("changed"))
        observed("R01_batch_hash_" + label, batch.to_dict() != before)
        controls.append(("stable_object_hash_" + label, hash(batch) == old_hash))

    b = T.H.HB()
    b.apply(T.D[1], 27.0)
    history = b.history()

    def facts():
        return Chain(history, T.V.validate_history(history)).facts

    ap = facts().applies[0]
    old = ap.seq
    mutate(ap, lambda x: setattr(x, "seq", 99))
    observed("R02_fixed_apply_seq", ap.seq != old)
    ap = facts().applies[0]
    old = copy.deepcopy(ap.context)
    mutate(ap.context, lambda x: x[0].__setitem__("confirmed", False))
    observed("R02_fixed_apply_context", ap.context != old)
    ap = facts().applies[0]
    old = len(ap.stored_sessions.sessions)
    mutate(ap.stored_sessions.sessions, lambda x: x.clear())
    observed("R02_fixed_apply_sessions", len(ap.stored_sessions.sessions) != old)
    f = facts()
    ctx = LedgerContext.from_facts(f, b.w.sessions, [], T.D[2])
    before = T.outcome(resolve_core, ctx, [], history.digest, "resolutions")
    mutate(f.applies, lambda x: x.clear())
    after = T.outcome(resolve_core, ctx, [], history.digest, "resolutions")
    controls.append(("missing_decision_originally_rejected", before[0:2] == ("err", "ledger_mismatch")))
    observed("R02_facts_applies_changes_projection", after[0] == "ok")
    f = facts()
    mutate(f.by_seq, lambda x: x.clear())
    observed("R02_facts_by_seq", len(f.by_seq) == 0)
    f = facts()
    decision = f.decision_cols(1)
    decision["record_id"] = "changed"
    controls.append(("decision_cols_is_already_a_copy", f.decision_cols(1)["record_id"] != "changed"))
    plan = O.HistoryResolutionPlan.from_dict({"basis": {}, "plan_hash": {"items": []}})
    plan.plan_hash["items"].append("changed")
    controls.append(("plan_hash_is_already_a_copy", plan.plan_hash == {"items": []}))

    # Valid history: G, APPLY D1, DECLARE D2, RESTORE(point=1,DROP=2), RESTART D4.
    # D2 is only next(D1) in the active APPLY; its close_at is intentionally ignored.
    # Including the retired declaration adds a full comparison of D2 and stops it.
    b = T.H.HB()
    b.apply(T.D[1], 27.0)
    b.declare(T.D[2], "q1")
    b.restore(1, {2: "DROP"}, "q2")
    b.restart(T.D[4], "q3")
    h = b.history()
    check = T.V.validate_history(h)
    sl = T.P.make_sessions(overrides={T.D[2]: lambda s: s.__class__(
        s.date, s.open_at, s.close_at.replace(hour=15), s.confirmed)})
    regular = T.outcome(O.project_history_ledger, h, sl, b.w.ledger, T.D[5])
    real = Chain._facts

    def b03x(self):
        old = self.resolutions
        self.resolutions = [r for r in self.events if r["kind"] == "DECLARE_MISSING" and r["replay_of"] is None]
        try:
            return real(self)
        finally:
            self.resolutions = old

    with mock.patch.object(Chain, "_facts", b03x):
        mutant = T.outcome(O.project_history_ledger, h, sl, b.w.ledger, T.D[5])
    distinguished = (regular[0] == "ok" and mutant[:3] == ("err", "session_context_mismatch", "sessions"))
    print("R03_B03x", "DISTINGUISHED" if distinguished else "UNEXPECTED", "effective", check.effective_seqs)
    for name, ok in controls:
        print("CONTROL", name, "OK" if ok else "FAILED")
    runtime_ok = all(changed != args.expect_fixed for _name, changed in issues)
    print("runtime_probes", len(issues), "controls", len(controls), "mutation_counterexamples", 1)
    return 0 if runtime_ok and distinguished and all(ok for _name, ok in controls) else 1


if __name__ == "__main__":
    sys.exit(main())

