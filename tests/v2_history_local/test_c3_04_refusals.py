"""C3-07: how a refusal is told apart (the C-2 review's P-01). history_invalid on a publish or an initialization means
the current file is broken; a hand-made value whose candidate is invalid is store_candidate_invalid. This file may call
the private constructor (through c2_helpers.rehash) to make such a value; the runtime may not (test_c3_09)."""
import unittest

import c3_helpers as H


def streak(b):
    b["records"][0]["state_after"].update(streak=77)


class BrokenCurrent(H.RootCase):
    def test_a_broken_current_file_is_reported_as_it_is_and_not_changed(self):
        c = H.C2.day_case()
        good = c.current
        text = good.decode("utf-8")
        broken = {
            "truncated": good[:-7],
            "a hash changed": text.replace('"event_hash":"', '"event_hash":"0', 1).encode("utf-8"),
            "not utf8": b"\xff\xfe",
            "empty": b"",
        }
        for name, data in broken.items():
            with self.subTest(name=name):
                H.put(self.root, H.HIST, data)
                before = H.state_of(self.root)
                e = self.run_err(self.store().publish, c.pub)
                self.assertEqual(e.code, "history_invalid", name)
                self.assertNotEqual(e.code, "store_candidate_invalid")
                self.assertEqual(H.state_of(self.root), before)
                self.assertEqual(H.listing(self.root), ["history.json"])

    def test_the_broken_current_wins_over_a_bad_candidate(self):
        # the current file is inspected first: a hand-made value on a broken file still says the file is broken
        c = H.C2.day_case()
        bad = H.C2.rehash(c.pub, streak)
        H.put(self.root, H.HIST, c.current[:-7])
        e = self.run_err(self.store().publish, bad)
        self.assertEqual(e.code, "history_invalid")
        self.assertNotEqual(e.code, "store_candidate_invalid")


class BadCandidate(H.RootCase):
    def test_a_hand_made_value_with_an_invalid_candidate_is_not_a_broken_file(self):
        c = H.C2.day_case()
        self.put_current(c)
        before = H.state_of(self.root)
        bad = H.C2.rehash(c.pub, streak)
        # what C-2 itself says about this value: the code of a broken history (the ambiguity of P-01)
        self.assertEqual(H.C2.err(H.U.check_publication, c.current, bad)[0], "history_invalid")
        e = self.run_err(self.store().publish, bad)
        self.assertStore(e, "store_candidate_invalid", "publication", "candidate")
        self.assertIsNone(e.__cause__)
        self.assertEqual(H.state_of(self.root), before)
        self.assertEqual(H.listing(self.root), ["history.json"])

    def test_the_same_for_an_initialization(self):
        g = H.C2.genesis_case()

        def spoil(b):
            b["candidate_history"]["events"][0]["state_after"]["streak"] = 77
        bad = H.C2.rehash(g.pub, spoil)
        self.assertEqual(H.C2.err(H.U.check_publication, None, bad)[0], "history_invalid")
        e = self.run_err(self.store().initialize, bad)
        self.assertStore(e, "store_candidate_invalid", "publication", "candidate")
        self.assertEqual(H.listing(self.root), [])

    def test_the_publication_refusals_of_c2_pass_through(self):
        c = H.C2.day_case()
        self.put_current(c)
        cases = {
            "publication_invalid": H.C2.rehash(c.pub, lambda b: b.update(candidate_digest="1" * 64)),
            "stale": H.C2.rehash(c.pub, lambda b: b["expected"].update(head_hash="2" * 64)),
        }
        e = self.run_err(self.store().publish, cases["publication_invalid"])
        self.assertEqual((e.code, e.rule), ("publication_invalid", "candidate_digest"))
        e = self.run_err(self.store().publish, cases["stale"])
        self.assertEqual((e.code, e.rule), ("publication_stale", "head"))
        self.assertEqual(H.raw(self.root), c.current)

    def test_a_value_whose_form_is_wrong_is_the_values_error(self):
        c = H.C2.day_case()
        self.put_current(c)
        bad = H.C2.rehash(c.pub, lambda b: b.update(candidate_head_seq=-1))
        e = self.run_err(self.store().publish, bad)
        self.assertEqual(e.code, "publication_invalid")
        self.assertEqual(H.raw(self.root), c.current)

    def test_a_good_value_after_a_refusal_still_publishes(self):
        c = H.C2.day_case()
        self.put_current(c)
        store = self.store()
        self.run_err(store.publish, H.C2.rehash(c.pub, streak))
        self.assertEqual(H.listing(self.root), ["history.json"])
        store.publish(c.pub)
        self.assertEqual(H.raw(self.root), H.C2.file_bytes(c.candidate))


if __name__ == "__main__":
    unittest.main()
