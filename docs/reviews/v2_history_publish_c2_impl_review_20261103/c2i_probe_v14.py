"""C-2 implementation review, mutant V14 (the v1 snapshot is not validated before the confirm step): a single fault gives
the same code either way, because confirm_migration_plan validates the snapshot too; the two orders differ only when the
plan hash is also wrong. Run from the repository root."""
import json, os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tests", "v2_history_publish"))
import c2_helpers as X  # noqa: E402
from v2_persistence.codec import decode_snapshot  # noqa: E402
U = X.U
c = X.migration_case()
doc = json.loads(c.data.decode("utf-8"))


def find_invalid():
    """A text that decode_snapshot accepts and validate_snapshot refuses (one leaf changed)."""
    from v2_persistence.recompute import validate_snapshot
    def leaves(x, p=()):
        if isinstance(x, dict):
            for k in x:
                yield from leaves(x[k], p + (k,))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from leaves(v, p + (i,))
        else:
            yield p, x
    for path, v in leaves(doc):
        for nv in ([v + 1] if type(v) in (int, float) else []) + ["zz"]:
            d = json.loads(json.dumps(doc))
            t = d
            for k in path[:-1]:
                t = t[k]
            t[path[-1]] = nv
            data = json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")
            try:
                s = decode_snapshot(data.decode("utf-8"))
            except X.CoreError:
                continue
            try:
                validate_snapshot(s)
            except X.CoreError:
                return path, data
    return None, None


path, bad = find_invalid()
print("leaf", path)
print("alone       :", X.err(U.publish_migration, c.plan, c.plan.plan_hash, bad, c.rs, c.w.sessions, c.ledger))
print("with a wrong confirmed hash:", X.err(U.publish_migration, c.plan, X.ZERO, bad, c.rs, c.w.sessions, c.ledger))
