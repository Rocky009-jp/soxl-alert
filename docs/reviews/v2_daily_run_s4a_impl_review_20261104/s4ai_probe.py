"""Probes for the S4-A implementation review (c15ab18). Run from the repository root of the tested commit:
  PYTHONDONTWRITEBYTECODE=1 python -B <this file> <repo>
X1: a gap consumed by a STALE (or STOPPED) run never appears in any morning text.
X2: render_message runs outside the handler: a CoreError raised while the DONE text is made leaves run_morning,
    after the day was saved (the next morning repeats it).
X3: after an uncertain save of the target that reconciles as PUBLISHED, target_status is ALREADY_APPLIED and the text
    equals the text of a normal run."""
import os, sys, shutil
repo = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(repo, "tests", "v2_daily_run"))
os.chdir(repo)
import s4a_helpers as S
import v2_daily_run.run as run_module
from unittest import mock
from v2_core.errors import InputError
D, P = S.D, S.P

def root():
    r = S.make_root(); return r

def x1():
    print("== X1 gap under STALE")
    r = root()
    try:
        w = P.World(0, unconfirmed=(D[4],))
        S.decide(w, [1, 3, 5])
        st = S.real_store(r, w)
        a = S.run(st, w, S.now_at(D[5]))
        print("run1:", a.outcome, a.code, [(c.d, c.gap, c.skipped_sessions) for c in a.consumed])
        print("run1 text mentions D2 (%s): %s" % (D[2], D[2] in a.message))
        w2 = P.World(0)                      # the next morning: D4 is confirmed now, same ledger
        w2.ledger = list(w.ledger)
        b = S.run(S.HistoryFileStore(r, writable=True, durability=S.DURABILITY), w2, S.now_at(D[5]))
        print("run2:", b.outcome, [(c.d, c.gap, c.skipped_sessions) for c in b.consumed])
        print("run2 text mentions D2 (%s): %s ; mentions D4 (%s): %s" % (D[2], D[2] in b.message, D[4], D[4] in b.message))
        return (D[2] in a.message) or (D[2] in b.message)
    finally:
        shutil.rmtree(r, True)

def x2():
    print("== X2 CoreError while the DONE text is made")
    r = root()
    try:
        w = P.World(0); S.decide(w, [1, 2])
        st = S.real_store(r, w)
        def boom(result):
            raise InputError("price_not_finite_positive", "soxl_close")
        with mock.patch.object(run_module, "render_message", boom):
            try:
                rep = S.run(st, w, S.now_at(D[2])); print("returned", rep.outcome); leaked = False
            except InputError as e:
                print("leaked:", type(e).__name__, e.code); leaked = True
        print("APPLY saved before the error:", S.applies_of(r))
        with mock.patch.object(run_module, "render_message", boom):
            try:
                S.run(S.HistoryFileStore(r, writable=True, durability=S.DURABILITY), w, S.now_at(D[2])); again = False
            except InputError:
                again = True
        print("the next run leaks again:", again)
        from v2_core.display import bstar
        from v2_core.fixture import PRICE_DEF_SOXL_CLOSE
        from decimal import Decimal
        try:
            bstar(Decimal("1E+27"), PRICE_DEF_SOXL_CLOSE); print("bstar 1e27 ok")
        except Exception as e:
            print("bstar(1e27) raises", type(e).__name__, "(not a CoreError; a validated MarketSeries accepts 1e27)")
        return leaked
    finally:
        shutil.rmtree(r, True)

def x3():
    print("== X3 uncertain save of the target")
    out = []
    for plan in ({}, {2: "uncertain_after_write"}):
        r = root()
        try:
            w = P.World(0); S.decide(w, [1, 2])
            st = S.Flaky(S.real_store(r, w), plan)
            rep = S.run(st, w, S.now_at(D[2]))
            out.append((rep.outcome, rep.target_status, [c.d for c in rep.consumed], rep.message, S.raw(r), st.count("publish"), st.count("reconcile")))
        finally:
            shutil.rmtree(r, True)
    a, b = out
    print("normal :", a[0], a[1], a[2], "publish", a[5], "reconcile", a[6])
    print("restart:", b[0], b[1], b[2], "publish", b[5], "reconcile", b[6])
    print("same text:", a[3] == b[3], " same bytes:", a[4] == b[4])
    return a[1] != b[1]

def x2b():
    print("== X2b a SOXL close of 1e27 on D (series stub that reports it, as a validated MarketSeries would accept)")
    from decimal import Decimal
    import v2_core.fixture as F
    try:
        F.MarketSeries(["2026-03-02"], [1.0], {}, {}, [], soxl_close={"2026-03-02": 1e27},
                       meta={"price_definition": F.PRICE_DEF_SOXX, "soxl_close_definition": F.PRICE_DEF_SOXL_CLOSE})
        print("MarketSeries accepts soxl_close=1e27: True")
    except Exception as e:
        print("MarketSeries rejects 1e27:", type(e).__name__, getattr(e, "code", e))
    class Big(P.StubSeries):
        def through(self, d):
            return Big([r for r in self.rows.values() if r.date <= d])
        def soxl_close(self, d):
            return Decimal("1E+27") if d == D[2] else None
    r = root()
    try:
        w = P.World(0); w.series = Big(list(w.series.rows.values())); S.decide(w, [1, 2])
        st = S.real_store(r, w)
        res = []
        for i in range(2):
            try:
                rep = S.run(S.HistoryFileStore(r, writable=True, durability=S.DURABILITY), w, S.now_at(D[2]))
                res.append(rep.outcome)
            except Exception as e:
                res.append(type(e).__name__)
        print("two mornings:", res, "APPLY saved:", S.applies_of(r))
        return res
    finally:
        shutil.rmtree(r, True)

r1, r2, r3, r4 = x1(), x2(), x3(), x2b()
print("RESULT X1 gap shown in some text:", r1, "| X2 leaked:", r2, "| X3 target_status differs:", r3, "| X2b:", r4)
