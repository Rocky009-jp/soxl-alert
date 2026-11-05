"""S4E-05 and S4E-11: a morning whose inputs are wrong still sends the one notice of the target day (STOPPED, a judgment-less
notice under the key <D>-halt, exit 0), the record names the reason (the code, and for a failed fetch the symbol and a fixed
word), and the same morning with the inputs back to normal sends the judgment. A time past the table raises in load_inputs:
one ERROR notice under the fallback key, the code in the record, exit 1. provenance["fetch_count"] is the number of fetches made."""
import unittest

import s4e_helpers as H
from datetime import datetime, timezone

D, I = H.D, H.I
DAY, START = "2026-07-28", "2026-07-27"


def start(case, mode="dry"):
    work, net = H.Work(case), H.Net(DAY)
    assert work.init(net, mode, start=START).code == 0
    return work, net


class WrongInputs(H.D.Case):
    def check_halt(self, result, code, word=None):
        kv = result.kv
        self.assertEqual(result.code, 0)
        self.assertEqual((kv["run_outcome"], kv["key"], kv["delivery"], kv["send_status"], kv["code"]),
                         ("STOPPED", DAY + "-halt", "SENT", "SENT", code))
        self.assertTrue(kv["inputs_failure"].startswith(code + "（"))
        self.assertIn("判定なし", result.block())
        self.assertIn(code, result.block())
        self.assertEqual(H.leaks(result.text), [])
        if word is None:
            self.assertEqual(result.all("fetch_failure"), [])
        else:
            self.assertEqual(result.all("fetch_failure"), [word])

    def normal_again(self, work, net):
        net.override.clear()
        net.provider.drop, net.provider.extra, net.provider.bad = (), {}, {}
        net.provider.rows = H.D.research()
        again = work.morning(net, "dry", DAY, hhmm="08:40", start=START)
        self.assertEqual(again.code, 0)
        self.assertEqual((again.kv["run_outcome"], again.kv["key"], again.kv["delivery"], again.kv["send_status"]),
                         ("DONE", DAY + "-morning", "SENT", "SENT"))
        return again

    def test_a_fetch_that_raises(self):
        work, net = start(self)
        net.override["SPY"] = OSError("network " + H.MARK)
        result = work.morning(net, "dry", DAY, start=START)
        self.check_halt(result, "input_market_fetch_failed", "SPY other")
        self.assertEqual(result.kv["provenance.fetch_count"], "2")
        self.assertEqual(len(net.charts()), 2)
        self.normal_again(work, net)

    def test_a_status_500(self):
        work, net = start(self)
        net.override["SOXX"] = H.http_error(H.CHART_BASE + "SOXX", 500)
        result = work.morning(net, "dry", DAY, start=START)
        self.check_halt(result, "input_market_fetch_failed", "SOXX http_500")
        self.assertEqual(result.kv["provenance.fetch_count"], "1")
        self.normal_again(work, net)

    def test_a_response_over_the_limit(self):
        work, net = start(self)
        net.override["IEF"] = ("size", H.R.MAX_BYTES + 1)
        result = work.morning(net, "dry", DAY, start=START)
        self.check_halt(result, "input_market_fetch_failed", "IEF size")
        self.assertEqual(result.kv["provenance.fetch_count"], "3")
        self.normal_again(work, net)

    def test_two_rows_of_the_target_day_after_the_close(self):
        work, net = start(self)
        net.provider.extra = {s: [(H.D.ny_stamp(DAY, 15, 59), 77.0, 77.0)] for s in H.SYMBOLS}
        result = work.morning(net, "dry", DAY, start=START)
        self.check_halt(result, "input_market_response_invalid")
        self.normal_again(work, net)

    def test_a_hole_in_the_table_days(self):
        work, net = start(self)
        net.provider.drop = ("2026-07-27",)
        result = work.morning(net, "dry", DAY, start=START)
        self.check_halt(result, "input_market_rows_missing")
        self.assertIn("2026-07-27", result.kv["inputs_failure"])
        self.normal_again(work, net)

    def test_a_ledger_that_is_wrong(self):
        work, net = start(self)
        work.put_ledger(D.HEADER.replace("record_id", "id") + D.decision_line("2026-07-27"))
        result = work.morning(net, "dry", DAY, start=START, sync=False)
        self.check_halt(result, "input_ledger_header_invalid")
        work.ledger = ""
        again = self.normal_again(work, net)
        self.assertEqual(again.kv["existing_status"], "None")

    def test_a_ledger_that_is_missing(self):
        work, net = start(self)
        result = work.morning(net, "dry", DAY, start=START, sync=False)
        self.check_halt(result, "input_ledger_missing")

    def test_the_judgment_less_notice_in_a_live_run_goes_out_once(self):
        work, net = start(self, "live")
        net.override["SOXX"] = H.http_error(H.CHART_BASE + "SOXX", 429)
        result = work.morning(net, "live", DAY, start=START)
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["run_outcome"], result.kv["delivery"]), ("STOPPED", "SENT"))
        self.assertEqual(result.all("fetch_failure"), ["SOXX http_429"])
        self.assertEqual(len(net.posts()), 1)
        self.assertIsNone(result.block())                    # a live run writes no text
        self.assertIn("判定なし", net.posts()[0]["content"])
        again = work.morning(net, "live", DAY, hhmm="08:40", start=START) if net.override.pop("SOXX") else None
        self.assertEqual((again.kv["run_outcome"], again.kv["key"], again.kv["delivery"]), ("DONE", DAY + "-morning", "SENT"))
        self.assertEqual(len(net.posts()), 2)                # the judgment after a judgment-less notice is sent (S4-B)


class TimePastTheTable(H.D.Case):
    def test_load_inputs_raises_then_one_error_notice_and_exit_1(self):
        work, net = H.Work(self), H.Net()
        self.assertEqual(work.init(net, "dry").code, 0)
        late = datetime(2029, 1, 2, 6, 0, tzinfo=timezone.utc)
        result = work.run(net, ["morning", "--mode", "dry"], late)
        self.assertEqual(result.code, 1)
        self.assertEqual(result.kv["inputs_raised"], "input_calendar_ended（calendar）")
        self.assertEqual(result.kv["key"], "2029-01-02-error")
        self.assertEqual((result.kv["delivery"], result.kv["send_status"]), ("SENT", "SENT"))
        self.assertEqual(net.requests, [])                    # nothing was fetched
        self.assertIsNotNone(result.block())
        status = work.run(net, ["status", "--mode", "dry", "--date", "2029-01-02"], late)
        self.assertIn("- 2029-01-02-error: SENT ", status.text)
        self.assertEqual(H.leaks(result.text), [])
        again = work.run(net, ["morning", "--mode", "dry"], late)
        self.assertEqual((again.code, again.kv["delivery"]), (1, "SKIPPED_CLAIMED"))     # one notice only; still exit 1


class FetchCount(H.D.Case):
    """S4-D review P-01 (S4E-11): the count is the number of fetches made, also when a response is wrong."""

    def count(self, setup):
        work, net = start(self)
        setup(net)
        result = work.morning(net, "dry", DAY, start=START)
        self.assertEqual(result.kv["run_outcome"], "STOPPED")
        return result.kv["provenance.fetch_count"], result.kv["code"], len(net.charts())

    def test_a_wrong_shape_or_value_in_the_last_symbol_counts_four(self):
        self.assertEqual(self.count(lambda n: n.override.update(SOXL=b"not json " + H.MARK.encode())),
                         ("4", "input_market_response_invalid", 4))

        def bad_value(net):
            net.provider.rows["SOXL"][DAY] = (2e6, 2e6)
        self.assertEqual(self.count(bad_value), ("4", "input_market_value_invalid", 4))

    def test_the_count_stops_at_the_symbol_that_failed(self):
        self.assertEqual(self.count(lambda n: n.override.update(SOXX=b"{}")), ("1", "input_market_response_invalid", 1))
        self.assertEqual(self.count(lambda n: n.override.update(SPY=b"{}")), ("2", "input_market_response_invalid", 2))
        self.assertEqual(self.count(lambda n: n.override.update(IEF=OSError("x"))), ("3", "input_market_fetch_failed", 3))
        self.assertEqual(self.count(lambda n: n.override.update(SOXL=OSError("x"))), ("4", "input_market_fetch_failed", 4))

    def test_load_inputs_itself_counts_the_same(self):
        rig = D.Rig(self, start=START)
        report, inp = rig.morning(DAY, D.Provider(DAY, bad={"SOXL": b"not json"}))
        self.assertEqual(inp.failure.code, "input_market_response_invalid")
        self.assertEqual(inp.provenance["fetch_count"], 4)
        rig = D.Rig(self, start=START)
        report, inp = rig.morning(DAY, D.Provider(DAY, bad={"SPY": OSError("x")}))
        self.assertEqual((inp.failure.code, inp.provenance["fetch_count"]), ("input_market_fetch_failed", 2))
        ok = D.Rig(self, start=START)
        report, inp = ok.morning(DAY, D.Provider(DAY))
        self.assertEqual((inp.failure, inp.provenance["fetch_count"]), (None, 4))

    def test_a_run_that_does_not_fetch_counts_zero(self):
        work, net = start(self)
        first = work.morning(net, "dry", DAY, start=START)
        self.assertEqual(first.kv["provenance.fetch_count"], "4")
        second = work.morning(net, "dry", DAY, hhmm="08:40", start=START)
        self.assertEqual(second.kv["provenance.fetch_count"], "0")


if __name__ == "__main__":
    unittest.main()
