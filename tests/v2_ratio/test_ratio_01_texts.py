"""RATIO-01 .. RATIO-06: the invested ratio in the morning notice (R-01, R-02, R-04, R-05 of the request).

Expected texts are literals written here; the ratio numbers are compared with rule.ratio of the judgment; the texts of the
days that must not change are compared with golden_2c7320f.json, which ratio_cases.build made once at the code start
2c7320f. Nothing here opens a socket, reads the clock or writes outside a temporary directory."""
import dataclasses
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _p in (HERE, ROOT, os.path.join(ROOT, "tests", "v2_core"), os.path.join(ROOT, "tests", "v2_notify")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ratio_cases as R  # noqa: E402
import s4b_helpers as H  # noqa: E402  (existing helper; it also disables sockets)
import v2_helpers as h  # noqa: E402  (existing helper of the core tests)
import v2_daily_run as A  # noqa: E402
import v2_notify as N  # noqa: E402
from v2_core import display  # noqa: E402
from v2_core.engine import RuleResult, RuleStatus, RunClass  # noqa: E402
from v2_core.state import MarketState  # noqa: E402
from v2_core.tri import Tri  # noqa: E402
from v2_run.web import LIMIT, live_text, split_text  # noqa: E402

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 1, 10, 7, 40, tzinfo=JST)
SESSIONS = h.make_sessions(R.DATES)
with open(os.path.join(HERE, "golden_2c7320f.json"), encoding="utf-8") as _f:
    GOLDEN = json.load(_f)
RESULTS = R.results(ROOT)

# (headline, body line) per signal scenario, written out by hand from the request (section 2)
EXPECTED = {
    "exfear_confirmed": ("投入比率：利用可能資金の100%",
                         "▶ 投入比率：**利用可能資金の100%**（極端恐怖・確認済み、比率のみ）"),
    "normal_confirmed": ("投入比率：利用可能資金の100%",
                         "▶ 投入比率：**利用可能資金の100%**（通常買い・確認済み、比率のみ）"),
    "trend_confirmed": ("投入比率：利用可能資金の25%（手元確認が必要）",
                        "▶ 投入比率：**利用可能資金の25%**（トレンド参加・確認済み、比率のみ。0株か再参加かは手元確認）"),
    "exfear_unconfirmed": ("投入比率の目安：利用可能資金の100%（参考・未確認）",
                           "▶ 投入比率の目安：利用可能資金の100%（参考・未確認、比率のみ）"),
    "normal_unconfirmed": ("投入比率の目安：利用可能資金の100%（参考・未確認）",
                           "▶ 投入比率の目安：利用可能資金の100%（参考・未確認、比率のみ）"),
}


def done_report(text, headline=None, d=R.D):
    return A.RunReport(A.DONE, d, (), "PREPARED", text, headline=headline)


def notice_of(result):
    """The morning notice of a judgment, made the way run_morning makes the report (the text and the headline)."""
    return N.compose_notice(done_report(display.render_message(result), display.ratio_headline(result)), SESSIONS, NOW)


class SignalDays(unittest.TestCase):
    """R-01: the four kinds of a day with a signal, in the first line and in the body."""

    def test_the_headline_and_the_body_line_are_as_written_in_the_request(self):
        self.assertEqual(sorted(EXPECTED), sorted(R.SIGNAL))
        for name, (headline, line) in EXPECTED.items():
            result = RESULTS[name]
            self.assertEqual(display.ratio_headline(result), headline, name)
            self.assertEqual(display.ratio_line(result), line, name)

    def test_the_first_line_of_the_notice_and_the_body_line(self):
        for name, (headline, line) in EXPECTED.items():
            text = notice_of(RESULTS[name]).text
            lines = text.splitlines()
            self.assertEqual(lines[0], "【SOXL日次】対象D=%s ／ %s" % (R.D, headline), name)
            self.assertTrue(lines[1].startswith(display.render_message(RESULTS[name]).splitlines()[0]), name)
            self.assertIn("実行区分", lines[1])
            self.assertEqual(lines[2], line, name)               # right under the run-class line
            self.assertEqual(text.count("投入比率"), 2, name)         # the two places, nowhere else

    def test_the_number_is_the_ratio_of_the_judgment_and_not_a_written_in_string(self):
        for name in R.SIGNAL:
            result = RESULTS[name]
            rule = next(r for r in result.rules.values() if r.status in (RuleStatus.MET, RuleStatus.UNCONFIRMED))
            self.assertIn("利用可能資金の%d%%" % rule.ratio, display.ratio_headline(result))
            self.assertIn("利用可能資金の%d%%" % rule.ratio, display.ratio_line(result))
        # a changed ratio of the rule shows in both places: nothing is copied from a literal
        result = RESULTS["trend_confirmed"]
        rules = dict(result.rules)
        rules["TREND"] = dataclasses.replace(rules["TREND"], ratio=40)
        changed = dataclasses.replace(result, rules=rules)
        self.assertIn("利用可能資金の40%（手元確認が必要）", display.ratio_headline(changed))
        self.assertIn("**利用可能資金の40%**", display.ratio_line(changed))

    def test_only_a_confirmed_ratio_is_bold_and_only_an_unconfirmed_one_says_reference(self):
        for name, (headline, line) in EXPECTED.items():
            confirmed = name.endswith("_confirmed")
            self.assertEqual("**" in line, confirmed, name)
            self.assertEqual("参考・未確認" in line, not confirmed, name)
            self.assertEqual("参考・未確認" in headline, not confirmed, name)
            self.assertEqual("目安" in line, not confirmed, name)
            self.assertEqual("目安" in headline, not confirmed, name)
            self.assertEqual("確認済み" in line, confirmed, name)
            self.assertEqual("手元確認" in headline, name == "trend_confirmed", name)

    def test_the_first_rule_is_used_when_several_rules_hold(self):
        # the same choice as _profile_lines: met[0] in the order EXFEAR, NORMAL, TREND
        result = RESULTS["exfear_confirmed"]
        rules = dict(result.rules)
        rules["TREND"] = RuleResult("TREND", RuleStatus.MET, 25, ["fg_at_least_30"])
        both = dataclasses.replace(result, rules=rules)
        self.assertEqual(display.ratio_headline(both), EXPECTED["exfear_confirmed"][0])
        rules = dict(result.rules)
        rules["EXFEAR"] = dataclasses.replace(rules["EXFEAR"], status=RuleStatus.UNCONFIRMED)
        rules["TREND"] = RuleResult("TREND", RuleStatus.MET, 25, ["fg_at_least_30"])
        first_unconfirmed = dataclasses.replace(result, rules=rules)
        self.assertEqual(display.ratio_headline(first_unconfirmed), EXPECTED["exfear_unconfirmed"][0])

    def test_an_unconfirmed_trend_rule_is_a_reference_without_the_hand_check_words(self):
        result = RESULTS["trend_confirmed"]
        rules = dict(result.rules)
        rules["TREND"] = dataclasses.replace(rules["TREND"], status=RuleStatus.UNCONFIRMED)
        reference = dataclasses.replace(result, rules=rules, run_class=RunClass.REFERENCE_UNCONFIRMED)
        self.assertEqual(display.ratio_headline(reference), "投入比率の目安：利用可能資金の25%（参考・未確認）")
        self.assertEqual(display.ratio_line(reference), "▶ 投入比率の目安：利用可能資金の25%（参考・未確認、比率のみ）")

    def test_no_shares_amounts_orders_or_sales_are_added(self):
        for name in R.SIGNAL:
            for text in EXPECTED[name]:
                for word in ("株", "ドル", "$", "円", "成行", "指値", "売却", "注文", "購入しました", "買ってください"):
                    if word == "株" and name == "trend_confirmed" and "0株か再参加" in text:
                        continue                # the hand check the request asks for ("0株か再参加かは手元確認")
                    self.assertNotIn(word, text, (name, word))

    def test_only_the_two_signal_classes_get_a_ratio_whatever_the_rules_say(self):
        # found by defect injection: the class is checked on its own, not only through the status of the rules
        result = RESULTS["exfear_confirmed"]
        for run_class in (RunClass.NO_SIGNAL, RunClass.WAITING_FG, RunClass.DATA_ERROR, RunClass.CONFLICT):
            odd = dataclasses.replace(result, run_class=run_class)
            self.assertIsNone(display.ratio_headline(odd), run_class)
            self.assertIsNone(display.ratio_line(odd), run_class)
        for run_class in (RunClass.CONDITION_MET, RunClass.REFERENCE_UNCONFIRMED):
            odd = dataclasses.replace(result, run_class=run_class)
            self.assertIsNotNone(display.ratio_headline(odd), run_class)

    def test_a_missing_or_odd_ratio_adds_nothing(self):
        result = RESULTS["exfear_confirmed"]
        for bad in (None, "100", 100.0, True):
            rules = dict(result.rules)
            rules["EXFEAR"] = dataclasses.replace(rules["EXFEAR"], ratio=bad)
            odd = dataclasses.replace(result, rules=rules)
            self.assertIsNone(display.ratio_headline(odd), bad)
            self.assertIsNone(display.ratio_line(odd), bad)


class DaysWithoutEmphasis(unittest.TestCase):
    """R-02: what does not change, compared with the texts that 2c7320f made."""

    def test_every_day_without_a_signal_is_character_for_character_the_old_text(self):
        for name in R.NO_SIGNAL:
            result = RESULTS[name]
            self.assertIsNone(display.ratio_headline(result), name)
            self.assertIsNone(display.ratio_line(result), name)
            self.assertEqual(display.render_message(result), GOLDEN["body:" + name], name)
            self.assertEqual(display.render(result), GOLDEN["render:" + name], name)
            if name in ("data_error", "conflict"):
                continue
            report = done_report(display.render_message(result), display.ratio_headline(result))
            self.assertIsNone(report.headline, name)
            self.assertEqual(N.compose_notice(report, SESSIONS, NOW).text, GOLDEN["notice:" + name], name)
            self.assertNotIn("投入比率", GOLDEN["notice:" + name])

    def test_the_halt_and_the_error_notices_are_the_old_text(self):
        halt = A.RunReport(A.STALE, R.D, (), None, "plain notice", code="run_session_unconfirmed", field="sessions",
                           detail="2026-01-12")
        self.assertEqual(N.compose_notice(halt, SESSIONS, NOW).text, GOLDEN["halt"])
        self.assertEqual(N.compose_error_notice(R.D, "run_args_invalid", "RunError").text, GOLDEN["error"])

    def test_a_signal_day_is_the_old_text_plus_the_two_lines_and_nothing_else(self):
        for name, (headline, line) in EXPECTED.items():
            body = display.render_message(RESULTS[name]).split("\n")
            old_body = GOLDEN["body:" + name].split("\n")
            self.assertEqual(len(body), len(old_body) + 1, name)
            self.assertEqual(body[:1] + body[2:], old_body, name)              # drop the one new line, the rest is equal
            self.assertEqual(body[1], line, name)
            new_notice = notice_of(RESULTS[name]).text.split("\n")
            old_notice = GOLDEN["notice:" + name].split("\n")
            self.assertEqual(len(new_notice), len(old_notice) + 1, name)
            self.assertEqual(new_notice[0], old_notice[0] + " ／ " + headline, name)
            self.assertEqual(new_notice[1:2] + new_notice[3:], old_notice[1:], name)
            self.assertEqual(new_notice[2], line, name)
            self.assertEqual(display.render(RESULTS[name]).split("\n")[1], line, name)

    def test_the_summary_is_untouched_on_every_day(self):
        for name, result in RESULTS.items():
            old_summary = "――完了サマリ" + GOLDEN["render:" + name].split("\n\n――完了サマリ", 1)[1]
            self.assertEqual(display.render_summary(result), old_summary, name)


class RunReportHeadline(unittest.TestCase):
    def test_the_default_is_none_and_the_value_is_part_of_equality(self):
        self.assertIsNone(done_report("text").headline)
        self.assertEqual(done_report("text", "投入比率：利用可能資金の100%"), done_report("text", "投入比率：利用可能資金の100%"))
        self.assertNotEqual(done_report("text"), done_report("text", "投入比率：利用可能資金の100%"))
        self.assertNotIn("投入比率", repr(done_report("text", "投入比率：利用可能資金の100%")))

    def test_a_headline_is_one_short_printable_line_and_only_of_a_done_report(self):
        for bad in ("a\nb", "a\rb", "a b", "a\x0bb", "a\x00b", "", " a", "a ", 5, b"a", "x" * 81, "a\tb"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                done_report("text", bad)
        for outcome in (A.STALE, A.STOPPED):
            with self.assertRaises(ValueError):
                A.RunReport(outcome, R.D, (), None, "text", code="c", headline="投入比率：利用可能資金の100%")
        self.assertEqual(done_report("text", "x" * 80).headline, "x" * 80)

    def test_every_headline_the_display_makes_is_accepted(self):
        for name in R.SIGNAL:
            self.assertIsNotNone(done_report("text", display.ratio_headline(RESULTS[name])).headline)

    def test_a_halt_report_never_carries_the_ratio(self):
        halt = A.RunReport(A.STOPPED, R.D, (), None, "plain notice", code="run_args_invalid")
        self.assertIsNone(halt.headline)
        self.assertNotIn("投入比率", N.compose_notice(halt, SESSIONS, NOW).text)

    def test_compose_does_not_parse_the_text(self):
        # a text that holds the words but a report without a headline: the first line stays as it was
        report = done_report("【…】\n▶ 投入比率：**利用可能資金の100%**\nx")
        self.assertEqual(N.compose_notice(report, SESSIONS, NOW).text.splitlines()[0], "【SOXL日次】対象D=%s" % R.D)


class OneLineAndSplit(unittest.TestCase):
    """R-04: the first line is one line and survives the live heading and the 1900-character split."""

    def test_the_first_line_has_no_line_break_and_is_short(self):
        for name in R.SIGNAL:
            text = notice_of(RESULTS[name]).text
            first = text.split("\n", 1)[0]
            self.assertEqual(len(first.splitlines()), 1)
            self.assertTrue(first.startswith("【SOXL日次】対象D=%s ／ " % R.D), name)
            self.assertLess(len(first), 80, name)

    def test_the_live_text_changes_only_the_preview_heading(self):
        for name in R.SIGNAL:
            text = notice_of(RESULTS[name]).text
            live = live_text(text)
            self.assertEqual(live.split("\n")[0], text.split("\n")[0])
            self.assertEqual(live.split("\n")[2], text.split("\n")[2])
            self.assertTrue(live.split("\n")[1].startswith("【詳細】"))
            self.assertEqual(len(split_text(live)), 1)

    def test_a_long_notice_is_cut_at_line_ends_and_the_first_line_stays_whole(self):
        for name in R.SIGNAL:
            text = notice_of(RESULTS[name]).text
            long_text = text + "\n" + "\n".join("  行%03d " % i + "あ" * 60 for i in range(40))
            self.assertGreater(len(long_text), LIMIT)
            parts = split_text(live_text(long_text))
            self.assertGreater(len(parts), 1)
            head = parts[0].split("\n")
            self.assertEqual(head[0], "（1/%d）" % len(parts))
            self.assertEqual(head[1], text.split("\n")[0], name)
            self.assertTrue(head[2].startswith("【詳細】 対象D="), name)
            self.assertEqual(head[3], display.ratio_line(RESULTS[name]), name)
            for part in parts:
                self.assertLessEqual(len(part), LIMIT + 12)


class RealDayOfThe19th(unittest.TestCase):
    """R-05: the text of the real morning of D=2026-11-19 (made by 2c7320f), rebuilt: only the two lines are added."""

    def old_lines(self):
        with open(os.path.join(HERE, "real_20261119_2c7320f.txt"), encoding="utf-8") as f:
            return f.read().rstrip("\n").split("\n")

    def rebuilt_result(self):
        dates = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23"]

        class Series(h.StubSeries):
            def through(self, d):
                return Series([r for r in self.rows.values() if r.date <= d])._copy_closes(self)

            def description(self):                # the shape of the real series (4,220 rows from 2010-02-11)
                return {"price_definition": "adj_close_total_return",
                        "soxl_close_definition": "close_split_adjusted_not_dividend_adjusted", "rows": 4220,
                        "first_date": "2010-02-11", "last_date": "2026-11-19",
                        "input_manifest": [{"sha256": "d5c99d9b6fc2" + "0" * 52}]}

        series = Series([h.row(d, **h.WEAK) for d in dates])
        series.closes["2026-11-19"] = 45.29999923706055
        sessions = h.make_sessions(dates)
        observation = h.obs("r", "2026-11-19", 18, hour=21)
        observation["observed_at_iso8601"] = "2026-11-19T21:26:00+00:00"
        from v2_core.engine import evaluate_day
        return evaluate_day(MarketState("2026-11-18", Tri.TRUE, 0, Tri.FALSE), "2026-11-19", series, sessions,
                            [observation]), sessions

    def test_the_rebuilt_old_text_is_the_real_one_without_the_two_lines(self):
        result, sessions = self.rebuilt_result()
        text = N.compose_notice(done_report(display.render_message(result), None, "2026-11-19"), sessions, NOW).text
        # the rebuild without the new lines must be the real text: the check that the rebuild is the real day
        without = [line for line in text.split("\n") if not line.startswith("▶ 投入比率")]
        self.assertEqual(without, self.old_lines())

    def test_the_new_text_adds_exactly_the_two_lines(self):
        result, sessions = self.rebuilt_result()
        new = notice_of_with(result, sessions).split("\n")
        old = self.old_lines()
        self.assertEqual(len(new), len(old) + 1)
        self.assertEqual(new[0], old[0] + " ／ 投入比率：利用可能資金の100%")
        self.assertEqual(new[1], old[1])
        self.assertEqual(new[2], "▶ 投入比率：**利用可能資金の100%**（極端恐怖・確認済み、比率のみ）")
        self.assertEqual(new[3:], old[2:])


    def test_the_real_day_is_one_part_and_the_first_line_is_the_first_line_of_the_message(self):
        # the real day is about 1,000 characters: one message, whose first line (the one a phone shows) is the headline
        result, sessions = self.rebuilt_result()
        text = live_text(notice_of_with(result, sessions))
        self.assertLess(len(text), LIMIT)
        parts = split_text(text)
        self.assertEqual(len(parts), 1)
        lines = parts[0].split("\n")
        self.assertEqual(lines[0], "【SOXL日次】対象D=2026-11-19 ／ 投入比率：利用可能資金の100%")
        self.assertEqual(lines[1].split(" ")[0], "【詳細】")
        self.assertEqual(lines[2], "▶ 投入比率：**利用可能資金の100%**（極端恐怖・確認済み、比率のみ）")


def notice_of_with(result, sessions):
    report = done_report(display.render_message(result), display.ratio_headline(result), result.d)
    return N.compose_notice(report, sessions, NOW).text


class EndToEnd(H.Case):
    """The real chain: run_morning -> compose_notice -> the outbox and the sender (a double)."""

    def world(self, per_date, base):
        self.w = H.P.World(0, per_date=per_date)
        for i in (1, 2, 3):
            self.w.ledger.append(H.P.obs("R%d" % i, H.D[i], base))

    def test_a_confirmed_signal_morning_sends_the_ratio_in_both_places(self):
        self.world({H.D[3]: dict(soxx=110.0, rsi=56.0, shd=1.0, prev_rsi=54.0)}, 35.0)
        now = H.now_at(H.D[3])
        reference = self.reference(now)
        self.assertEqual(reference.outcome, "DONE")
        self.assertEqual(reference.headline, "投入比率：利用可能資金の25%（手元確認が必要）")
        self.assertIn("▶ 投入比率：**利用可能資金の25%**（トレンド参加・確認済み、比率のみ。0株か再参加かは手元確認）",
                      reference.message.splitlines())
        report = self.job(now)
        self.assertEqual(report.delivery, "SENT")
        lines = self.last_text().splitlines()
        self.assertEqual(lines[0], "【SOXL日次】対象D=%s ／ 投入比率：利用可能資金の25%%（手元確認が必要）" % H.D[3])
        self.assertEqual(lines[2], "▶ 投入比率：**利用可能資金の25%**（トレンド参加・確認済み、比率のみ。0株か再参加かは手元確認）")
        self.assertEqual(report.d, H.D[3])
        self.assertEqual(report.kind, "morning")                       # the key (<D>-morning) is the same as before

    def test_a_morning_without_a_signal_sends_the_old_first_line(self):
        self.world({}, 35.0)
        now = H.now_at(H.D[3])
        reference = self.reference(now)
        self.assertIsNone(reference.headline)
        self.assertEqual(self.job(now).delivery, "SENT")
        self.assertEqual(self.last_text().splitlines()[0], "【SOXL日次】対象D=%s" % H.D[3])
        self.assertNotIn("投入比率", self.last_text())

    def test_the_outbox_key_and_the_hash_follow_the_text_that_was_sent(self):
        self.world({H.D[3]: dict(soxx=110.0, rsi=56.0, shd=1.0, prev_rsi=54.0)}, 35.0)
        now = H.now_at(H.D[3])
        reference = self.reference(now)
        notice = N.compose_notice(reference, self.w.sessions, now)
        self.assertEqual(notice.key, "%s-morning" % H.D[3])
        self.assertEqual(notice.text_sha256, H.sha(notice.text))
        self.job(now)
        self.assertEqual(self.last_text(), notice.text)
        self.assertEqual(self.job(now).delivery, "SKIPPED_CLAIMED")      # a second run is still not sent twice

    def test_an_error_or_halt_morning_has_no_ratio(self):
        self.world({H.D[3]: dict(soxx=110.0, rsi=56.0, shd=1.0, prev_rsi=54.0)}, 35.0)
        self.w.sessions = H.P.make_sessions(unconfirmed=(H.D[3],))
        now = H.now_at(H.D[3])
        self.job(now)
        self.assertNotIn("投入比率", self.last_text())


if __name__ == "__main__":
    unittest.main()
