"""S4E-13: check-source records the facts of the four chart responses (shape, rows, first and last day, the New York times, the
rows of the target day, the table days with no row, the null rows, the difference to the research data before 2026, the
difference to the pin) and writes nothing: the heads of every ref are the same before and after. The fetch ends the day after the
New York date of now, like load_inputs."""
import unittest
from datetime import datetime, timezone

import s4e_helpers as H

D = H.D
UTC = timezone.utc
TARGET = "2026-07-24"
PINNED = "2026-07-23"


class Base(H.D.Case):
    def setUp(self):
        super().setUp()
        self.work, self.net = H.Work(self), H.Net(PINNED)
        self.assertEqual(self.work.init(self.net, "dry").code, 0)
        for day in H.days("2026-07-21", PINNED):
            self.assertEqual(self.work.morning(self.net, "dry", day).code, 0)
        self.net.upto = TARGET
        self.net.requests.clear()
        self.net.chart_args.clear()
        self.heads = self.work.heads()

    def check(self, now=None):
        result = self.work.run(self.net, ["check-source", "--mode", "dry"], now or H.aware(TARGET))
        self.assertEqual(self.work.heads(), self.heads)                  # nothing written, whatever was found
        self.assertEqual(self.net.posts(), [])
        self.assertEqual(H.leaks(result.text), [])
        return result


class Normal(Base):
    def test_the_facts_of_a_normal_response(self):
        result = self.check()
        self.assertEqual(result.code, 0)
        self.assertEqual(result.kv["target_d"], TARGET)
        self.assertEqual(result.kv["pin_through"], PINNED)
        rows = D.research(TARGET)
        for symbol in H.SYMBOLS:
            kv = {k.split(".", 1)[1]: v for k, v in result.kv.items() if k.startswith(symbol + ".")}
            mine = rows[symbol]
            self.assertEqual(kv["shape"], "ok", symbol)
            self.assertEqual(kv["meta_symbol_ok"], "True")
            self.assertEqual(kv["rows"], str(len(mine)), symbol)
            self.assertEqual((kv["first"], kv["last"]), (min(mine), TARGET), symbol)
            self.assertEqual(kv["times_ny"], "09:30×%d" % len(mine), symbol)
            self.assertEqual(kv["duplicate_dates"], "-")
            self.assertEqual(kv["target_rows"], "1", symbol)
            self.assertEqual(kv["table_days_missing_or_null"], "0", symbol)
            self.assertEqual(kv["table_days_missing_examples"], "-")
            self.assertEqual(kv["null_rows"], "0")
            self.assertEqual(kv["pre2026_only_in_response"], "0", symbol)
            self.assertEqual(kv["pre2026_only_in_research"], "0", symbol)
            self.assertEqual(kv["pin_last_close_changed"], "False", symbol)
            self.assertEqual(kv["pin_older_close_changed"], "0", symbol)
            self.assertEqual(kv["pin_adj_return_maxdiff"], "0.00e+00", symbol)
        self.assertEqual(result.all("fetch_failure"), [])

    def test_the_four_symbols_are_fetched_once_each_to_the_day_after_the_new_york_date(self):
        # 01:00 UTC on 07-25 is 21:00 on 07-24 in New York: end = 07-25 (a UTC date would give 07-26)
        result = self.check(datetime(2026, 7, 25, 1, 0, tzinfo=UTC))
        self.assertEqual(result.code, 0)
        self.assertEqual(self.net.chart_args, [(s, "2010-02-11", "2026-07-25") for s in H.SYMBOLS])
        self.assertEqual(len(self.net.requests), 4)
        self.assertEqual(result.kv["target_d"], TARGET)
        other = self.check(datetime(2026, 7, 24, 22, 40, tzinfo=UTC))                     # 07:40 Japan time on 07-25: the same end
        self.assertEqual(self.net.chart_args[4:], [(s, "2010-02-11", "2026-07-25") for s in H.SYMBOLS])
        self.assertEqual(other.code, 0)

    def test_the_run_leaves_the_record_in_the_summary_file_too(self):
        result = self.check()
        self.assertTrue(result.summary.startswith("### v2_run"))
        self.assertIn("- SOXX.rows: ", result.summary)


class Findings(Base):
    def test_two_rows_of_the_target_day(self):
        self.net.provider.extra = {"SOXX": [(D.ny_stamp(TARGET, 15, 59), 77.0, 77.0)]}
        result = self.check()
        self.assertEqual(result.code, 0)
        self.assertEqual(result.kv["SOXX.target_rows"], "2")
        self.assertEqual(result.kv["SOXX.duplicate_dates"], TARGET)
        self.assertEqual(result.kv["SPY.target_rows"], "1")
        self.assertEqual(result.kv["SPY.duplicate_dates"], "-")

    def test_a_changed_last_close_and_a_table_day_missing_in_one_symbol(self):
        rows = self.net.provider.rows
        old_close, old_adj = rows["SOXX"][PINNED]
        rows["SOXX"][PINNED] = (old_close * 1.01, old_adj * 1.01)
        gone = rows["SPY"].pop("2026-03-02")
        self.assertIsNotNone(gone)
        result = self.check()
        self.assertEqual(result.kv["SOXX.pin_last_close_changed"], "True")
        before = rows["SOXX"]["2026-07-22"]
        previous = D.research("2026-07-22")["SOXX"]["2026-07-22"]
        self.assertEqual(before, previous)
        expected = 0.01 * old_adj / previous[1]
        self.assertAlmostEqual(float(result.kv["SOXX.pin_adj_return_maxdiff"]), expected, delta=expected * 0.01)
        self.assertEqual(result.kv["SOXX.pin_older_close_changed"], "0")
        self.assertEqual(result.kv["SPY.table_days_missing_or_null"], "1")
        self.assertEqual(result.kv["SPY.table_days_missing_examples"], "2026-03-02")
        self.assertEqual(result.kv["SOXX.table_days_missing_or_null"], "0")
        self.assertEqual(result.kv["SPY.pin_last_close_changed"], "False")

    def test_an_older_close_that_changed_is_counted(self):
        rows = self.net.provider.rows
        for day in ("2026-07-20", "2026-07-21"):
            close, adj = rows["IEF"][day]
            rows["IEF"][day] = (close + 1.0, adj)
        result = self.check()
        self.assertEqual(result.kv["IEF.pin_older_close_changed"], "2")
        self.assertEqual(result.kv["IEF.pin_last_close_changed"], "False")

    def test_null_rows_and_a_null_table_day(self):
        self.net.provider.rows["SOXL"]["2026-07-22"] = (None, None)
        result = self.check()
        self.assertEqual(result.kv["SOXL.null_rows"], "1")
        self.assertEqual(result.kv["SOXL.table_days_missing_or_null"], "1")
        self.assertEqual(result.kv["SOXL.table_days_missing_examples"], "2026-07-22")

    def test_days_before_2026_that_only_one_side_has(self):
        rows = self.net.provider.rows
        research_day = [d for d in sorted(rows["SOXX"]) if "2015-06-01" <= d < "2015-07-01"][0]
        del rows["SOXX"][research_day]
        rows["SOXX"]["2015-06-06"] = (50.0, 50.0)                       # a Saturday: only the response has it
        result = self.check()
        self.assertEqual(result.kv["SOXX.pre2026_only_in_research"], "1")
        self.assertEqual(result.kv["SOXX.pre2026_only_in_response"], "1")
        self.assertEqual(result.kv["SPY.pre2026_only_in_research"], "0")

    def test_a_response_of_a_wrong_shape_is_a_fact_and_the_exit_is_still_0_because_every_fetch_passed(self):
        self.net.override["SPY"] = b"not json " + H.MARK.encode()
        result = self.check()
        self.assertEqual(result.code, 0)
        self.assertEqual(result.kv["SPY.shape"], "invalid")
        self.assertEqual(result.kv["SOXX.shape"], "ok")

    def test_a_failed_fetch_names_the_symbol_a_type_and_a_fixed_word_and_the_exit_is_1(self):
        for symbol, error, word in (("IEF", H.http_error(H.CHART_BASE + "IEF", 429), "IEF http_429"),
                                    ("SOXX", OSError("network " + H.MARK), "SOXX other")):
            self.net.override = {symbol: error}
            result = self.check()
            self.assertEqual(result.code, 1)
            self.assertEqual(result.kv[symbol + ".fetch"], "failed (FetchFailed)")
            self.assertIn(word, result.all("fetch_failure"))
            for other in H.SYMBOLS:
                if other != symbol:
                    self.assertEqual(result.kv[other + ".shape"], "ok")
            self.assertNotIn(symbol + ".rows", result.kv)


class PinStates(H.D.Case):
    def fresh(self):
        work, net = H.Work(self), H.Net(TARGET)
        self.assertEqual(work.init(net, "dry").code, 0)
        work.sync_ledger(H.START, TARGET)
        return work, net

    def test_without_a_pin_the_facts_come_without_the_pin_comparison(self):
        work, net = self.fresh()
        heads = work.heads()
        result = work.run(net, ["check-source", "--mode", "dry"], H.aware(TARGET))
        self.assertEqual(result.code, 0)
        self.assertEqual(result.kv["pin_through"], "None")
        self.assertNotIn("SOXX.pin_last_close_changed", result.kv)
        self.assertEqual(result.kv["SOXX.shape"], "ok")
        self.assertEqual(work.heads(), heads)

    def test_a_pin_that_is_not_a_snapshot_is_recorded_as_unreadable_and_nothing_is_written(self):
        work, net = self.fresh()
        work.remote.plant("v2-dry-market", {"market.json": b"{}"}, parent=None)
        heads = work.heads()
        result = work.run(net, ["check-source", "--mode", "dry"], H.aware(TARGET))
        self.assertEqual(result.code, 0)
        self.assertEqual(result.kv["pin_through"], "unreadable (InputError（input_market_pin_invalid）)")
        self.assertNotIn("SOXX.pin_last_close_changed", result.kv)
        self.assertEqual(work.heads(), heads)

    def test_the_live_mode_reads_the_live_pin_only(self):
        work, net = self.fresh()
        self.assertEqual(work.init(net, "live").code, 0)
        self.assertEqual(work.morning(net, "dry", "2026-07-21").code, 0)         # a dry pin exists; the live ref has none
        result = work.run(net, ["check-source", "--mode", "live"], H.aware(TARGET))
        self.assertEqual(result.kv["pin_through"], "None")


if __name__ == "__main__":
    unittest.main()
