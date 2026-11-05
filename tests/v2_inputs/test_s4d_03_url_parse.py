"""S4D-04 and S4D-05: the URL of the chart request and the arguments of the fetch calls; the interpretation of a chart
response (rows, null days, bad values, wrong shapes, the New York date of a time, the pre-history start, the target day)."""
import json
import unittest
from datetime import datetime, timezone

import s4d_helpers as H

I = H.I
InputError = H.InputError
Q = "?period1=%d&period2=%d&interval=1d&events=div%%2Csplit&includeAdjustedClose=true"
BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"


def body(items, symbol="SOXX"):
    return json.dumps(H.chart_body(symbol, items)).encode("utf-8")


def parse(items, symbol="SOXX", through=None):
    return I.parse_chart(body(items, symbol), symbol, through)


def rejected(case, data, code, detail=None, symbol="SOXX", through=None):
    with case.assertRaises(InputError) as cm:
        I.parse_chart(data, symbol, through)
    err = cm.exception
    case.assertEqual((err.code, err.field, err.detail), (code, "market", detail))
    case.assertIsNone(err.__context__)
    case.assertIsNone(err.__cause__)
    return err


class Url(H.Case):
    def test_the_two_examples(self):
        self.assertEqual(I.chart_url("SOXX", "2010-02-11", "2026-07-29"), BASE + "SOXX" + Q % (1265846400, 1785283200))
        self.assertEqual(I.chart_url("SOXL", "2010-02-11", "2028-12-30"), BASE + "SOXL" + Q % (1265846400, 1861747200))
        self.assertEqual(I.chart_url("IEF", "2026-07-28", "2026-07-29"), BASE + "IEF" + Q % (1785196800, 1785283200))

    def test_every_symbol_has_a_url_and_the_function_is_pure(self):
        for s in H.SYMBOLS:
            self.assertEqual(I.chart_url(s, "2010-02-11", "2026-07-29"), I.chart_url(s, "2010-02-11", "2026-07-29"))
            self.assertTrue(I.chart_url(s, "2010-02-11", "2026-07-29").startswith(BASE + s + "?"))


class FetchArguments(H.Case):
    def args_of(self, now):
        rig = H.Rig(self)
        provider = H.Provider("2026-07-28")
        inp = I.load_inputs(rig.clone.git, provider, now, H.REFS, H.C.clock)
        self.see(inp)
        return provider, inp

    def test_four_symbols_once_each_from_the_prehistory_start_to_the_next_new_york_day(self):
        provider, _inp = self.args_of(H.jst_morning("2026-07-28"))       # 22:40Z on 07-28 = 18:40 New York on 07-28
        self.assertEqual(sorted(a[0] for a in provider.args), sorted(H.SYMBOLS))
        self.assertEqual(len(provider.args), 4)
        for symbol, start, end in provider.args:
            self.assertEqual((start, end), ("2010-02-11", "2026-07-29"), symbol)

    def test_the_end_is_the_day_after_the_new_york_date_of_now(self):
        cases = [(datetime(2026, 7, 28, 3, 30, tzinfo=timezone.utc), "2026-07-28"),     # 23:30 on 07-27 New York
                 (datetime(2026, 7, 28, 4, 30, tzinfo=timezone.utc), "2026-07-29"),     # 00:30 on 07-28 New York
                 (datetime(2026, 12, 1, 22, 30, tzinfo=timezone.utc), "2026-12-02"),    # 17:30 on 12-01 (winter)
                 (datetime(2026, 12, 2, 4, 30, tzinfo=timezone.utc), "2026-12-02")]     # 23:30 on 12-01 (winter)
        for now, end in cases:
            provider, _inp = self.args_of(now)
            self.assertEqual({a[2] for a in provider.args}, {end}, now)

    def test_no_fetch_when_the_pin_already_reaches_the_target(self):
        rig = H.Rig(self)
        first = H.Provider("2026-07-28")
        I.load_inputs(rig.clone.git, first, H.jst_morning("2026-07-28"), H.REFS, H.C.clock)
        self.assertEqual(first.calls, 4)
        second = H.Provider("2026-07-28")
        I.load_inputs(rig.clone.git, second, H.jst_morning("2026-07-28"), H.REFS, H.C.clock)
        self.assertEqual(second.calls, 0)


class Rows(H.Case):
    def test_a_correct_response_gives_the_rows(self):
        got = parse([("2026-07-27", 10.0, 9.5), ("2026-07-28", 11, 10.25)])
        self.assertEqual(got, {"2026-07-27": (10.0, 9.5), "2026-07-28": (11.0, 10.25)})
        for v in got.values():
            self.assertEqual({type(x) for x in v}, {float})

    def test_a_null_day_has_no_row_and_is_not_an_error(self):
        got = parse([("2026-07-24", 10.0, 9.0), ("2026-07-27", None, 9.5), ("2026-07-28", 11.0, None),
                     ("2026-07-29", None, None), ("2026-07-30", 12.0, 11.5)])
        self.assertEqual(got, {"2026-07-24": (10.0, 9.0), "2026-07-30": (12.0, 11.5)})

    def test_a_value_that_is_not_a_finite_number_in_range_is_a_bad_value_with_the_first_date(self):
        nan, inf = float("nan"), float("inf")
        bad_values = [nan, inf, -inf, 0, 0.0, -1, -0.5, 1000000, 1000000.0, 1e6, 1e7, True, False, "12.3", "", [1], {"a": 1},
                      10 ** 400]
        for bad in bad_values:
            for slot in (0, 1):
                items = [("2026-07-24", 10.0, 9.0), ("2026-07-27", 10.0, 9.0), ("2026-07-28", 10.0, 9.0)]
                day, c, a = items[1]
                items[1] = (day, bad, a) if slot == 0 else (day, c, bad)
                items[2] = ("2026-07-28", -3.0, 9.0)
                rejected(self, body(items), "input_market_value_invalid", "2026-07-27")
        # the first of several bad days is named, whatever the order of the response
        items = [("2026-07-28", 0.0, 9.0), ("2026-07-27", nan, 9.0)]
        rejected(self, body(items), "input_market_value_invalid", "2026-07-27")

    def test_the_largest_accepted_price_is_below_the_limit(self):
        for ok in (999999.99, 999999, 0.0001, 1e-9, 5e5):
            self.assertEqual(parse([("2026-07-28", ok, ok)]), {"2026-07-28": (float(ok), float(ok))})

    def test_a_wrong_shape_is_a_response_invalid(self):
        good = H.chart_body("SOXX", [("2026-07-27", 10.0, 9.0), ("2026-07-28", 11.0, 10.0)])

        def variant(edit):
            data = json.loads(json.dumps(good))
            edit(data)
            return json.dumps(data).encode("utf-8")

        r = lambda d: d["chart"]["result"][0]    # noqa: E731
        cases = {
            "not bytes": ["text", None, 3, bytearray(b"{}"), memoryview(b"{}"), [], {}],
            "not utf-8": [b"\xff\xfe\x00", b"{\x80}"],
            "not json": [b"", b"not json", b"{", b"null", b"[]", b"3", b"\"x\""],
            "no chart": [variant(lambda d: d.pop("chart")), variant(lambda d: d.update(chart=None)),
                         variant(lambda d: d.update(chart=[])), variant(lambda d: d["chart"].pop("result"))],
            "no result": [variant(lambda d: d["chart"].update(result=[])), variant(lambda d: d["chart"].update(result=None)),
                          variant(lambda d: d["chart"].update(result="x")), variant(lambda d: d["chart"].update(result={}))],
            "no meta or symbol": [variant(lambda d: r(d).pop("meta")), variant(lambda d: r(d)["meta"].pop("symbol")),
                                  variant(lambda d: r(d).update(meta=None))],
            "other symbol": [variant(lambda d: r(d)["meta"].update(symbol="SPY")),
                             variant(lambda d: r(d)["meta"].update(symbol="soxx")),
                             variant(lambda d: r(d)["meta"].update(symbol=None))],
            "no columns": [variant(lambda d: r(d).pop("timestamp")), variant(lambda d: r(d).pop("indicators")),
                           variant(lambda d: r(d)["indicators"].pop("quote")),
                           variant(lambda d: r(d)["indicators"].pop("adjclose")),
                           variant(lambda d: r(d)["indicators"].update(quote=[])),
                           variant(lambda d: r(d)["indicators"].update(adjclose=[])),
                           variant(lambda d: r(d)["indicators"]["quote"][0].pop("close")),
                           variant(lambda d: r(d)["indicators"]["adjclose"][0].pop("adjclose"))],
            "lengths differ": [variant(lambda d: r(d)["timestamp"].pop()),
                               variant(lambda d: r(d)["indicators"]["quote"][0]["close"].pop()),
                               variant(lambda d: r(d)["indicators"]["adjclose"][0]["adjclose"].append(1.0))],
            "columns are not lists": [variant(lambda d: r(d).update(timestamp="ab")),
                                      variant(lambda d: r(d)["indicators"]["quote"][0].update(close={"a": 1, "b": 2})),
                                      variant(lambda d: r(d)["indicators"]["adjclose"][0].update(adjclose=None))],
            "a time that is not an integer": [variant(lambda d: r(d)["timestamp"].__setitem__(0, 1.5)),
                                              variant(lambda d: r(d)["timestamp"].__setitem__(0, "1785000000")),
                                              variant(lambda d: r(d)["timestamp"].__setitem__(0, None)),
                                              variant(lambda d: r(d)["timestamp"].__setitem__(0, True)),
                                              variant(lambda d: r(d)["timestamp"].__setitem__(0, 10 ** 30)),
                                              variant(lambda d: r(d)["timestamp"].__setitem__(0, -10 ** 30))],
        }
        for name, datas in cases.items():
            for data in datas:
                rejected(self, data, "input_market_response_invalid")
        self.assertEqual(len(I.parse_chart(json.dumps(good).encode("utf-8"), "SOXX")), 2)       # the base is fine

    def test_the_same_date_twice_up_to_the_target_is_a_wrong_shape(self):
        items = [("2026-07-27", 10.0, 9.0), ("2026-07-27", 10.5, 9.5), ("2026-07-28", 11.0, 10.0)]
        rejected(self, body(items), "input_market_response_invalid")
        rejected(self, body(items), "input_market_response_invalid", through="2026-07-28")
        rejected(self, body(items), "input_market_response_invalid", through="2026-07-27")
        # two times of one New York day count as the same date
        two = [(H.ny_stamp("2026-07-27", 9, 30), 10.0, 9.0), (H.ny_stamp("2026-07-27", 15, 59), 10.5, 9.5)]
        rejected(self, body(two), "input_market_response_invalid")

    def test_a_time_gives_the_same_new_york_date_before_and_after_a_change_of_time(self):
        days = ["2026-03-06", "2026-03-09", "2026-10-30", "2026-11-02", "2027-03-12", "2027-03-15", "2027-11-05",
                "2027-11-08", "2028-03-10", "2028-03-13", "2028-11-03", "2028-11-06", "2026-07-28", "2026-01-05"]
        for day in days:
            for hour, minute in ((9, 30), (16, 0), (0, 0), (12, 0), (23, 59)):
                got = I.parse_chart(body([(H.ny_stamp(day, hour, minute), 10.0, 9.0)]), "SOXX")
                self.assertEqual(list(got), [day], (day, hour, minute))

    def test_rows_before_the_prehistory_start_are_dropped(self):
        items = [("2010-02-09", -1.0, -1.0), ("2010-02-10", None, None), ("2010-02-11", 10.0, 9.0),
                 ("2010-02-12", 11.0, 10.0)]
        self.assertEqual(sorted(parse(items)), ["2010-02-11", "2010-02-12"])

    def test_a_row_after_the_target_is_dropped_before_any_check(self):
        items = [("2026-07-27", 10.0, 9.0), ("2026-07-28", 11.0, 10.0),
                 ("2026-07-29", 12.0, 11.0), ("2026-07-29", 12.5, 11.5),     # the same date twice
                 ("2026-07-30", float("nan"), 11.0), ("2026-07-31", 5e6, 5e6), ("2026-08-03", None, None)]
        got = parse(items, through="2026-07-28")
        self.assertEqual(sorted(got), ["2026-07-27", "2026-07-28"])
        self.assertEqual(got["2026-07-28"], (11.0, 10.0))
        # without a target everything is checked
        rejected(self, body(items), "input_market_response_invalid")
        # a target after the double: the double is now before it
        rejected(self, body(items), "input_market_response_invalid", through="2026-07-29")
        # a bad value up to the target is still a bad value
        bad = [("2026-07-27", 10.0, 9.0), ("2026-07-28", 0.0, 9.0), ("2026-07-29", 12.0, 11.0)]
        rejected(self, body(bad), "input_market_value_invalid", "2026-07-28", through="2026-07-28")
        self.assertEqual(sorted(parse(bad, through="2026-07-27")), ["2026-07-27"])


if __name__ == "__main__":
    unittest.main()
