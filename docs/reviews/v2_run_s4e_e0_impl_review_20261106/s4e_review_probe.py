"""Review probes Z1-Z8 of S4-E E-0 (review only, not a test of the repository). usage: REPO=<clone> python -B -m unittest s4e_review_probe -v"""
import os, sys, unittest
ROOT = os.environ["REPO"]
sys.path.insert(0, os.path.join(ROOT, "tests", "v2_run"))
import s4e_helpers as H
D = H.D


class Probes(H.D.Case):
    def test_z1_morning_of_the_boundary_day_right_after_init(self):
        """init at 07:00 JST with the last closed session, then the 07:40 run of the same morning."""
        work, net = H.Work(self), H.Net("2026-07-20")
        r0 = work.init(net, "dry")                       # start 2026-07-20, at 07:00 of 07-21 JST
        print("\nZ1 init", r0.code, r0.kv.get("state"), r0.kv.get("outbox"))
        work.put_ledger(D.ledger_text([], ""))           # header only (E-2: the ledger starts the session after)
        r1 = work.cmd(net, "morning", "dry", "2026-07-20", "07:40")
        print("Z1 morning", r1.code, {k: r1.kv.get(k) for k in ("run_outcome", "key", "delivery", "code", "consumed", "inputs_failure")})
        print("Z1 block", (r1.block() or "")[:300])
        r2 = work.morning(net, "dry", "2026-07-21")
        print("Z1 next", r2.code, {k: r2.kv.get(k) for k in ("run_outcome", "key", "delivery", "code", "consumed")})

    def test_z2_header_only_ledger_first_morning(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        work.init(net, "dry")
        work.put_ledger(D.ledger_text([], ""))
        r = work.cmd(net, "morning", "dry", "2026-07-21", "07:40")
        print("\nZ2", r.code, {k: r.kv.get(k) for k in ("run_outcome", "key", "delivery", "code", "consumed", "inputs_failure")})
        print("Z2 block", (r.block() or "")[:400])

    def test_z3_no_ledger_ref_first_morning(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        work.init(net, "dry")
        r = work.cmd(net, "morning", "dry", "2026-07-21", "07:40")
        print("\nZ3", r.code, {k: r.kv.get(k) for k in ("run_outcome", "key", "delivery", "code", "consumed", "inputs_failure")})

    def test_z4_morning_without_init(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        work.sync_ledger("2026-07-20", "2026-07-21")
        r = work.cmd(net, "morning", "dry", "2026-07-21", "07:40")
        print("\nZ4", r.code, r.text[-700:])

    def test_z5_check_source_before_any_pin(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        work.init(net, "dry")
        r = work.cmd(net, "check-source", "dry", "2026-07-21", "07:30")
        print("\nZ5", r.code, r.kv.get("pin_through"), r.kv.get("SOXX.rows"), [k for k in r.kv if k.startswith("SOXX.pin")])


if __name__ == "__main__":
    unittest.main()


class Silent(H.D.Case):
    def _live_days(self, work, net, days):
        self.assertEqual(work.init(net, "live").code, 0)
        for day in days:
            r = work.morning(net, "live", day)
            self.assertEqual((r.code, r.kv["delivery"]), (0, "SENT"), day)

    def test_z6_outbox_ref_deleted(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self._live_days(work, net, ["2026-07-21", "2026-07-22"])
        H.tgit(work.remote.path, "update-ref", "-d", "refs/heads/v2-outbox")
        for day in ("2026-07-23", "2026-07-24"):
            before = len(net.posts())
            r = work.morning(net, "live", day)
            print("\nZ6", day, r.code, {k: r.kv.get(k) for k in ("run_outcome", "key", "delivery", "existing_status", "code")},
                  "posts", len(net.posts()) - before)

    def test_z7_remote_unreachable(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self._live_days(work, net, ["2026-07-21"])
        moved = work.remote.path + "_moved"
        work.sync_ledger(H.START, "2026-07-22"); net.upto = "2026-07-22"
        os.rename(work.remote.path, moved)
        before = len(net.posts())
        try:
            r = work.cmd(net, "morning", "live", "2026-07-22", env={H.R.SECRET_NAME: H.WEBHOOK})
        finally:
            os.rename(moved, work.remote.path)
        print("\nZ7", r.code, {k: r.kv.get(k) for k in ("run_outcome", "key", "delivery", "existing_status", "code", "inputs_failure", "failed")},
              "posts", len(net.posts()) - before)

    def test_z8_state_ref_deleted(self):
        work, net = H.Work(self), H.Net("2026-07-21")
        self._live_days(work, net, ["2026-07-21"])
        H.tgit(work.remote.path, "update-ref", "-d", "refs/heads/v2-state")
        before = len(net.posts())
        r = work.morning(net, "live", "2026-07-22")
        print("\nZ8", r.code, {k: r.kv.get(k) for k in ("run_outcome", "key", "delivery", "existing_status", "code")},
              "posts", len(net.posts()) - before)
