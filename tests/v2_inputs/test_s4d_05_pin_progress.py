"""S4D-08, S4D-09 and S4D-11: how the pin moves (first run, the same morning again, the next target day, a fetch that adds
nothing, the 60 minutes after the close), that a revision of the source does not reach a day that is already pinned, and a
morning when the rows of the target day are not there yet."""
import json
import unittest
from datetime import timedelta

import s4d_helpers as H
import v2_inputs.market as M
import v2_daily_run

I = H.I
DAYS = H.table_days("2026-07-21", "2026-07-28")


def expected_pin(day):
    rows = H.research(day)
    body = {"schema": "v2_inputs.market.1", "through": day, "source": "yahoo_chart_v8", "symbols": {}}
    for s in H.SYMBOLS:
        dates = sorted(d for d in rows[s] if H.PRE <= d <= day)
        body["symbols"][s] = {"dates": dates, "close": [rows[s][d][0] for d in dates],
                              "adjclose": [rows[s][d][1] for d in dates]}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


class Progress(H.Case):
    def test_first_run_pins_one_commit_without_a_parent_holding_only_market_json(self):
        rig = H.Rig(self)
        report, inp = rig.morning("2026-07-21", H.Provider("2026-07-21"))
        self.see(report, inp)
        self.assertEqual((report.run_outcome, report.kind, report.delivery), ("DONE", "morning", "SENT"))
        log = rig.remote.log("v2-market")
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["parents"], log[0]["names"]), ([], ["market.json"]))
        self.assertEqual(log[0]["subject"], "v2 market through 2026-07-21")
        self.assertEqual(rig.remote.blob("v2-market", "market.json"), expected_pin("2026-07-21"))
        p = inp.provenance
        self.assertEqual((p["pinned_by"], p["fetch_count"], p["market_through"], p["market_commit"]),
                         ("this", 4, "2026-07-21", log[0]["sha"]))
        self.assertEqual(p["market_sha256"], H.blob_sha256(expected_pin("2026-07-21")))

    def test_the_same_morning_again_fetches_nothing_and_changes_nothing(self):
        rig = H.Rig(self)
        rig.morning("2026-07-21", H.Provider("2026-07-21"))
        before = rig.remote.refs()
        again = H.Provider("2026-07-21", scale=1.002)
        report, inp = rig.morning("2026-07-21", again)
        self.assertEqual(again.calls, 0)
        self.assertEqual((inp.provenance["pinned_by"], inp.provenance["fetch_count"]), ("existing", 0))
        self.assertEqual(inp.provenance["market_commit"], rig.remote.sha("v2-market"))
        self.assertEqual(rig.remote.refs(), before)
        self.assertEqual((report.run_outcome, report.delivery), ("DONE", "SKIPPED_CLAIMED"))

    def test_the_next_target_day_fetches_again_and_adds_a_commit_on_the_last_one(self):
        rig = H.Rig(self)
        rig.morning("2026-07-21", H.Provider("2026-07-21"))
        first = rig.remote.sha("v2-market")
        provider = H.Provider("2026-07-22")
        report, inp = rig.morning("2026-07-22", provider)
        self.assertEqual(provider.calls, 4)
        log = rig.remote.log("v2-market")
        self.assertEqual([c["sha"] for c in log][0], first)
        self.assertEqual(len(log), 2)
        self.assertEqual(log[1]["parents"], [first])
        self.assertEqual(log[1]["subject"], "v2 market through 2026-07-22")
        self.assertEqual(rig.remote.blob("v2-market", "market.json"), expected_pin("2026-07-22"))
        self.assertEqual(H.tgit(rig.remote.path, "merge-base", "--is-ancestor", first, log[1]["sha"], check=False).returncode, 0)
        self.assertEqual((report.run_outcome, inp.provenance["pinned_by"]), ("DONE", "this"))

    def test_a_weekend_morning_fetches_nothing(self):
        rig = H.Rig(self)
        rig.morning("2026-07-24", H.Provider("2026-07-24"))                  # a Friday
        for day in ("2026-07-24", "2026-07-25", "2026-07-26"):               # the mornings of Saturday, Sunday, Monday
            weekend = H.Provider("2026-07-24")
            report, inp = rig.morning(day, weekend)
            self.assertEqual(weekend.calls, 0, day)
            self.assertEqual(inp.provenance["pinned_by"], "existing")
            self.assertEqual(report.delivery, "SKIPPED_CLAIMED")

    def test_a_fetch_that_reaches_no_further_than_the_pin_makes_no_commit_and_the_pinned_bytes_are_used(self):
        rig = H.Rig(self)
        rig.morning("2026-07-21", H.Provider("2026-07-21"))
        head, pinned = rig.remote.sha("v2-market"), rig.remote.blob("v2-market", "market.json")
        original = H.research("2026-07-21")["SOXX"]["2026-07-21"][1]
        revised = H.Provider("2026-07-21", scale=1.01)                       # the source revised the adjusted close
        report, inp = rig.morning("2026-07-22", revised)                     # the target is 07-22, the rows reach 07-21
        self.assertEqual(revised.calls, 4)
        self.assertEqual(rig.remote.sha("v2-market"), head)
        self.assertEqual(rig.remote.blob("v2-market", "market.json"), pinned)
        self.assertEqual(inp.provenance["pinned_by"], "existing")
        self.assertEqual(inp.provenance["market_sha256"], H.blob_sha256(pinned))
        self.assertEqual(inp.series.soxx[-1], original)                      # the pinned value, not the revised one
        self.assertEqual((report.run_outcome, report.code, report.kind), ("STALE", "run_session_unconfirmed", "halt"))

    def test_the_close_margin_is_sixty_minutes_not_fifty_nine(self):
        for early in (False, True):
            if early:
                day, start, rows = "2026-11-27", "2026-11-20", H.synthetic("2026-11-27")
                close = H.ny_to_utc(day, 13, 0)
            else:
                day, start, rows = "2026-07-28", "2026-07-20", H.research()
                close = H.ny_to_utc(day, 16, 0)
            previous = H.table_days(H.next_day(start), day)[-2]
            for minutes, want in ((59, previous), (60, day)):
                rig = H.Rig(self, start=start)
                rig.sync_ledger(previous)                  # the decision of the day itself is written the morning after
                now = close + timedelta(minutes=minutes)
                inp, _ = rig.inputs(day, H.Provider(day, rows=rows), now=now)
                self.assertIsNone(inp.failure)
                self.assertEqual(inp.provenance["market_through"], want, (early, minutes))

    def test_the_sessions_are_confirmed_through_the_pin(self):
        rig = H.Rig(self)
        inp, _ = rig.inputs("2026-07-22", H.Provider("2026-07-22"))
        flags = {s.date: s.confirmed for s in inp.sessions.sessions}
        self.assertTrue(flags["2026-07-22"])
        self.assertFalse(flags["2026-07-23"])
        self.assertTrue(all(v for d, v in flags.items() if d <= "2026-07-22"))
        self.assertFalse(any(v for d, v in flags.items() if d > "2026-07-22"))


class PriceRevision(H.Case):
    def test_a_revision_of_the_source_does_not_stop_the_rerun_of_the_same_morning(self):
        rig = H.Rig(self)
        for day in DAYS:
            report, _inp = rig.morning(day, H.Provider(day))
            self.assertEqual((report.run_outcome, report.kind, report.delivery), ("DONE", "morning", "SENT"), day)
        sent = len(rig.sender.texts)
        before = rig.remote.refs()
        revised = H.Provider("2026-07-28", scale=1.001)                      # 0.1 % on every adjusted close
        report, inp = rig.morning("2026-07-28", revised)
        self.assertEqual(revised.calls, 0)
        self.assertEqual((report.run_outcome, report.code, report.delivery), ("DONE", None, "SKIPPED_CLAIMED"))
        self.assertEqual(len(rig.sender.texts), sent)
        self.assertEqual(rig.remote.refs(), before)
        # the control: the revised series straight into the run (no pin) is a recompute mismatch
        now = H.jst_morning("2026-07-28")
        fetched = {s: I.parse_chart(H.chart_bytes(s, H.research()[s], "2026-07-28", scale=1.001), s) for s in H.SYMBOLS}
        series = M.series_of("2026-07-28", fetched, "x")
        direct = v2_daily_run.run_morning(rig.clone.hist, now, series, I.build_sessions(now, "2026-07-28"),
                                          inp.raw_observations)
        self.assertEqual((direct.outcome, direct.code), ("STOPPED", "recompute_mismatch"))

    def test_a_revision_reaches_only_the_days_after_it(self):
        rig = H.Rig(self)
        rig.morning("2026-07-21", H.Provider("2026-07-21"))
        report, inp = rig.morning("2026-07-22", H.Provider("2026-07-22", scale=1.001))
        self.assertEqual(report.run_outcome, "DONE")
        again, _inp = rig.inputs("2026-07-22", H.Provider("2026-07-22"))
        self.assertEqual(again.provenance["market_sha256"], inp.provenance["market_sha256"])
        self.assertEqual(inp.series.soxx[-1], H.research("2026-07-22")["SOXX"]["2026-07-22"][1] * 1.001)
        close = H.research("2026-07-22")["SOXL"]["2026-07-22"][0]                       # the close is not revised
        value = inp.series.soxl_close("2026-07-22")
        self.assertEqual(value, type(value)(str(close)))


class TargetNotThereYet(H.Case):
    def test_no_row_for_the_target_day_is_a_stale_with_one_notice_then_a_verdict_later(self):
        rig = H.Rig(self)
        rig.morning("2026-07-21", H.Provider("2026-07-21"))
        report, inp = rig.morning("2026-07-22", H.Provider("2026-07-21"))
        self.assertIsNone(inp.failure)
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery),
                         ("STALE", "run_session_unconfirmed", "halt", "SENT"))
        flags = {s.date: s.confirmed for s in inp.sessions.sessions}
        self.assertFalse(flags["2026-07-22"])
        later, inp2 = rig.morning("2026-07-22", H.Provider("2026-07-22"))
        self.assertEqual((later.run_outcome, later.kind, later.delivery), ("DONE", "morning", "SENT"))
        self.assertEqual(rig.sent_kinds()[-2:], ["halt", "morning"])
        self.assertEqual(inp2.provenance["pinned_by"], "this")


if __name__ == "__main__":
    unittest.main()
