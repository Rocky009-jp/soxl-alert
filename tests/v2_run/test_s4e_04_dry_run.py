"""S4E-04: init --mode dry, then five mornings (at least 60 minutes after each close): every morning is DONE with a judgment that
was "sent" to the dry sender (nothing reaches the fake Discord), the exit code is 0, the record has the text block and the sources
and times; the same morning again is SKIPPED_CLAIMED. The same five days run directly over the research fixture give the same
outcome and the same text apart from the input fingerprint."""
import json
import re
import unittest

import s4e_helpers as H
from v2_core.fixture import load_research_fixture

D, I = H.D, H.I
DAYS = H.days("2026-07-21", "2026-07-28")[:5]
FINGERPRINT = re.compile("入力SHA256先頭12桁=[0-9a-f/]+")


class FiveDryMornings(H.D.Case):
    def test_five_mornings_are_done_and_sent_to_the_dry_sender_only(self):
        self.assertEqual(DAYS, ["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27"])
        work, net = H.Work(self), H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        direct, direct_sender = D.Rig(self), H.B.Sender()
        texts = []
        for day in DAYS:
            result = work.morning(net, "dry", day)
            self.assertEqual(result.code, 0, day)
            self.assertEqual((result.kv["run_outcome"], result.kv["key"], result.kv["delivery"], result.kv["send_status"]),
                             ("DONE", day + "-morning", "SENT", "SENT"), day)
            self.assertEqual(result.kv["consumed"], day)
            self.assertEqual(len(result.kv["history_digest"]), 12)
            for key in ("seconds.load_inputs", "seconds.morning_job", "seconds.outbox_load", "outbox_files",
                        "provenance.fetch_count", "provenance.market_through", "provenance.pinned_by",
                        "provenance.market_sha256", "provenance.ledger_commit", "provenance.calendar_sha256"):
                self.assertIn(key, result.kv, key)
            self.assertEqual(result.kv["provenance.market_through"], day)
            self.assertEqual(result.kv["provenance.pinned_by"], "this")
            self.assertEqual(result.kv["provenance.fetch_count"], "4")
            self.assertEqual(result.kv["outbox_files"], str(1 + 2 * (len(texts) + 1)))      # the marker, then claim and result
            block = result.block()
            self.assertIsNotNone(block)
            self.assertIn("対象D=" + day, block)
            texts.append(block)
            # the same day directly over the research fixture
            direct.sync_ledger(day)
            now = D.jst_morning(day)
            series, _fg = load_research_fixture(D.DATA_DIR, through=day)
            reference = D.plain_run(direct.clone, direct_sender, now, series, I.build_sessions(now, day), D.ledger_rows(direct.ledger))
            self.assertEqual((reference.run_outcome, reference.kind, reference.delivery), ("DONE", "morning", "SENT"))
            self.assertEqual(FINGERPRINT.sub("", block), FINGERPRINT.sub("", direct_sender.texts[-1]), day)
            self.assertNotEqual(block, direct_sender.texts[-1])
        self.assertEqual(net.posts(), [])
        self.assertEqual([r["kind"] for r in net.requests], ["chart"] * (4 * 5))
        self.assertEqual(len(set(texts)), 5)
        # the dry history is the same bytes as the direct run's history (each day applied once)
        self.assertEqual(work.remote.blob("v2-dry-state", "history.json"), direct.remote.blob("v2-state", "history.json"))
        events = json.loads(work.remote.blob("v2-dry-state", "history.json").decode("utf-8"))["events"]
        self.assertEqual([e["d"] for e in events if e["kind"] == "APPLY"], DAYS)
        log = work.remote.log("v2-dry-market")
        self.assertEqual([c["subject"] for c in log], ["v2 market through " + d for d in DAYS])

    def test_the_same_morning_a_second_time_is_skipped_and_sends_nothing(self):
        work, net = H.Work(self), H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        first = work.morning(net, "dry", DAYS[0])
        self.assertEqual(first.kv["delivery"], "SENT")
        charts, heads = len(net.charts()), work.heads()
        second = work.morning(net, "dry", DAYS[0], hhmm="08:40")
        self.assertEqual(second.code, 0)
        self.assertEqual((second.kv["run_outcome"], second.kv["delivery"], second.kv["existing_status"]), ("DONE", "SKIPPED_CLAIMED", "SENT"))
        self.assertEqual(second.kv["send_status"], "None")
        self.assertIsNone(second.block())                     # nothing was "sent": no text block
        self.assertEqual(len(net.charts()), charts)           # the pin reaches the target day: no fetch
        self.assertEqual(second.kv["provenance.pinned_by"], "existing")
        self.assertEqual(second.kv["provenance.fetch_count"], "0")
        self.assertEqual(work.heads(), heads)

    def test_the_morning_with_no_new_session_is_skipped_too(self):
        work, net = H.Work(self), H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        self.assertEqual(work.morning(net, "dry", "2026-07-24").code, 0)
        # Saturday morning's target is Friday; the Monday morning (Japan) has the same target day
        monday = work.cmd(net, "morning", "dry", "2026-07-26", "07:40")
        self.assertEqual(monday.code, 0)
        self.assertEqual(monday.kv["key"], "2026-07-24-morning")
        self.assertEqual(monday.kv["delivery"], "SKIPPED_CLAIMED")

    def test_a_run_less_than_sixty_minutes_after_the_close_has_no_complete_target_day_yet(self):
        work, net = H.Work(self), H.Net(DAYS[0])
        self.assertEqual(work.init(net, "dry").code, 0)
        work.sync_ledger(H.START, H.START)                     # a ledger with the header only (no observation after now)
        net.upto = DAYS[0]
        # the close of 07-21 is 20:00 UTC; at 20:30 UTC the 60 minutes have not passed: the series stops at 07-20 or earlier
        from datetime import datetime, timezone
        early = work.run(net, ["morning", "--mode", "dry"], datetime(2026, 7, 21, 20, 30, tzinfo=timezone.utc))
        self.assertEqual(early.code, 0)
        self.assertEqual(early.kv["run_outcome"], "STALE")
        self.assertEqual(early.kv["key"], DAYS[0] + "-halt")


if __name__ == "__main__":
    unittest.main()
