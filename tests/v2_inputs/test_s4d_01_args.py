"""S4D-02: every wrong argument is an InputError (input_args_invalid, field inputs, no detail) before anything is called:
the git object and the fetch function are not touched (zero calls). A naive datetime and a date are refused as `now`."""
import unittest
from datetime import date, datetime, timedelta, timezone

import s4d_helpers as H

I = H.I

NOW = datetime(2026, 7, 28, 7, 40, tzinfo=H.JST)


class NoGit(object):
    """A git object that must not be used: any attribute access fails the test."""

    def __getattr__(self, name):
        raise AssertionError("git was used: " + name)


class Counting(object):
    def __init__(self):
        self.calls = 0

    def __call__(self, *a):
        self.calls += 1
        return b""


class Args(H.Case):
    def refuse(self, **given):
        fetch = Counting()
        args = {"git": NoGit(), "fetch": fetch, "now": NOW, "refs": dict(H.REFS), "clock": H.C.clock}
        args.update(given)
        with self.assertRaises(H.InputError) as cm:
            I.load_inputs(args["git"], args["fetch"], args["now"], args["refs"], args["clock"])
        err = self.see(cm.exception)
        self.assertEqual((err.code, err.field, err.detail), ("input_args_invalid", "inputs", None))
        self.assertEqual(fetch.calls, 0)
        self.assertCleanError(err)
        return err

    def test_now_must_be_an_aware_datetime(self):
        for bad in (datetime(2026, 7, 28, 7, 40), date(2026, 7, 28), "2026-07-28T07:40+09:00", None, 3, 1.5,
                    1785000000, b"2026-07-28"):
            self.refuse(now=bad)

    def test_the_fetch_and_the_clock_must_be_callable(self):
        for bad in (None, 3, "fetch", b"x", [], {}):
            self.refuse(fetch=bad)
            self.refuse(clock=bad)

    def test_refs_must_be_the_two_names_in_the_shape_of_the_store(self):
        good = "v2-market"
        bad_refs = (None, 3, "v2-market", ["market", "ledger"], ("market", "ledger"), {}, {"market": good},
                    {"ledger": good}, {"market": good, "ledger": "v2-ledger", "state": "v2-state"},
                    {"market": good, "other": "v2-ledger"}, {"Market": good, "Ledger": "v2-ledger"}, {1: good, 2: good})
        for bad in bad_refs:
            self.refuse(refs=bad)
        shapes = (None, 3, b"v2-ledger", "", "UP", "-a", "a" * 41, "a_b", "a/b", "a b", "a\n", "é", "a.b", "refs/heads/a",
                  ["v2-ledger"], True)
        for bad in shapes:
            self.refuse(refs={"market": good, "ledger": bad})
            self.refuse(refs={"market": bad, "ledger": "v2-ledger"})
        self.refuse(refs={"market": good, "ledger": good})            # one ref for both is refused (review P-05)

    def test_a_shape_of_the_longest_valid_name_is_accepted_by_the_check(self):
        # the check alone: with an object that fails on its first use the call gets as far as the first git use
        for name in ("a", "0", "v2-market", "a" * 40):
            with self.assertRaises(AssertionError):
                I.load_inputs(NoGit(), Counting(), NOW, {"market": name, "ledger": "v2-ledger"}, H.C.clock)

    def test_the_other_public_functions_refuse_a_naive_now_too(self):
        for bad in (datetime(2026, 7, 28), date(2026, 7, 28), None, "x"):
            for call in (lambda b=bad: I.build_sessions(b, None), lambda b=bad: I.coverage_failure(b)):
                with self.assertRaises(H.InputError) as cm:
                    call()
                self.assertEqual((cm.exception.code, cm.exception.field), ("input_args_invalid", "inputs"))

    def test_chart_url_refuses_a_symbol_or_a_date_it_does_not_know(self):
        for bad in (None, "", "soxx", "QQQ", b"SOXX", 3, "SOXX ", "SOXX\n"):
            with self.assertRaises(H.InputError) as cm:
                I.chart_url(bad, "2010-02-11", "2026-07-29")
            self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.detail),
                             ("input_args_invalid", "inputs", None))
        for bad in (None, "", "2010-2-11", "20100211", "2010-02-30", 3, "2010-02-11T00:00"):
            with self.assertRaises(H.InputError):
                I.chart_url("SOXX", bad, "2026-07-29")
            with self.assertRaises(H.InputError):
                I.chart_url("SOXX", "2010-02-11", bad)

    def test_a_valid_call_does_not_raise_args_invalid(self):
        # a different zone is fine; the call then fails on the git object, which proves the arguments passed
        for zone in (timezone.utc, timezone(timedelta(hours=-5)), H.JST):
            with self.assertRaises(AssertionError):
                I.load_inputs(NoGit(), Counting(), NOW.astimezone(zone), dict(H.REFS), H.C.clock)


if __name__ == "__main__":
    unittest.main()
