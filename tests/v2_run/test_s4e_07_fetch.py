"""S4E-08 (the fetch half) and S4E-09: the request of a fetch (the URL of chart_url as it is, the two headers, the timeout 30, the
four symbols once each, `end` = the day after the New York date of now), the limit of 8 MB, every failure as an exception that
holds a fixed word and records (symbol, word), and no URL or body in anything that is raised."""
import socket
import unittest
import urllib.error
from datetime import datetime, timezone

import s4e_helpers as H

R, WEB = H.R, H.WEB
D = H.D
UTC = timezone.utc


def expected_url(symbol, start, end):
    """The URL of the S4-D design, written here again (not taken from chart_url)."""
    seconds = [int(datetime.fromisoformat(x + "T00:00:00+00:00").timestamp()) for x in (start, end)]
    return ("https://query1.finance.yahoo.com/v8/finance/chart/%s?period1=%d&period2=%d&interval=1d&events=div%%2Csplit"
            "&includeAdjustedClose=true" % (symbol, seconds[0], seconds[1]))


def fetch_with(net, failures=None):
    return R.make_fetch(net, failures)


def call(fetch, symbol="SOXX"):
    return fetch(symbol, "2010-02-11", "2026-07-28")


class RequestShape(unittest.TestCase):
    def test_the_url_the_headers_and_the_timeout(self):
        net = H.Net("2026-07-28")
        data = call(fetch_with(net), "SPY")
        self.assertIsInstance(data, bytes)
        request = net.requests[0]
        self.assertEqual(request["url"], expected_url("SPY", "2010-02-11", "2026-07-28"))
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["timeout"], 30)
        self.assertEqual(request["headers"], {"user-agent": "Mozilla/5.0 (compatible; soxl-alert-v2)", "accept": "application/json"})
        self.assertIsNone(request["data"])
        self.assertEqual(len(net.requests), 1)

    def test_one_call_one_request_and_no_retry_after_a_failure(self):
        net = H.Net("2026-07-28")
        net.override["SOXX"] = OSError("network")
        with self.assertRaises(WEB.FetchFailed):
            call(fetch_with(net))
        self.assertEqual(len(net.requests), 1)


class RequestsOfAMorning(H.D.Case):
    def morning_requests(self, now, init_start="2026-07-27", upto="2026-07-28"):
        work, net = H.Work(self), H.Net(upto)
        self.assertEqual(work.run(net, ["init", "--mode", "dry", "--start-after", init_start], now).code, 0)
        work.sync_ledger(init_start, upto)
        net.requests.clear()
        net.chart_args.clear()
        result = work.run(net, ["morning", "--mode", "dry"], now)
        return net, result

    def test_four_symbols_once_each_in_order_with_the_exact_url(self):
        net, result = self.morning_requests(H.aware("2026-07-28"))
        self.assertEqual(result.code, 0)
        self.assertEqual([r["symbol"] for r in net.charts()], ["SOXX", "SPY", "IEF", "SOXL"])
        self.assertEqual(len(net.requests), 4)
        for request, (symbol, start, end) in zip(net.charts(), net.chart_args):
            self.assertEqual(start, "2010-02-11")
            self.assertEqual(end, "2026-07-29")
            self.assertEqual(request["url"], expected_url(symbol, start, end))
            self.assertEqual(request["timeout"], 30)
            self.assertEqual(request["headers"]["user-agent"], "Mozilla/5.0 (compatible; soxl-alert-v2)")
            self.assertEqual(request["headers"]["accept"], "application/json")

    def test_end_is_the_day_after_the_new_york_date_of_now(self):
        # the same New York date (2026-07-28 evening, summer time) seen at three clock times: end is 07-29 each time;
        # the UTC date of the third is already the next day, so a UTC date would give 07-30
        cases = [(datetime(2026, 7, 28, 22, 40, tzinfo=UTC), "2026-07-29"),     # 07:40 Japan time of 07-29; New York 18:40 on 07-28
                 (datetime(2026, 7, 28, 21, 0, tzinfo=UTC), "2026-07-29"),      # New York 17:00 on 07-28 (06:00 Japan time)
                 (datetime(2026, 7, 29, 1, 0, tzinfo=UTC), "2026-07-29"),       # New York 21:00 on 07-28, UTC date 07-29
                 (datetime(2026, 7, 29, 3, 59, tzinfo=UTC), "2026-07-29"),      # New York 23:59 on 07-28
                 (datetime(2026, 7, 29, 4, 0, tzinfo=UTC), "2026-07-30")]       # New York 00:00 on 07-29
        for now, end in cases:
            work, net = H.Work(self), H.Net("2026-07-28")
            self.assertEqual(work.run(net, ["init", "--mode", "dry", "--start-after", "2026-07-27"], now).code, 0)
            net.override = {s: OSError("network") for s in H.SYMBOLS}
            result = work.run(net, ["morning", "--mode", "dry"], now)
            self.assertEqual(result.kv["run_outcome"], "STOPPED")
            self.assertEqual(net.chart_args, [("SOXX", "2010-02-11", end)], now.isoformat())

    def test_in_winter_the_new_york_date_uses_the_winter_offset(self):
        for now, end in ((datetime(2026, 12, 1, 3, 0, tzinfo=UTC), "2026-12-01"),       # New York 22:00 on 11-30 (UTC-5)
                         (datetime(2026, 12, 1, 5, 0, tzinfo=UTC), "2026-12-02")):      # New York 00:00 on 12-01
            work, net = H.Work(self), H.Net("2026-11-30")
            self.assertEqual(work.run(net, ["init", "--mode", "dry", "--start-after", "2026-11-20"], now).code, 0)
            net.override = {s: OSError("network") for s in H.SYMBOLS}
            work.run(net, ["morning", "--mode", "dry"], now)
            self.assertEqual(net.chart_args[0][2], end)


class Limit(unittest.TestCase):
    def test_exactly_8_mib_passes_and_one_byte_more_does_not(self):
        net, failures = H.Net(), []
        net.override["SOXX"] = b"x" * R.MAX_BYTES
        self.assertEqual(len(call(fetch_with(net, failures))), R.MAX_BYTES)
        self.assertEqual(failures, [])
        net.override["SOXX"] = b"x" * (R.MAX_BYTES + 1)
        with self.assertRaises(WEB.FetchFailed) as caught:
            call(fetch_with(net, failures))
        self.assertEqual(caught.exception.args, ("size",))
        self.assertEqual(failures, [("SOXX", "size")])
        net.override["SOXX"] = ("size", R.MAX_BYTES * 3)
        with self.assertRaises(WEB.FetchFailed):
            call(fetch_with(net, failures))
        self.assertEqual(failures[-1], ("SOXX", "size"))

    def test_a_status_that_is_not_200_is_a_failure_with_its_digits(self):
        for status, word in ((204, "http_204"), (206, "http_206"), (301, "http_301"), (202, "http_202"), (500, "http_500")):
            net, failures = H.Net(), []
            net.override["SPY"] = ("status", status)
            with self.assertRaises(WEB.FetchFailed) as caught:
                call(fetch_with(net, failures), "SPY")
            self.assertEqual(caught.exception.args, (word,))
            self.assertEqual(failures, [("SPY", word)])


class Words(unittest.TestCase):
    def failure(self, error, symbol="IEF"):
        net, failures = H.Net(), []
        net.override[symbol] = error
        with self.assertRaises(WEB.FetchFailed) as caught:
            call(fetch_with(net, failures), symbol)
        exc = caught.exception
        for text in (str(exc), repr(exc), repr(exc.args)):
            for mark in (H.MARK, H.TOKEN_MARK, H.BODY_MARK, "http://", "https://", "yahoo", "query1"):
                self.assertNotIn(mark, text)
        self.assertIsNone(exc.__context__)
        self.assertIsNone(exc.__cause__)
        self.assertEqual(len(failures), 1)
        return failures[0]

    def test_the_six_words(self):
        url = H.CHART_BASE + "IEF"
        self.assertEqual(self.failure(H.http_error(url, 429)), ("IEF", "http_429"))
        self.assertEqual(self.failure(H.http_error(url, 500)), ("IEF", "http_500"))
        self.assertEqual(self.failure(H.http_error(url, 404)), ("IEF", "http_404"))
        self.assertEqual(self.failure(socket.timeout("timed out " + url)), ("IEF", "timeout"))
        self.assertEqual(self.failure(TimeoutError("timed out " + url)), ("IEF", "timeout"))
        self.assertEqual(self.failure(urllib.error.URLError(TimeoutError("timed out " + url))), ("IEF", "timeout"))   # RP-01
        self.assertEqual(self.failure(urllib.error.URLError(socket.timeout("timed out"))), ("IEF", "timeout"))
        self.assertEqual(self.failure(urllib.error.URLError(ConnectionRefusedError(111, "refused " + url))), ("IEF", "url_error"))
        self.assertEqual(self.failure(urllib.error.URLError(socket.gaierror(-2, "no host " + url))), ("IEF", "url_error"))
        self.assertEqual(self.failure(ConnectionResetError(104, "reset " + url)), ("IEF", "url_error"))
        self.assertEqual(self.failure(RuntimeError("other " + url + H.BODY_MARK)), ("IEF", "other"))
        self.assertEqual(self.failure(OSError("network " + H.MARK)), ("IEF", "other"))
        self.assertEqual(self.failure(ValueError(url)), ("IEF", "other"))

    def test_failures_are_recorded_in_order_across_calls(self):
        net, failures = H.Net(), []
        fetch = fetch_with(net, failures)
        net.override["SOXX"] = H.http_error(H.CHART_BASE + "SOXX", 503)
        net.override["SPY"] = socket.timeout("x")
        for symbol in ("SOXX", "SPY"):
            with self.assertRaises(WEB.FetchFailed):
                call(fetch, symbol)
        self.assertEqual(failures, [("SOXX", "http_503"), ("SPY", "timeout")])

    def test_an_answer_that_is_not_bytes_is_other(self):
        class Odd(H.Resp):
            def read(self, n=-1):
                return "text"
        net, failures = H.Net(), []
        fetch = R.make_fetch(lambda request, timeout=None: Odd(b""), failures)
        with self.assertRaises(WEB.FetchFailed):
            call(fetch)
        self.assertEqual(failures, [("SOXX", "other")])

    def test_without_a_list_nothing_is_recorded_and_it_still_raises(self):
        net = H.Net()
        net.override["SOXX"] = OSError("x")
        with self.assertRaises(WEB.FetchFailed):
            call(R.make_fetch(net))

    def test_the_words_are_the_fixed_set(self):
        for word in ("timeout", "url_error", "size", "other"):
            self.assertIn(word, WEB.FETCH_WORDS)
        self.assertEqual(len(WEB.FETCH_WORDS), 4)


class WordsInTheRecord(H.D.Case):
    def test_the_record_of_a_morning_and_of_check_source_carry_symbol_and_word(self):
        cases = [("SOXX", H.http_error(H.CHART_BASE + "SOXX", 429), "SOXX http_429"),
                 ("SPY", H.http_error(H.CHART_BASE + "SPY", 500), "SPY http_500"),
                 ("IEF", socket.timeout("x"), "IEF timeout"),
                 ("SOXL", urllib.error.URLError(ConnectionRefusedError(111, "r")), "SOXL url_error")]
        for symbol, error, word in cases:
            work, net = H.Work(self), H.Net("2026-07-28")
            self.assertEqual(work.init(net, "dry", start="2026-07-27").code, 0)
            net.override[symbol] = error
            result = work.morning(net, "dry", "2026-07-28", start="2026-07-27")
            self.assertEqual(result.all("fetch_failure"), [word])
            self.assertEqual(H.leaks(result.text), [])
            self.assertNotIn("Error", result.text.replace("InputError", ""))      # no exception name of the fetch either
            checked = work.cmd(net, "check-source", "dry", "2026-07-28")
            self.assertEqual(checked.code, 1)
            self.assertIn(word, checked.all("fetch_failure"))
            self.assertEqual(H.leaks(checked.text), [])


if __name__ == "__main__":
    unittest.main()
