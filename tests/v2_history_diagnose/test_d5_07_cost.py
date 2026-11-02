"""D5-16 cost measurement on a synthetic one-year-sized history (260 APPLY records, APPLY-centred).

The measured times are printed (stderr) for the result document; they are not a bound. No threshold, no cut-off in the
runtime. The value is for this synthetic history only: a history with many RECOVERY_RESTORE records also has each
restore's chain view checked, so this is not a proof of the worst time for every input.
"""
import sys
import time
import unittest

import d5_helpers as X
from v2_persistence.events import append_event
from v2_persistence.runner import make_genesis, prepare_day

APPLIES = 260


def build_events():
    dates = X.P.weekdays(n=APPLIES + 2)
    sessions = X.P.make_sessions(dates=dates)
    series = X.P.make_series(dates=dates)
    snap = make_genesis(dates[0], sessions)
    ledger = []
    for i, d in enumerate(dates[1:APPLIES + 1], 1):
        ledger.append(X.P.obs("R-" + d, d, 20.0 + (i % 40)))
        snap = append_event(snap, prepare_day(snap, d, series, sessions, ledger).plan.event)
    return snap.events


class Cost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = build_events()

    def timed(self, data):
        start = time.perf_counter()
        d = X.diagnose(data)
        return d, time.perf_counter() - start

    def test_the_synthetic_history_is_as_described(self):
        events = self.events
        self.assertEqual(len(events), APPLIES + 1)
        self.assertEqual(events[0]["kind"], "GENESIS")
        self.assertEqual({e["kind"] for e in events[1:]}, {"APPLY"})

    def test_intact_worst_and_ordinary_damage(self):
        events = self.events
        n = len(events)
        valid, t_valid = self.timed(X.file_of(events))
        self.assertEqual(valid["status"], "VALID")
        self.assertEqual(valid["verified"]["count"], n)

        tail, t_tail = self.timed(X.file_of(X.with_hash(events, n - 1)))
        self.assertEqual(tail["status"], "PREFIX_ONLY")
        self.assertEqual(tail["verified"]["count"], n - 1)

        head_only, t_head = self.timed(X.file_of(events, head_hash=X.ZERO))
        self.assertEqual(head_only["verified"]["count"], n)

        worst, t_worst = self.timed(X.file_of(X.with_hash(events, 1)))
        self.assertEqual(worst["status"], "PREFIX_ONLY")
        self.assertEqual(worst["verified"]["count"], 1, "damage right after the GENESIS: every k from n down to 2 fails")
        self.assertEqual(worst["discarded"]["count"], n - 1)

        genesis_bad, t_genesis = self.timed(X.file_of(X.with_hash(events, 0)))
        self.assertEqual(genesis_bad["status"], "NO_VALID_PREFIX")
        self.assertEqual(genesis_bad["discarded"]["count"], n)

        sys.stderr.write(
            "\nD5-16 (records=%d, bytes=%d): intact %.3fs, last record damaged %.3fs, header only %.3fs, "
            "damage after GENESIS %.3fs, GENESIS damaged %.3fs\n"
            % (n, len(X.file_of(events)), t_valid, t_tail, t_head, t_worst, t_genesis))


if __name__ == "__main__":
    unittest.main()
