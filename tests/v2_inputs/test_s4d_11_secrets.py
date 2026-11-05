"""S4D-16: the provenance has exactly the documented keys with text and int values; no text of the remote path or of a failed
git command (the mark SECRETMARK_), of a fetch error or of a response body leaves load_inputs, the notice, the reports or the
commits; the detail of every error is a date or nothing; no error is chained to another."""
import re
import unittest

import s4d_helpers as H

I = H.I
KEYS = {"calendar_sha256", "market_through", "market_sha256", "market_commit", "pinned_by", "fetch_count", "ledger_commit"}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
HEX64, HEX40 = re.compile(r"[0-9a-f]{64}"), re.compile(r"[0-9a-f]{40}")


def sweep(case, rig, report, inp, extra=()):
    """Everything this run showed or stored: the failure, the provenance, the rows, the reports, the texts, the bytes of the
    pins and the history and the commits."""
    case.see(inp.failure, inp.provenance, inp.raw_observations, report, list(rig.sender.texts), list(extra))
    if inp.failure is not None:
        case.see(repr(inp.failure), str(inp.failure), inp.failure.args)
    for ref in ("v2-market", "v2-state", "v2-outbox", "v2-ledger"):
        if rig.remote.sha(ref) is not None:
            case.see(rig.remote.files(ref), [(c["subject"], c["author"], c["committer"]) for c in rig.remote.log(ref)])


class Provenance(H.Case):
    def test_a_good_run_has_exactly_the_seven_keys_with_text_and_int_values(self):
        rig = H.Rig(self, start=H.START)
        report, inp = rig.morning(H.D, H.Provider(H.D))
        self.assertIsNone(inp.failure)
        p = inp.provenance
        self.assertEqual(set(p), KEYS)
        for key, value in p.items():
            self.assertIn(type(value), (str, int), key)
        self.assertIs(type(p["fetch_count"]), int)
        self.assertRegex(p["calendar_sha256"], HEX64)
        self.assertRegex(p["market_sha256"], HEX64)
        self.assertRegex(p["market_commit"], HEX40)
        self.assertRegex(p["ledger_commit"], HEX40)
        self.assertRegex(p["market_through"], DATE)
        self.assertIn(p["pinned_by"], ("this", "other", "existing"))
        self.assertEqual(p["calendar_sha256"], I.calendar_sha256())

    def test_a_failure_keeps_only_the_keys_decided_so_far(self):
        for name in H.CODES:
            with self.subTest(code=name):
                rig, report, inp, day = H.run_case(self, name)
                p = inp.provenance
                self.assertTrue(set(p) <= KEYS, p)
                self.assertTrue({"calendar_sha256", "fetch_count"} <= set(p))
                for value in p.values():
                    self.assertIn(type(value), (str, int))
        rig, report, inp, day = H.run_case(self, "input_market_fetch_failed")
        self.assertEqual(set(inp.provenance), {"calendar_sha256", "fetch_count"})
        self.assertEqual(inp.provenance["fetch_count"], 1)
        rig, report, inp, day = H.run_case(self, "input_ledger_missing")
        self.assertEqual(set(inp.provenance), KEYS - {"ledger_commit"})


class Secrets(H.Case):
    def test_no_mark_leaves_in_any_failure_or_in_a_good_run(self):
        for name in H.CODES:
            with self.subTest(code=name):
                rig, report, inp, day = H.run_case(self, name)
                sweep(self, rig, report, inp)
                self.assertNoMark()
                self.assertCleanError(inp.failure)
                self.shown.clear()
        rig = H.Rig(self, start=H.START)
        report, inp = rig.morning(H.D, H.Provider(H.D))
        sweep(self, rig, report, inp)
        self.assertNoMark()

    def test_an_unreachable_remote_is_a_returned_git_failure_that_shows_no_path(self):
        rig = H.Rig(self, start=H.START)
        rig.sync_ledger(H.D)
        with H.C.Gone(rig.remote):
            inp, _now = rig.inputs(H.D, H.Provider(H.D))
        self.see(inp.failure, inp.provenance, repr(inp.failure), str(inp.failure))
        self.assertEqual((inp.failure.code, inp.failure.field, inp.failure.detail), ("input_git_failed", "inputs", None))
        self.assertNoMark()
        self.assertCleanError(inp.failure)

    def test_a_failed_git_command_that_says_the_mark_shows_it_nowhere(self):
        rig = H.Rig(self, start=H.START)
        rig.sync_ledger(H.D)
        for command in (("fetch", "ls-remote"), ("push",), ("hash-object",), ("mktree",), ("commit-tree",), ("cat-file",),
                        ("ls-tree",)):
            git = H.C.Scripted(rig.clone.dir, rule=H.C.failing(*command))
            inp, _now = rig.inputs(H.D, H.Provider(H.D), git=git)
            self.see(inp.failure, inp.provenance, repr(inp.failure), str(inp.failure))
            self.assertNoMark()
            if inp.failure is not None:
                self.assertCleanError(inp.failure)
                self.assertIn(inp.failure.code, ("input_git_failed", "input_market_pin_failed"), command)

    def test_the_raised_errors_are_clean_too(self):
        rig = H.Rig(self)
        with self.assertRaises(H.InputError) as cm:
            rig.inputs("2029-01-01", H.Provider(H.D))
        self.see(cm.exception, repr(cm.exception))
        self.assertCleanError(cm.exception)
        with self.assertRaises(H.InputError) as cm:
            I.load_inputs(rig.clone.git, H.Provider(H.D), None, H.REFS, H.C.clock)
        self.assertCleanError(cm.exception)
        self.assertNoMark()


class Details(H.Case):
    def test_the_detail_of_every_error_is_a_date_or_nothing(self):
        seen = set()
        for name in H.CODES:
            rig, report, inp, day = H.run_case(self, name)
            detail = inp.failure.detail
            self.assertTrue(detail is None or DATE.fullmatch(detail), (name, detail))
            seen.add(detail)
            self.assertIn(report.code, (name,))
        self.assertTrue({None, "2026-07-28", "2010-02-11", "2026-07-03", "2026-07-27"} <= seen)


if __name__ == "__main__":
    unittest.main()
