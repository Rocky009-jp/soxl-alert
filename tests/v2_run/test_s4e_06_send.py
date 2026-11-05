"""S4E-06, S4E-07 and the post half of S4E-08: the answers of the Discord sender (one request per part, no retry, nothing after a
failed part), the URL rules, the split of a long text and the swap of the heading just before sending, the exact shape of a post,
and the exit codes of a live morning."""
import hashlib
import json
import tempfile
import unittest

import s4e_helpers as H

R, WEB = H.R, H.WEB
D, N = H.D, H.N
TEXT = R.PREVIEW_HEAD + " 対象D=2026-07-21\n本文の行\n"


def sender(net, url=H.WEBHOOK):
    return R.DiscordSender(url, net)


def long_text(lines=100, width=40):
    return "\n".join("行%03d " % i + "あ" * width for i in range(lines))


class Answers(unittest.TestCase):
    def test_every_row_of_the_table_for_a_one_part_text(self):
        table = {"204": "SENT", "200": "SENT", "202": "SENT",
                 "400": "NOT_STARTED", "401": "NOT_STARTED", "404": "NOT_STARTED", "429": "NOT_STARTED",
                 "refused": "NOT_STARTED", "dns": "NOT_STARTED",
                 "500": "UNKNOWN", "503": "UNKNOWN", "timeout": "UNKNOWN", "url_timeout": "UNKNOWN", "other": "UNKNOWN"}
        for behaviour, want in table.items():
            net = H.Net()
            net.discord = [behaviour]
            self.assertEqual(sender(net).send(TEXT), want, behaviour)
            self.assertEqual(len(net.posts()), 1, behaviour)

    def test_a_failure_of_a_later_part_is_unknown_and_nothing_follows_it(self):
        text = long_text()
        parts = len(R.split_text(R.live_text(text)))
        self.assertEqual(parts, 3)
        for behaviour in ("400", "401", "429", "500", "refused", "dns", "timeout", "other"):
            for failing in (1, 2):
                net = H.Net()
                net.discord = ["204"] * failing + [behaviour]
                self.assertEqual(sender(net).send(text), "UNKNOWN", (behaviour, failing))
                self.assertEqual(len(net.posts()), failing + 1, (behaviour, failing))        # one request per part, then stop
        for behaviour in ("400", "refused"):                                                 # the first part: NOT_STARTED
            net = H.Net()
            net.discord = [behaviour]
            self.assertEqual(sender(net).send(text), "NOT_STARTED")
            self.assertEqual(len(net.posts()), 1)

    def test_all_parts_are_sent_once_each_in_order(self):
        text = long_text()
        net = H.Net()
        self.assertEqual(sender(net).send(text), "SENT")
        posted = [p["content"] for p in net.posts()]
        self.assertEqual(posted, R.split_text(R.live_text(text)))
        self.assertEqual([p.split("\n")[0] for p in posted], ["（1/3）", "（2/3）", "（3/3）"])

    def test_no_retry_whatever_the_failure(self):
        for behaviour in ("429", "500", "503", "timeout", "refused", "dns", "other"):
            net = H.Net()
            net.discord = [behaviour, "204", "204"]
            sender(net).send(TEXT)
            self.assertEqual(len(net.posts()), 1, behaviour)
            self.assertEqual(net.discord, ["204", "204"], behaviour)


class UrlRules(unittest.TestCase):
    def test_a_url_that_is_not_a_webhook_is_never_posted_to(self):
        for url in (None, "", "   ", 123, b"https://discord.com/api/webhooks/1/x", "http://discord.com/api/webhooks/1/x",
                    "https://discord.com/api/webhooks", "https://example.com/api/webhooks/1/x",
                    "https://discord.com.evil.example/api/webhooks/1/x", "ftp://discord.com/api/webhooks/1/x",
                    "https://discord.com/api/webhooks/1/x?thread_id=1", "https://discord.com/api/webhooks/1/x?wait=true",
                    "https://discord.com/api/webhooks/1/トークン", "https://discord.com/api/webhooks/1/x y",
                    "https://discord.com/api/webhooks/1/x\n", "https://discord.com/api/webhooks/1/x\r\nHost: a"):
            net = H.Net()
            self.assertEqual(sender(net, url).send(TEXT), "NOT_STARTED", repr(url))
            self.assertEqual(net.requests, [], repr(url))

    def test_the_two_hosts_are_accepted_and_a_text_that_is_not_a_string_is_not_posted(self):
        for url in ("https://discord.com/api/webhooks/1/x", "https://discordapp.com/api/webhooks/1/x"):
            net = H.Net()
            self.assertEqual(sender(net, url).send(TEXT), "SENT")
            self.assertEqual(net.posts()[0]["url"], url + "?wait=true")
        net = H.Net()
        self.assertEqual(sender(net).send(None), "NOT_STARTED")
        self.assertEqual(sender(net).send(b"bytes"), "NOT_STARTED")
        self.assertEqual(net.requests, [])

    def test_the_url_is_not_in_the_repr_or_in_anything_that_is_raised(self):
        s = sender(H.Net())
        self.assertNotIn(H.TOKEN_MARK, repr(s))
        self.assertNotIn(H.TOKEN_MARK, str(s) + repr(vars(s).keys()))
        self.assertEqual(repr(R.DrySender()), "DrySender()")


class Split(unittest.TestCase):
    def test_1900_characters_are_one_part_and_1901_are_two(self):
        self.assertEqual(R.split_text("a" * 1900), ["a" * 1900])
        parts = R.split_text("a" * 950 + "\n" + "b" * 950)           # 1901 characters
        self.assertEqual(len("a" * 950 + "\n" + "b" * 950), 1901)
        self.assertEqual(parts, ["（1/2）\n" + "a" * 950, "（2/2）\n" + "b" * 950])
        self.assertEqual(R.split_text(""), [""])
        self.assertEqual(R.split_text("あ" * 1900), ["あ" * 1900])

    def test_every_part_starts_with_its_number_is_at_most_2000_and_the_lines_come_back_in_order(self):
        for text in (long_text(100, 40), long_text(300, 10), "\n".join("x" * 1899 for _ in range(7)),
                     "\n".join(["", "a" * 1000, "", "", "b" * 900, "c" * 1000, ""] * 5)):
            parts = R.split_text(text)
            self.assertGreater(len(parts), 1)
            total = len(parts)
            body = []
            for index, part in enumerate(parts, 1):
                head, _sep, rest = part.partition("\n")
                self.assertEqual(head, "（%d/%d）" % (index, total))
                self.assertLessEqual(len(part), 2000)
                self.assertLessEqual(len(rest), R.LIMIT)
                body.append(rest)
            self.assertEqual("\n".join(body), text)

    def test_a_line_over_the_limit_is_cut_and_every_part_is_still_at_most_2000(self):
        text = "a" * 5000
        parts = R.split_text(text)
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(len(p) <= 2000 for p in parts))
        self.assertEqual("".join(p.partition("\n")[2] for p in parts), text)
        mixed = "head\n" + "z" * 4000 + "\ntail"
        parts = R.split_text(mixed)
        self.assertTrue(all(len(p) <= 2000 for p in parts))
        self.assertEqual("".join(p.partition("\n")[2] for p in parts).replace("head", "").count("z"), 4000)
        self.assertTrue(parts[-1].endswith("tail"))

    def test_a_thousand_parts_still_fit_2000(self):
        parts = R.split_text("\n".join("y" * 1899 for _ in range(1200)))
        self.assertEqual(len(parts), 1200)
        self.assertTrue(all(len(p) <= 2000 for p in parts))


class Heading(H.D.Case):
    def test_the_live_text_swaps_only_the_heading(self):
        self.assertEqual(R.live_text(TEXT), R.LIVE_HEAD + " 対象D=2026-07-21\n本文の行\n")
        self.assertEqual(R.live_text("no heading"), "no heading")
        self.assertEqual(R.live_text(R.PREVIEW_HEAD * 2), R.LIVE_HEAD * 2)

    def test_a_live_morning_posts_the_live_heading_and_the_outbox_keeps_the_original(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self.assertEqual(work.init(net, "live").code, 0)
        result = work.morning(net, "live", "2026-07-21")
        self.assertEqual(result.code, 0)
        self.assertIsNone(result.block())
        posted = net.posts()[0]["content"]
        self.assertNotIn("プレビュー", posted)
        self.assertNotIn(R.PREVIEW_HEAD, posted)
        self.assertIn(R.LIVE_HEAD, posted)
        claim = json.loads(work.remote.blob("v2-outbox", "2026-07-21-morning.claim.json").decode("utf-8"))
        self.assertIn(R.PREVIEW_HEAD, claim["text"])
        self.assertNotIn(R.LIVE_HEAD, claim["text"])
        self.assertEqual(posted, claim["text"].replace(R.PREVIEW_HEAD, R.LIVE_HEAD))
        # the recorded hash is the hash of the text before the swap
        parent = tempfile.mkdtemp(prefix="v2s4e_mirror_")
        self.addCleanup(__import__("shutil").rmtree, parent, True)
        outbox = H.GS.GitOutbox(H.GS.Git(work.dir), "v2-outbox", parent, H.C.clock)
        entry = [e for e in N.outbox_status(outbox, "2026-07-21") if e.kind == "morning"][0]
        self.assertEqual(entry.text_sha256, hashlib.sha256(claim["text"].encode("utf-8")).hexdigest())
        self.assertNotEqual(entry.text_sha256, hashlib.sha256(posted.encode("utf-8")).hexdigest())

    def test_a_resend_goes_through_the_same_swap(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self.assertEqual(work.init(net, "live").code, 0)
        net.discord = ["500"]
        self.assertEqual(work.morning(net, "live", "2026-07-21").code, 1)
        net.discord = []
        again = work.cmd(net, "resend", "live", "2026-07-21", "09:00",
                         ["--date", "2026-07-21", "--kind", "morning", "--request-id", "r1"], env={R.SECRET_NAME: H.WEBHOOK})
        self.assertEqual(again.code, 0)
        body = net.posts()[-1]["content"]
        self.assertTrue(body.startswith("【再送】"))
        self.assertNotIn(R.PREVIEW_HEAD, body)
        self.assertIn(R.LIVE_HEAD, body)

    def test_the_dry_record_keeps_the_preview_heading(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self.assertEqual(work.init(net, "dry").code, 0)
        result = work.morning(net, "dry", "2026-07-21")
        self.assertIn(R.PREVIEW_HEAD, result.block())
        self.assertNotIn(R.LIVE_HEAD, result.block())
        sender_ = R.DrySender()
        self.assertEqual(sender_.send(TEXT), "SENT")
        self.assertEqual(sender_.texts, [TEXT])


class ShapeOfAPost(unittest.TestCase):
    def test_method_url_headers_body_and_timeout(self):
        net = H.Net()
        self.assertEqual(sender(net).send(TEXT + "あ"), "SENT")
        post = net.posts()[0]
        self.assertEqual(post["method"], "POST")
        self.assertEqual(post["url"], H.WEBHOOK + "?wait=true")
        self.assertEqual(post["headers"]["content-type"], "application/json")
        self.assertEqual(post["headers"]["user-agent"], "Mozilla/5.0 (compatible; soxl-alert-v2)")
        self.assertEqual(post["timeout"], 20)
        body = json.loads(post["data"].decode("utf-8"))
        self.assertEqual(sorted(body), ["allowed_mentions", "content"])
        self.assertEqual(body["allowed_mentions"], {"parse": []})
        self.assertEqual(body["content"], R.live_text(TEXT + "あ"))
        self.assertIn("あ".encode("utf-8"), post["data"])               # UTF-8, not \u escapes
        self.assertEqual(sorted(post["headers"]), ["content-type", "user-agent"])

    def test_every_post_of_a_long_text_blocks_mentions(self):
        net = H.Net()
        sender(net).send(long_text() + "\n@everyone @here <@123>")
        self.assertGreater(len(net.posts()), 1)
        self.assertTrue(all(p["mentions"] == {"parse": []} for p in net.posts()))
        self.assertTrue(all(p["timeout"] == 20 for p in net.posts()))


class LiveMornings(H.D.Case):
    def run_with(self, behaviours):
        work, net = H.Work(self), H.Net("2026-07-21")
        self.assertEqual(work.init(net, "live").code, 0)
        net.discord = list(behaviours)
        return work, net, work.morning(net, "live", "2026-07-21")

    def test_exit_codes_of_a_live_morning(self):
        for behaviour, delivery, code in (("204", "SENT", 0), ("400", "NOT_SENT", 1), ("401", "NOT_SENT", 1), ("429", "NOT_SENT", 1),
                                          ("500", "UNKNOWN", 1), ("503", "UNKNOWN", 1), ("timeout", "UNKNOWN", 1),
                                          ("refused", "NOT_SENT", 1), ("dns", "NOT_SENT", 1)):
            work, net, result = self.run_with([behaviour])
            self.assertEqual((result.kv["delivery"], result.code), (delivery, code), behaviour)
            self.assertEqual(len(net.posts()), 1, behaviour)
            self.assertEqual(H.leaks(result.text), [], behaviour)

    def test_the_second_run_of_the_same_morning_does_not_send_again(self):
        for behaviour in ("500", "400", "timeout"):
            work, net, first = self.run_with([behaviour])
            second = work.morning(net, "live", "2026-07-21", hhmm="08:40")
            self.assertEqual((second.kv["delivery"], second.code), ("SKIPPED_CLAIMED", 0), behaviour)
            self.assertEqual(len(net.posts()), 1, behaviour)

    def test_a_live_morning_without_the_secret_or_with_a_wrong_one_sends_nothing(self):
        for env in ({}, {R.SECRET_NAME: ""}, {R.SECRET_NAME: "https://example.com/api/webhooks/1/" + H.TOKEN_MARK},
                    {R.SECRET_NAME: H.WEBHOOK + "?thread_id=1"}):
            work, net = H.Work(self), H.Net("2026-07-21")
            self.assertEqual(work.init(net, "live").code, 0)
            net.upto = "2026-07-21"
            work.sync_ledger(H.START, "2026-07-21")
            result = work.cmd(net, "morning", "live", "2026-07-21", env=env)
            self.assertEqual((result.kv["delivery"], result.kv["send_status"], result.code), ("NOT_SENT", "NOT_SENT", 1))
            self.assertEqual(net.posts(), [])
            self.assertEqual(H.leaks(result.text), [])


if __name__ == "__main__":
    unittest.main()
