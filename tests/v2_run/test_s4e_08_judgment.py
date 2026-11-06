"""S4E-10 and S4E-12: the fallback key of an ERROR notice checks the judgment of its date (S4-B review P-01, the one condition of
job.py), a HALT or ERROR resend is refused at the entry when the MORNING of the same day exists (P-02), a resend of a morning that
is UNKNOWN is sent, the same id is never sent twice, a claim that cannot be made sends nothing, and status reads only."""
import tempfile
import unittest
from datetime import datetime, timezone

import s4e_helpers as H

R, N = H.R, H.N
DAY = "2026-07-21"
LATE = datetime(2029, 1, 2, 6, 0, tzinfo=timezone.utc)


def live(case):
    work, net = H.Work(case), H.Net(DAY)
    assert work.init(net, "live").code == 0
    return work, net


def resend(work, net, kind, rid, day=DAY, mode="live", hhmm="09:00"):
    return work.cmd(net, "resend", mode, day, hhmm, ["--date", day, "--kind", kind, "--request-id", rid], env={R.SECRET_NAME: H.WEBHOOK})


def status(work, net, day=DAY, mode="live"):
    return work.cmd(net, "status", mode, day, "09:05", ["--date", day])


def keys(result):
    return {k: v.split(" ")[0] for k, v in result.pairs if k.startswith("20")}


class FallbackKey(H.D.Case):
    def plant_morning(self, work, state):
        parent = tempfile.mkdtemp(prefix="v2s4e_mirror_")
        self.addCleanup(__import__("shutil").rmtree, parent, True)
        outbox = H.GS.GitOutbox(H.GS.Git(work.dir), "v2-outbox", parent, H.C.clock)
        claim = outbox.claim(N.Notice(N.MORNING, "2029-01-02", "earlier morning text", "DONE", None), LATE)
        outbox.record("2029-01-02", N.MORNING, claim, state, LATE)

    def test_the_error_of_a_date_with_a_judgment_is_not_sent(self):
        for state in ("SENT", "UNKNOWN", "NOT_SENT"):
            work, net = live(self)
            self.plant_morning(work, state)
            result = work.run(net, ["morning", "--mode", "live"], LATE, env={R.SECRET_NAME: H.WEBHOOK})
            self.assertEqual(result.kv["key"], "2029-01-02-error", state)
            self.assertEqual(result.kv["delivery"], "SKIPPED_JUDGMENT_EXISTS", state)
            self.assertEqual(result.kv["existing_status"], state, state)
            self.assertEqual(result.kv["send_status"], "None")
            self.assertEqual(net.requests, [], state)                      # nothing was fetched and nothing was sent
            self.assertEqual(result.code, 1, state)                        # load_inputs raised: still a failure for the run
            self.assertEqual(result.kv["inputs_raised"], "input_calendar_ended（calendar）")
            self.assertNotIn("2029-01-02-error", "".join(work.remote.names("v2-outbox")))

    def test_without_a_judgment_of_that_date_the_error_is_sent_once(self):
        work, net = live(self)
        result = work.run(net, ["morning", "--mode", "live"], LATE, env={R.SECRET_NAME: H.WEBHOOK})
        self.assertEqual((result.kv["key"], result.kv["delivery"]), ("2029-01-02-error", "SENT"))
        self.assertEqual(len(net.posts()), 1)
        self.assertEqual(result.code, 1)

    def test_a_damaged_morning_of_the_date_also_blocks_it(self):
        work, net = live(self)
        work.remote.plant("v2-outbox", {"v2-outbox-init": b"v2-outbox\n", "2029-01-02-morning.result.json": b"{}"})
        result = work.run(net, ["morning", "--mode", "live"], LATE, env={R.SECRET_NAME: H.WEBHOOK})
        self.assertEqual(result.kv["delivery"], "SKIPPED_JUDGMENT_EXISTS")
        self.assertEqual(result.kv["existing_status"], "DAMAGED")
        self.assertEqual(net.requests, [])


class UnreadableOutbox(H.D.Case):
    """E-0 review N-01: a SKIPPED_* answer over an outbox that cannot be read (existing_status DAMAGED) sent nothing, so the run
    ends with 1; a SKIPPED_* over a judgment that really exists (SENT) stays 0."""

    def test_a_live_morning_after_the_outbox_ref_was_deleted_sends_nothing_and_exits_1(self):
        work, net = live(self)
        self.assertEqual(work.morning(net, "live", DAY).code, 0)
        self.assertEqual(work.morning(net, "live", "2026-07-22").code, 0)
        posts = len(net.posts())
        H.tgit(work.remote.path, "update-ref", "-d", "refs/heads/v2-outbox")
        self.assertIsNone(work.remote.sha("v2-outbox"))
        result = work.morning(net, "live", "2026-07-23")
        self.assertEqual(result.kv["run_outcome"], "DONE")                     # the history is used up, as before
        self.assertEqual((result.kv["delivery"], result.kv["existing_status"]), ("SKIPPED_CLAIMED", "DAMAGED"))
        self.assertEqual(len(net.posts()), posts)                               # nothing was sent
        self.assertEqual(result.code, 1)
        self.assertIn("- exit_code: 1", result.text)

    def test_a_morning_before_init_is_a_failure_too(self):
        work, net = H.Work(self), H.Net(DAY)
        result = work.morning(net, "live", DAY)
        self.assertEqual((result.kv["delivery"], result.kv["existing_status"]), ("SKIPPED_JUDGMENT_EXISTS", "DAMAGED"))
        self.assertEqual((net.posts(), result.code), ([], 1))

    def test_a_judgment_less_notice_over_a_sent_judgment_is_skipped_and_the_exit_stays_0(self):
        work, net = live(self)
        first = work.morning(net, "live", DAY)
        self.assertEqual((first.kv["delivery"], first.code), ("SENT", 0))
        posts = len(net.posts())
        work.put_ledger("not,a,ledger\n")                                       # the second morning of the same D stops on the ledger
        second = work.morning(net, "live", DAY, hhmm="08:40", sync=False)
        self.assertEqual(second.kv["run_outcome"], "STOPPED")
        self.assertTrue(second.kv["key"].endswith("-halt"))
        self.assertEqual((second.kv["delivery"], second.kv["existing_status"]), ("SKIPPED_JUDGMENT_EXISTS", "SENT"))
        self.assertEqual(len(net.posts()), posts)
        self.assertEqual(second.code, 0)


class Resend(H.D.Case):
    def unknown_morning(self):
        work, net = live(self)
        net.discord = ["500"]
        first = work.morning(net, "live", DAY)
        self.assertEqual((first.kv["delivery"], first.code), ("UNKNOWN", 1))
        return work, net

    def test_a_morning_that_is_unknown_is_resent_and_status_shows_both(self):
        work, net = self.unknown_morning()
        result = resend(work, net, "morning", "r1")
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["delivery"], result.kv["send_status"], result.kv["original_status"]), ("SENT", "SENT", "UNKNOWN"))
        self.assertEqual(len(net.posts()), 2)
        shown = keys(status(work, net))
        self.assertEqual(shown[DAY + "-morning"], "UNKNOWN")
        self.assertEqual(shown[DAY + "-morning/r1"], "SENT")
        self.assertEqual(shown[DAY + "-halt"], "NONE")
        self.assertEqual(shown[DAY + "-error"], "NONE")
        self.assertEqual(H.leaks(result.text), [])

    def test_halt_and_error_resends_are_refused_when_the_morning_exists_in_any_state(self):
        for kind in ("halt", "error"):
            for setup in ("unknown", "sent"):
                work, net = live(self)
                net.discord = ["500"] if setup == "unknown" else []
                work.morning(net, "live", DAY)
                posts = len(net.posts())
                heads = work.heads()
                result = resend(work, net, kind, "r9")
                self.assertEqual(result.code, 1, (kind, setup))
                self.assertEqual(result.kv["delivery"], R.REFUSED_JUDGMENT_EXISTS, (kind, setup))
                self.assertEqual(len(net.posts()), posts, (kind, setup))
                self.assertEqual(work.heads(), heads, (kind, setup))

    def test_a_halt_resend_goes_through_when_there_is_no_morning_of_the_day(self):
        work, net = live(self)
        net.override["SPY"] = OSError("network")
        net.discord = ["500"]
        first = work.morning(net, "live", DAY)
        self.assertEqual((first.kv["key"], first.kv["delivery"]), (DAY + "-halt", "UNKNOWN"))
        self.assertEqual(keys(status(work, net))[DAY + "-morning"], "NONE")
        result = resend(work, net, "halt", "r1")
        self.assertEqual(result.code, 0)
        self.assertEqual((result.kv["delivery"], result.kv["original_status"]), ("SENT", "UNKNOWN"))
        self.assertEqual(len(net.posts()), 2)
        self.assertIn("判定なし", net.posts()[-1]["content"])

    def test_the_same_id_is_never_sent_twice_and_a_sent_original_is_refused(self):
        work, net = self.unknown_morning()
        self.assertEqual(resend(work, net, "morning", "r1").code, 0)
        posts = len(net.posts())
        again = resend(work, net, "morning", "r1")
        self.assertEqual(again.code, 1)
        self.assertEqual(again.kv["delivery"], "REFUSED_ALREADY_SENT")           # a resend of the key is SENT: nothing more is sent
        self.assertEqual(len(net.posts()), posts)
        work2, net2 = live(self)
        work2.morning(net2, "live", DAY)
        sent = resend(work2, net2, "morning", "r1")
        self.assertEqual((sent.code, sent.kv["delivery"]), (1, "REFUSED_ALREADY_SENT"))
        self.assertEqual(len(net2.posts()), 1)

    def test_an_unsent_resend_id_that_was_used_is_skipped(self):
        work, net = self.unknown_morning()
        net.discord = ["500"]
        failed = resend(work, net, "morning", "r1")
        self.assertEqual((failed.code, failed.kv["delivery"]), (1, "UNKNOWN"))
        posts = len(net.posts())
        again = resend(work, net, "morning", "r1")
        self.assertEqual((again.code, again.kv["delivery"]), (1, "SKIPPED_CLAIMED"))
        self.assertEqual(len(net.posts()), posts)
        fresh = resend(work, net, "morning", "r2")
        self.assertEqual((fresh.code, fresh.kv["delivery"]), (0, "SENT"))

    def test_a_resend_of_a_day_with_no_original_is_refused(self):
        work, net = live(self)
        result = resend(work, net, "morning", "r1", day="2026-07-22")
        self.assertEqual((result.code, result.kv["delivery"]), (1, "REFUSED_NO_ORIGINAL"))
        self.assertEqual(net.posts(), [])


class ClaimFailed(H.D.Case):
    def reject_outbox(self, work):
        work.remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/v2-outbox ] && exit 1; done; exit 0')

    def test_a_resend_whose_claim_is_refused_sends_nothing_and_exits_1(self):
        work, net = live(self)
        net.discord = ["500"]
        work.morning(net, "live", DAY)
        posts = len(net.posts())
        self.reject_outbox(work)
        result = resend(work, net, "morning", "r1")
        self.assertEqual(result.code, 1)
        self.assertEqual(result.kv["delivery"], "CLAIM_FAILED")
        self.assertEqual(len(net.posts()), posts)
        self.assertEqual(H.leaks(result.text), [])

    def test_a_morning_whose_claim_is_refused_sends_nothing_and_exits_1(self):
        work, net = live(self)
        self.reject_outbox(work)
        result = work.morning(net, "live", DAY)
        self.assertEqual((result.code, result.kv["delivery"], result.kv["send_status"]), (1, "CLAIM_FAILED", "None"))
        self.assertEqual(net.posts(), [])


class Status(H.D.Case):
    def test_status_changes_nothing_and_lists_the_keys_of_the_date(self):
        work, net = live(self)
        work.morning(net, "live", DAY)
        heads = work.heads()
        result = status(work, net)
        self.assertEqual(result.code, 0)
        self.assertEqual(work.heads(), heads)
        self.assertEqual(keys(result), {DAY + "-morning": "SENT", DAY + "-halt": "NONE", DAY + "-error": "NONE"})
        self.assertEqual(len(net.posts()), 1)
        self.assertEqual(len(net.charts()), 4)               # status fetched nothing more
        other = status(work, net, day="2026-07-22")
        self.assertEqual(set(keys(other).values()), {"NONE"})
        self.assertEqual(work.heads(), heads)

    def test_status_of_a_dry_run_reads_the_dry_outbox_only(self):
        work, net = H.Work(self), H.Net(DAY)
        self.assertEqual(work.init(net, "dry").code, 0)
        work.morning(net, "dry", DAY)
        self.assertEqual(keys(status(work, net, mode="dry"))[DAY + "-morning"], "SENT")
        self.assertEqual(work.v2_heads("v2-outbox"), {"v2-outbox": None})


if __name__ == "__main__":
    unittest.main()
