"""S4C-05 (initialize, read, the layout), S4C-06 (the same run as the C-3 store), S4C-07 (a save that was beaten) and
S4C-08 (a push whose outcome is not known). Expected values: the C-3 HistoryFileStore over the same inputs, the S4-A
helper's independent chain, and `git` called by the test directly on the bare remote."""
import unittest

import s4c_helpers as H

GS, S, D = H.GS, H.S, H.D

CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"


def c3_root(case, w):
    root = S.make_root()
    case.addCleanup(H.shutil.rmtree, root, True)
    return root, S.real_store(root, w)


class InitializeAndRead(H.Case):
    def setUp(self):
        super().setUp()
        self.w = H.world()
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote)

    def test_a_ref_that_does_not_exist_is_uninitialized(self):
        h = self.clone.hist
        with self.assertRaises(S.LocalStoreError) as cm:
            h.read()
        self.assertEqual(cm.exception.code, "store_uninitialized")
        pub = S.U.publish_genesis(self.w.start_after, self.w.sessions)
        with self.assertRaises(S.LocalStoreError) as cm:
            h.publish(S.U.publish_day(S.expected_history(self.w, 0), D[1], self.w.series, self.w.sessions, self.w.ledger))
        self.assertEqual(cm.exception.code, "store_uninitialized")
        self.assertEqual(h.reconcile(pub).outcome, "NOT_PUBLISHED")                  # a creation that did not happen
        day = S.U.publish_day(S.expected_history(self.w, 0), D[1], self.w.series, self.w.sessions, self.w.ledger)
        self.assertEqual(h.reconcile(day).outcome, "CONFLICT")                         # an append to nothing
        self.assertEqual(self.remote.refs(), {})

    def test_the_genesis_is_the_same_file_as_the_c3_store_writes_and_the_ref_holds_only_it(self):
        pub = S.genesis_pub(self.w)
        result = self.clone.hist.initialize(pub)
        root, c3 = c3_root(self, self.w)
        self.assertEqual(self.remote.blob(H.STATE, "history.json"), S.raw(root))
        self.assertEqual(self.remote.names(H.STATE), ["history.json"])
        history = self.clone.hist.read()
        self.assertEqual(history.digest, c3.read().digest)
        self.assertEqual(history.events, c3.read().events)
        self.assertEqual((result.status, result.committed, result.publication_hash), ("INITIALIZED", True, pub.publication_hash))
        self.assertEqual(result.history.digest, history.digest)
        self.assertEqual(result.persistence_level, "git_remote_ref")
        self.assertEqual(self.remote.refs(), {"refs/heads/" + H.STATE: self.remote.sha(H.STATE)})

    def test_a_second_initialization_is_refused_and_changes_nothing(self):
        self.clone.hist.initialize(S.genesis_pub(self.w))
        head = self.remote.sha(H.STATE)
        other = H.Clone(self, self.remote)
        for store in (self.clone.hist, other.hist):
            with self.assertRaises(S.LocalStoreError) as cm:
                store.initialize(S.genesis_pub(self.w))
            self.assertEqual(cm.exception.code, "already_initialized")
        self.assertEqual(self.remote.sha(H.STATE), head)

    def test_a_creation_that_another_clone_won_in_the_meantime_is_already_initialized(self):
        later = H.Tick()
        later()                                                  # its next time is not ours: not the same commit
        other = H.Clone(self, self.remote, later)
        git = H.Scripted(self.clone.dir)
        store = GS.GitHistoryStore(git, H.STATE, H.clock)
        done = []

        def first(_git, args):
            if not done:
                done.append(1)
                other.hist.initialize(S.genesis_pub(self.w))        # the other clone creates the ref just before our push
        git.hooks["push"] = first
        with self.assertRaises(S.LocalStoreError) as cm:
            store.initialize(S.genesis_pub(self.w))
        self.assertEqual(cm.exception.code, "already_initialized")
        self.assertEqual(self.remote.log(H.STATE)[-1]["parents"], [])               # the other clone's commit is the ref

    def test_a_file_that_is_not_a_regular_file_is_not_the_history(self):
        blob = H.text(H.tgit(self.remote.path, "hash-object", "-w", "--stdin", data=b"history.json"))
        tree = H.text(H.tgit(self.remote.path, "mktree", data=("120000 blob %s\thistory.json\n" % blob).encode("ascii")))
        commit = H.text(H.tgit(self.remote.path, "commit-tree", tree, "-m", "a link"))
        H.tgit(self.remote.path, "update-ref", "refs/heads/" + H.STATE, commit)
        with self.assertRaises(S.LocalStoreError) as cm:
            self.clone.hist.read()
        self.assertEqual(cm.exception.code, "store_layout_unsupported")

    def test_the_publication_checks_before_anything_is_pushed(self):
        h = self.clone.hist
        genesis = S.genesis_pub(self.w)
        h.initialize(genesis)
        head = self.remote.sha(H.STATE)
        day = S.U.publish_day(self.clone.hist.read(), D[1], self.w.series, self.w.sessions, self.w.ledger)
        with self.assertRaises(S.LocalStoreError) as cm:
            h.initialize(day)
        self.assertEqual((cm.exception.code, cm.exception.rule), ("store_operation_unsupported", "not_genesis"))
        with self.assertRaises(S.LocalStoreError) as cm:
            h.publish(genesis)
        self.assertEqual((cm.exception.code, cm.exception.rule), ("store_operation_unsupported", "not_append"))
        for bad in (None, {}, "pub", object(), 3):
            for call in (h.initialize, h.publish, h.reconcile):
                with self.assertRaises(S.LocalStoreError) as cm:
                    call(bad)
                self.assertEqual((cm.exception.code, cm.exception.rule), ("store_publication_invalid", "type"))
        self.assertEqual(self.remote.sha(H.STATE), head)

    def test_a_ref_without_history_json_is_a_layout_we_do_not_know(self):
        self.remote.plant(H.STATE, {"other.txt": b"x"}, parent=None)
        head = self.remote.sha(H.STATE)
        day = S.U.publish_day(S.expected_history(self.w, 0), D[1], self.w.series, self.w.sessions, self.w.ledger)
        for call in (lambda: self.clone.hist.read(), lambda: self.clone.hist.publish(day),
                     lambda: self.clone.hist.reconcile(day)):
            with self.assertRaises(S.LocalStoreError) as cm:
                call()
            self.assertEqual(cm.exception.code, "store_layout_unsupported")
        with self.assertRaises(S.LocalStoreError) as cm:
            self.clone.hist.initialize(S.genesis_pub(self.w))
        self.assertEqual(cm.exception.code, "already_initialized")
        self.assertEqual(self.remote.sha(H.STATE), head)

    def test_a_history_json_that_is_not_a_history_is_reported_as_the_c3_store_reports_it_and_nothing_is_pushed(self):
        day = S.U.publish_day(S.expected_history(self.w, 0), D[1], self.w.series, self.w.sessions, self.w.ledger)
        for data in (b"", b"{}", b"not json", b"\xff\xfe", b"[1, 2]"):
            root = S.make_root()
            self.addCleanup(H.shutil.rmtree, root, True)
            S.put(root, "history.json", data)
            c3 = S.HistoryFileStore(root, writable=True, durability=S.DURABILITY)
            with self.assertRaises(H.CoreError) as expected:
                c3.read()
            with self.assertRaises(H.CoreError) as expected_publish:
                c3.publish(day)
            remote = H.Remote(self)
            clone = H.Clone(self, remote, git_cls=H.Spy)
            head = remote.plant(H.STATE, {"history.json": data}, parent=None)
            for call, want in ((clone.hist.read, expected.exception), (lambda: clone.hist.publish(day),
                                                                     expected_publish.exception)):
                with self.assertRaises(H.CoreError) as cm:
                    call()
                self.assertNotIsInstance(cm.exception, S.LocalStoreError)
                self.assertEqual((cm.exception.code, cm.exception.field), (want.code, want.field))
            self.assertEqual(clone.git.names().count("push"), 0)
            self.assertEqual(remote.sha(H.STATE), head)
            self.assertEqual(clone.hist.reconcile(day).outcome, "CONFLICT")

    def test_a_publication_adds_one_day_and_gives_the_result_of_the_c3_store(self):
        self.clone.hist.initialize(S.genesis_pub(self.w))
        history = self.clone.hist.read()
        pub = S.U.publish_day(history, D[1], self.w.series, self.w.sessions, self.w.ledger)
        result = self.clone.hist.publish(pub)
        root, c3 = c3_root(self, self.w)
        expected = c3.publish(pub)
        self.assertEqual(self.remote.blob(H.STATE, "history.json"), S.raw(root))
        self.assertEqual((result.status, result.committed, result.publication_hash),
                         (expected.status, expected.committed, expected.publication_hash))
        self.assertEqual(result.history.digest, expected.history.digest)
        self.assertEqual(self.clone.hist.read().digest, expected.history.digest)
        self.assertEqual(self.clone.hist.reconcile(pub).outcome, "PUBLISHED")


class SameAsC3(H.Case):
    def both(self, decisions, last, hour=18):
        w = H.world(decisions)
        remote, clone = H.start(self, w)
        root, c3 = c3_root(self, w)
        report_git = H.run(clone, w, last, hour)
        report_c3 = S.run(c3, w, H.now_at(last, hour))
        self.assertEqual(report_git, report_c3)
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.raw(root))
        return w, remote, clone, root, c3, report_git

    def test_a_catch_up_of_several_days_and_the_run_again(self):
        w, remote, clone, root, c3, report = self.both(range(1, 7), 6)
        self.assertEqual((report.outcome, [c.d for c in report.consumed]), ("DONE", [D[i] for i in range(1, 7)]))
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 6))
        again_git, again_c3 = H.run(clone, w, 6), S.run(c3, w, H.now_at(6))
        self.assertEqual(again_git, again_c3)
        self.assertEqual(again_git.consumed, ())
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.raw(root))
        data = H.json.loads(remote.blob(H.STATE, "history.json").decode("utf-8"))
        self.assertEqual([e["d"] for e in data["events"] if e["kind"] == "APPLY"], [D[i] for i in range(1, 7)])

    def test_a_missing_day_is_saved_with_its_gap_the_same_way(self):
        w, remote, clone, root, c3, report = self.both([1, 2, 4], 5)
        self.assertTrue(any(c.gap for c in report.consumed))
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 5))

    def test_the_days_are_saved_one_by_one_in_order_one_commit_each(self):
        w, remote, clone, root, c3, report = self.both(range(1, 5), 4)
        log = remote.log(H.STATE)
        self.assertEqual(len(log), 1 + 4)                                       # the genesis and one per day
        self.assertEqual([c["parents"] for c in log[1:]], [[log[i]["sha"]] for i in range(4)])

    def test_a_stale_morning_and_an_unconfirmed_session_stop_the_same_way(self):
        w = H.world(range(1, 4), unconfirmed=(D[3],))
        remote, clone = H.start(self, w)
        root, c3 = c3_root(self, w)
        a, b = H.run(clone, w, 3), S.run(c3, w, H.now_at(3))
        self.assertEqual((a.outcome, a.code), ("STALE", "run_session_unconfirmed"))
        self.assertEqual(a, b)
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.raw(root))


class Beaten(H.Case):
    """S4C-07: another clone saved first."""

    def other_saves(self, remote, w, last):
        other = H.Clone(self, remote)
        return H.run(other, w, last)

    def test_the_ref_moves_between_the_commit_and_the_push_is_a_beaten_save(self):
        w = H.world()
        remote = H.Remote(self)
        seed = H.Clone(self, remote)
        seed.hist.initialize(S.genesis_pub(w))
        seed.outbox.initialize()
        clone = H.Clone(self, remote, git_cls=H.Scripted)
        fired = []

        def other_first(git, args):
            if not fired:
                fired.append(1)
                self.other_saves(remote, w, 4)
        clone.git.hooks["push"] = other_first
        report = H.run(clone, w, 4)
        self.assertEqual((report.outcome, report.code, report.consumed), ("STOPPED", "publication_stale", ()))
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 4))        # the other clone's save
        self.assertEqual(clone.git.names().count("push"), 1)

    def test_the_ref_moves_before_the_publish_fetch_is_a_beaten_save_without_a_push(self):
        w = H.world()
        remote = H.Remote(self)
        seed = H.Clone(self, remote)
        seed.hist.initialize(S.genesis_pub(w))
        clone = H.Clone(self, remote, git_cls=H.Scripted)
        seen = []

        def other_first(git, args):
            seen.append(1)
            if len(seen) == 2:                                   # the first fetch is read(); the second is publish()
                self.other_saves(remote, w, 4)
        clone.git.hooks["fetch"] = other_first
        report = H.run(clone, w, 4)
        self.assertEqual((report.outcome, report.code), ("STOPPED", "publication_stale"))
        self.assertEqual(clone.git.names().count("push"), 0)
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 4))

    def test_the_morning_job_says_that_another_run_may_have_been_at_work_and_the_judgment_comes_later(self):
        w = H.world()
        remote = H.Remote(self)
        seed = H.Clone(self, remote)
        seed.hist.initialize(S.genesis_pub(w))
        seed.outbox.initialize()
        clone = H.Clone(self, remote, git_cls=H.Scripted)
        fired = []

        def other_first(git, args):
            if not fired:
                fired.append(1)
                self.other_saves(remote, w, 4)
        clone.git.hooks["push"] = other_first
        sender = self.sender
        report = H.job(clone, w, 4, sender)
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery),
                         ("STOPPED", "publication_stale", "halt", "SENT"))
        self.assertEqual(len(sender.texts), 1)
        self.assertIn(CONCURRENT, sender.texts[0])
        self.assertEqual(remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 4))
        # the next run (nothing else running) gives the judgment of the same day
        again = H.job(clone, w, 4, sender)
        self.assertEqual((again.run_outcome, again.kind, again.delivery), ("DONE", "morning", "SENT"))
        self.assertEqual(len(sender.texts), 2)


class Uncertain(H.Case):
    """S4C-08."""

    def setUp(self):
        super().setUp()
        self.w = H.world(range(1, 2))
        self.remote = H.Remote(self)
        self.seed = H.Clone(self, self.remote)
        self.seed.hist.initialize(S.genesis_pub(self.w))

    def clone(self, **kw):
        return H.Clone(self, self.remote, **kw)

    def test_a_it_arrived_a_real_push_that_was_slow(self):
        self.remote.hook("post-receive", "[ -e ./slept ] || { touch ./slept; sleep 4; }")
        clone = self.clone(git_cls=H.Spy, timeout=1)
        report = H.run(clone, self.w, 1)
        self.assertEqual((report.outcome, report.code, [c.d for c in report.consumed]), ("DONE", None, [D[1]]))
        self.assertEqual(self.remote.blob(H.STATE, "history.json"), S.expected_bytes(self.w, 1))
        self.assertEqual(clone.git.names().count("push"), 1)                     # the push was not repeated

    def test_b_it_did_not_arrive(self):
        clone = self.clone(git_cls=H.Lost, deliver=False)
        head = self.remote.sha(H.STATE)
        report = H.run(clone, self.w, 1)
        self.assertEqual((report.outcome, report.code), ("STOPPED", "run_publish_not_published"))
        self.assertEqual(self.remote.sha(H.STATE), head)

    def test_c_it_arrived_and_another_save_followed(self):
        w = H.world(range(1, 3))
        other = self.clone()
        state = {}

        def after():
            state["report"] = H.run(other, w, 2)                 # the next day, saved by another clone
        clone = H.Clone(self, self.remote, git_cls=H.Lost)
        clone.git.after = after
        report = H.run(clone, w, 2)
        self.assertEqual(state["report"].outcome, "DONE")
        self.assertEqual(report.outcome, "DONE")
        self.assertEqual([c.d for c in report.consumed], [D[1]])
        self.assertEqual(self.remote.blob(H.STATE, "history.json"), S.expected_bytes(w, 2))
        data = H.json.loads(self.remote.blob(H.STATE, "history.json").decode("utf-8"))
        self.assertEqual([e["d"] for e in data["events"] if e["kind"] == "APPLY"], [D[1], D[2]])
        # the judgment of this store's reconcile for the first day, asked by a new object that remembers nothing
        pub = S.U.publish_day(S.expected_history(w, 0), D[1], w.series, w.sessions, w.ledger)
        self.assertEqual(self.clone().hist.reconcile(pub).outcome, "PUBLISHED_THEN_EXTENDED")

    def test_d_the_remote_holds_other_content(self):
        w_other = H.world(range(1, 2))
        w_other.ledger[0] = H.P.obs("R1", D[1], 71.0)             # another observation for the same day
        other = self.clone()
        state = {}

        def after():
            state["report"] = H.run(other, w_other, 1)
        clone = H.Clone(self, self.remote, git_cls=H.Lost, deliver=False)
        clone.git.after = after
        report = H.run(clone, self.w, 1)
        self.assertEqual(state["report"].outcome, "DONE")
        self.assertEqual((report.outcome, report.code), ("STOPPED", "run_publish_conflict"))
        self.assertEqual(self.remote.blob(H.STATE, "history.json"), S.expected_bytes(w_other, 1))
        self.assertNotEqual(S.expected_bytes(w_other, 1), S.expected_bytes(self.w, 1))

    def test_the_uncertain_code_and_the_reconcile_do_exactly_what_the_design_says(self):
        clone = self.clone(git_cls=H.Lost, deliver=True)
        pub = S.U.publish_day(clone.hist.read(), D[1], self.w.series, self.w.sessions, self.w.ledger)
        with self.assertRaises(S.LocalStoreError) as cm:
            clone.hist.publish(pub)
        self.assertEqual(cm.exception.code, "store_commit_uncertain")
        before = len(clone.git.calls)
        outcome = clone.hist.reconcile(pub)
        self.assertEqual(outcome.outcome, "PUBLISHED")
        added = [c[0] for c in clone.git.calls[before:]]
        self.assertEqual(added.count("fetch"), 1)
        self.assertNotIn("push", added)
        self.assertNotIn("commit-tree", added)


if __name__ == "__main__":
    unittest.main()
