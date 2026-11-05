"""S4E-03: init makes the genesis of the history and the outbox of the mode, each only when its ref is missing; the start day must
be a session of the table that has closed. The market pin and the ledger are never written by it."""
import os
import unittest

import s4e_helpers as H

R = H.R
D = H.D


class InitDry(H.D.Case):
    def test_a_closed_session_makes_the_history_and_the_outbox(self):
        work = H.Work(self)
        result = work.init(H.Net(), "dry", start="2026-07-20")
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["state"], result.kv["outbox"]), ("INITIALIZED", "INITIALIZED"))
        history = work.history("v2-dry-state")
        self.assertEqual(history["events"][0]["kind"], "GENESIS")
        self.assertEqual(history["events"][0]["start_after"], "2026-07-20")
        self.assertEqual(history["events"][0]["boundary_session"]["date"], "2026-07-20")
        self.assertTrue(history["events"][0]["boundary_session"]["confirmed"])
        self.assertEqual(len(history["events"]), 1)
        self.assertEqual(work.remote.names("v2-dry-outbox"), ["v2-outbox-init"])
        self.assertEqual(work.remote.blob("v2-dry-outbox", "v2-outbox-init"), b"v2-outbox\n")

    def test_the_boundary_is_the_one_asked_for(self):
        for start in ("2026-07-17", "2026-07-02", "2026-01-02"):
            work = H.Work(self)
            now = H.aware("2026-07-27")
            result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", start], now)
            self.assertEqual(result.code, 0, start)
            self.assertEqual(work.history("v2-dry-state")["events"][0]["start_after"], start)

    def test_init_does_not_make_the_pin_or_the_ledger_and_the_other_mode_is_untouched(self):
        work = H.Work(self)
        net = H.Net()
        self.assertEqual(work.init(net, "dry").code, 0)
        self.assertEqual(sorted(work.heads()), ["v2-dry-outbox", "v2-dry-state"])
        self.assertEqual(net.requests, [])
        work2 = H.Work(self)
        self.assertEqual(work2.init(net, "live").code, 0)
        self.assertEqual(sorted(work2.heads()), ["v2-outbox", "v2-state"])


class NotAccepted(H.D.Case):
    def refused(self, start, now, reason="start_after_not_a_closed_session"):
        work = H.Work(self)
        result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", start], now)
        self.assertEqual(result.code, 1, start)
        self.assertEqual(work.heads(), {}, start)
        if reason:
            self.assertEqual(result.kv.get("refused"), reason, start)
        return result

    def test_a_day_that_has_not_closed_yet(self):
        self.refused("2026-07-21", H.aware("2026-07-20"))                  # the morning of 07-21 (Japan): 07-21 is still ahead
        self.refused("2026-07-20", H.aware("2026-07-19", 12, 0))           # before the close of 07-20 (UTC 20:00)
        work = H.Work(self)
        just = H.aware("2026-07-20").replace(hour=19, minute=59, day=20, month=7, year=2026)
        self.assertEqual(work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2026-07-20"], just).code, 1)
        self.assertEqual(work.heads(), {})

    def test_a_day_that_the_table_does_not_have(self):
        for start in ("2026-07-25", "2026-07-26", "2026-07-03", "2026-05-25", "2025-12-31", "2026-01-01", "2026-12-25"):
            self.refused(start, H.aware("2026-08-10"))

    def test_the_early_close_counts_as_the_close(self):
        work = H.Work(self)
        # 2026-11-27 closes at 13:00 New York (18:00 UTC): refused at 17:59 UTC, accepted at 18:00 UTC
        from datetime import datetime, timezone
        early = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2026-11-27"],
                         datetime(2026, 11, 27, 17, 59, tzinfo=timezone.utc))
        self.assertEqual(early.code, 1)
        self.assertEqual(work.heads(), {})
        late = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2026-11-27"],
                        datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(late.code, 0)

    def test_a_time_past_the_table_is_a_failure_and_writes_nothing(self):
        work = H.Work(self)
        from datetime import datetime, timezone
        result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2028-12-29"],
                          datetime(2029, 1, 3, tzinfo=timezone.utc))
        self.assertEqual(result.code, 1)
        self.assertIn("failed: InputError（input_calendar_ended）", result.text)
        self.assertEqual(work.heads(), {})


class EachOnlyWhenMissing(H.D.Case):
    def make_history_only(self, work):
        work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        # leave only the history: drop the outbox ref of the bare remote
        H.tgit(work.remote.path, "update-ref", "-d", "refs/heads/v2-dry-outbox")

    def test_history_only_then_the_outbox_is_made_and_the_history_is_unchanged(self):
        work = H.Work(self)
        self.make_history_only(work)
        before = work.v2_heads("v2-dry-state", "v2-dry-outbox")
        self.assertIsNotNone(before["v2-dry-state"])
        self.assertIsNone(before["v2-dry-outbox"])
        result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2026-07-17"], H.aware("2026-07-20"))
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["state"], result.kv["outbox"]), ("EXISTS", "INITIALIZED"))
        after = work.v2_heads("v2-dry-state", "v2-dry-outbox")
        self.assertEqual(after["v2-dry-state"], before["v2-dry-state"])
        self.assertIsNotNone(after["v2-dry-outbox"])
        self.assertEqual(work.history("v2-dry-state")["events"][0]["start_after"], H.START)      # the old boundary stays

    def test_outbox_only_then_the_history_is_made(self):
        work = H.Work(self)
        work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        H.tgit(work.remote.path, "update-ref", "-d", "refs/heads/v2-dry-state")
        outbox = work.v2_heads("v2-dry-outbox")
        result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["state"], result.kv["outbox"]), ("INITIALIZED", "EXISTS"))
        self.assertEqual(work.v2_heads("v2-dry-outbox"), outbox)

    def test_both_present_nothing_changes(self):
        work = H.Work(self)
        self.assertEqual(work.init(H.Net(), "dry").code, 0)
        before = work.heads()
        for _ in range(2):
            result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", "2026-07-17"], H.aware("2026-07-20"))
            self.assertEqual(result.code, 0)
            self.assertEqual((result.kv["state"], result.kv["outbox"]), ("EXISTS", "EXISTS"))
            self.assertEqual(work.heads(), before)

    def test_a_refused_outbox_makes_the_run_fail_and_the_rerun_finishes_it(self):
        work = H.Work(self)
        work.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/v2-dry-outbox ] && exit 1; done; exit 0')
        first = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        self.assertEqual(first.code, 1)
        self.assertEqual(first.kv["state"], "INITIALIZED")
        self.assertTrue(first.kv["outbox"].startswith("failed ("))
        self.assertIsNone(work.v2_heads("v2-dry-outbox")["v2-dry-outbox"])
        os.remove(os.path.join(work.remote.path, "hooks", "pre-receive"))
        second = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        self.assertEqual(second.code, 0)
        self.assertEqual((second.kv["state"], second.kv["outbox"]), ("EXISTS", "INITIALIZED"))
        self.assertEqual(H.leaks(first.text), [])

    def test_a_refused_history_does_not_stop_the_outbox_from_being_made_but_the_exit_is_1(self):
        work = H.Work(self)
        work.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/v2-dry-state ] && exit 1; done; exit 0')
        result = work.run(H.Net(), ["init", "--mode", "dry", "--start-after", H.START], H.aware(H.START))
        self.assertEqual(result.code, 1)
        self.assertTrue(result.kv["state"].startswith("failed ("))
        self.assertEqual(result.kv["outbox"], "INITIALIZED")
        self.assertEqual(H.leaks(result.text), [])


class SameBoundaryBothModes(H.D.Case):
    def test_dry_and_live_started_at_the_same_boundary_reach_the_same_state_with_the_same_ledger(self):
        # N-03 (optional): the live run catches up over the days of the ledger and ends where the dry run was
        work = H.Work(self)
        net = H.Net(H.D.table_days("2026-07-21", "2026-08-03")[0])
        days = H.D.table_days("2026-07-21", "2026-08-03")
        self.assertEqual(work.init(net, "dry").code, 0)
        self.assertEqual(work.init(net, "live").code, 0)
        for day in days[:6]:
            self.assertEqual(work.morning(net, "dry", day).code, 0, day)
        self.assertEqual(work.morning(net, "live", days[5]).code, 0)
        dry, live = work.history("v2-dry-state"), work.history("v2-state")
        self.assertEqual(dry["current_state"], live["current_state"])
        self.assertEqual([e["d"] for e in dry["events"] if e["kind"] == "APPLY"],
                         [e["d"] for e in live["events"] if e["kind"] == "APPLY"])
        self.assertEqual(len(live["events"]), 7)             # the genesis and the six days, in one catch-up morning


if __name__ == "__main__":
    unittest.main()
