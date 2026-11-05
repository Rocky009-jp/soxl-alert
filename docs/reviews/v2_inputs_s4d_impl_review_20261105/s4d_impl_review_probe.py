"""S4-D implementation review probes (read-only; nothing is changed in the repository).
usage: python s4d_impl_review_probe.py <repo> <probe>
  count : the provenance fetch_count when a response cannot be read (Y1)
  hole  : a past day missing from the source after it was pinned (Y2)
  sess  : the confirmed sessions of a returned failure (Y3)
"""
import os
import sys
import unittest

REPO, WHICH = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(REPO, "tests", "v2_inputs"))
os.chdir(REPO)
import s4d_helpers as H  # noqa: E402

I = H.I


class Y1(H.Case):
    def test_count(self):
        for sym in ("SOXX", "SPY", "IEF", "SOXL"):
            rig = H.Rig(self, start=H.START)
            prov = H.Provider(H.D, bad={sym: b"not json"})
            report, inp = rig.morning(H.D, prov)
            print("Y1 bad=%s code=%s calls=%d provenance.fetch_count=%s" % (
                sym, inp.failure.code, prov.calls, inp.provenance.get("fetch_count")))
        rig = H.Rig(self, start=H.START)
        rows = H.research(); rows["SOXL"][H.D] = (2e6, 2e6)
        prov = H.Provider(H.D, rows=rows)
        report, inp = rig.morning(H.D, prov)
        print("Y1 value_invalid(SOXL) code=%s calls=%d provenance.fetch_count=%s" % (
            inp.failure.code, prov.calls, inp.provenance.get("fetch_count")))
        rig = H.Rig(self, start=H.START)
        prov = H.Provider(H.D, fail=True)
        report, inp = rig.morning(H.D, prov)
        print("Y1 fetch_failed code=%s calls=%d provenance.fetch_count=%s" % (
            inp.failure.code, prov.calls, inp.provenance.get("fetch_count")))


class Y2(H.Case):
    def test_hole(self):
        rig = H.Rig(self, start="2026-07-20")
        days = H.table_days("2026-07-21", "2026-07-31")
        for d in days[:4]:
            report, inp = rig.morning(d, H.Provider(d))
            print("Y2 %s %s %s pinned_by=%s" % (d, report.run_outcome, report.kind, inp.provenance.get("pinned_by")))
        # the source now lacks a past, already pinned day (one symbol), or answers null for it
        rows = H.research(); del rows["SPY"]["2026-03-05"]
        for d in days[4:7]:
            report, inp = rig.morning(d, H.Provider(d, rows=rows))
            print("Y2 %s (SPY 2026-03-05 missing at the source) %s code=%s detail=%s kind=%s through=%s" % (
                d, report.run_outcome, report.code, inp.failure and inp.failure.detail, report.kind,
                inp.provenance.get("market_through")))
        rows2 = H.research(); rows2["IEF"]["2026-04-14"] = (None, None)
        d = days[7]
        report, inp = rig.morning(d, H.Provider(d, rows=rows2))
        print("Y2 %s (IEF 2026-04-14 null at the source) %s code=%s detail=%s" % (
            d, report.run_outcome, report.code, inp.failure and inp.failure.detail))
        report, inp = rig.morning(d, H.Provider(d))
        print("Y2 %s (source fixed) %s %s" % (d, report.run_outcome, report.kind))


class Y3(H.Case):
    def test_sess(self):
        for name in ("input_ledger_missing", "input_market_response_invalid", "input_market_pin_invalid"):
            rig, report, inp, day = H.run_case(self, name)
            conf = [s.date for s in inp.sessions.sessions if s.confirmed]
            print("Y3 %s confirmed_through=%s target=%s" % (name, conf[-1] if conf else None, day))


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromName({"count": "Y1", "hole": "Y2", "sess": "Y3"}[WHICH],
                                                     sys.modules[__name__])
    r = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if r.wasSuccessful() else 1)
