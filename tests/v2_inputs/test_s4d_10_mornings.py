"""S4D-15: six mornings from the genesis of 2026-07-20 through load_inputs, guarded_store and morning_job (the accepted S4-A,
S4-B and S4-C parts) give a verdict each time, and the same six mornings over the research fixture directly give the same
reports, the same history.json bytes and the same texts except the input fingerprints."""
import json
import re
import unittest

import s4d_helpers as H
from v2_core.fixture import load_research_fixture

I = H.I
DAYS = H.table_days("2026-07-21", "2026-08-11")[:6]
FINGERPRINT = re.compile("入力SHA256先頭12桁=[0-9a-f/]+")


class SixMornings(H.Case):
    def test_six_mornings_equal_the_direct_run_over_the_research_fixture(self):
        self.assertEqual(DAYS, ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28"])
        real, direct = H.Rig(self), H.Rig(self)
        direct_sender = H.B.Sender()
        for day in DAYS:
            report, inp = real.morning(day, H.Provider(day))
            self.see(report, inp)
            self.assertIsNone(inp.failure, day)
            self.assertEqual((report.run_outcome, report.kind, report.delivery), ("DONE", "morning", "SENT"), day)
            direct.sync_ledger(day)
            now = H.jst_morning(day)
            series, _fg = load_research_fixture(H.DATA_DIR, through=day)
            reference = H.plain_run(direct.clone, direct_sender, now, series, I.build_sessions(now, day),
                                    H.ledger_rows(direct.ledger))
            names = ("run_outcome", "kind", "d", "delivery", "send_status", "existing_status", "code", "exit_code")
            self.assertEqual([getattr(report, n) for n in names], [getattr(reference, n) for n in names], day)
            self.assertEqual(report.d, day)
            self.assertEqual(FINGERPRINT.sub("", real.sender.texts[-1]), FINGERPRINT.sub("", direct_sender.texts[-1]), day)
            self.assertNotEqual(real.sender.texts[-1], direct_sender.texts[-1])        # only the fingerprints differ
        self.assertEqual(len(real.sender.texts), 6)
        self.assertEqual(real.sent_kinds(), ["morning"] * 6)
        # the stored histories are the same bytes, and each day was applied once
        mine, theirs = real.remote.blob("v2-state", "history.json"), direct.remote.blob("v2-state", "history.json")
        self.assertEqual(mine, theirs)
        events = json.loads(mine.decode("utf-8"))["events"]
        self.assertEqual([e["d"] for e in events if e["kind"] == "APPLY"], DAYS)
        # one pin per target day, every one a fast-forward of the last
        log = real.remote.log("v2-market")
        self.assertEqual(len(log), 6)
        for older, newer in zip(log, log[1:]):
            self.assertEqual(newer["parents"], [older["sha"]])
        self.assertEqual([c["subject"] for c in log], ["v2 market through " + d for d in DAYS])

    def test_the_mornings_after_the_weekend_and_the_rerun_of_the_last_one(self):
        rig = H.Rig(self)
        for day in DAYS:
            rig.morning(day, H.Provider(day))
        sent, before = len(rig.sender.texts), rig.remote.refs()
        for day in ("2026-07-28", "2026-07-29"):          # the same target day again; then the morning with no new session
            provider = H.Provider("2026-07-28")
            report, inp = rig.morning("2026-07-28", provider)
            self.assertEqual(provider.calls, 0)
            self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SKIPPED_CLAIMED"))
        self.assertEqual(len(rig.sender.texts), sent)
        self.assertEqual(rig.remote.refs(), before)

    def test_a_late_start_catches_up_over_the_missing_days(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-28", H.Provider("2026-07-28"))              # nothing ran before
        self.assertEqual((report.run_outcome, report.kind, report.delivery), ("DONE", "morning", "SENT"))
        history = json.loads(rig.remote.blob("v2-state", "history.json").decode("utf-8"))
        self.assertEqual([e["d"] for e in history["events"] if e["kind"] == "APPLY"],
                         H.table_days("2026-07-21", "2026-07-28"))
        self.assertEqual(rig.sent_kinds(), ["morning"])


if __name__ == "__main__":
    unittest.main()
