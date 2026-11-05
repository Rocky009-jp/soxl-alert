"""S4C-02: every wrong argument is a GitError (git_args_invalid) before git is started, and its text shows no path. Git is
made unable to start (subprocess.run raises) while each wrong call is made, so a started process fails the test."""
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

import s4c_helpers as H

GS, G = H.GS, H.G

NOT_STR = (None, 3, 3.5, b"/tmp", ["/tmp"], True)


class Args(H.Case):
    def setUp(self):
        super().setUp()
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote)
        self.dir = self.clone.dir
        self.link = os.path.join(self.clone.parent, "link")
        try:
            os.symlink(self.dir, self.link)
        except (OSError, NotImplementedError, AttributeError):
            self.link = None
        self.plain_file = os.path.join(self.clone.parent, "a_file")
        H.B.bwrite(self.clone.parent, "a_file", b"x")

    def refuse(self, call, field=None):
        before = sorted(os.listdir(self.clone.parent))
        with mock.patch.object(G.subprocess, "run", side_effect=AssertionError("git was started")) as run:
            with self.assertRaises(GS.GitError) as cm:
                call()
        self.assertEqual(run.call_count, 0)
        err = cm.exception
        self.assertEqual(err.code, "git_args_invalid")
        if field is not None:
            self.assertEqual(err.field, field)
        self.assertEqual(sorted(os.listdir(self.clone.parent)), before)          # no mirror directory was made
        for t in H.flatten(err) + [repr(err), str(err)]:
            self.assertNotIn(H.MARK, t)
            self.assertNotIn(self.dir, t)
        return err

    def test_the_work_directory_of_git(self):
        for bad in NOT_STR + ("", "relative/dir", "dir", os.path.join(self.dir, "nope"), self.plain_file, "/tmp\0x"):
            self.refuse(lambda b=bad: GS.Git(b), "workdir")

    def test_the_remote_and_the_timeout(self):
        for bad in (None, 3, "", "-x", "a b", "a/b", "a\nb", b"origin", "x" * 65):
            self.refuse(lambda b=bad: GS.Git(self.dir, remote=b), "remote")
        for bad in (0, -1, 1.5, True, "5", None, 2.0):
            self.refuse(lambda b=bad: GS.Git(self.dir, timeout=b), "timeout")

    def test_the_ref_of_every_call(self):
        git = self.clone.git
        bad_refs = (None, 3, b"state", "", "UP", "-a", "a" * 41, "a_b", "a/b", "a b", "a\n", "é", "a.b", "refs/heads/a")
        for bad in bad_refs:
            self.refuse(lambda b=bad: git.fetch(b), "ref")
            self.refuse(lambda b=bad: git.push(H.SHA0.replace("0", "a"), b), "ref")
            self.refuse(lambda b=bad: GS.GitHistoryStore(git, b, H.clock), "ref")
            self.refuse(lambda b=bad: GS.GitOutbox(git, b, self.clone.parent, H.clock), "ref")

    def test_the_sha_and_the_commit_arguments(self):
        git = self.clone.git
        for bad in (None, 3, "", "abc", "A" * 40, "g" * 40, "a" * 39, "a" * 41, "a" * 40 + "\n", b"a" * 40):
            self.refuse(lambda b=bad: git.push(b, "ok"), "commit")
            self.refuse(lambda b=bad: git.tree(b), "commit")
            self.refuse(lambda b=bad: git.blob_of(b), "object")
        good = "a" * 40
        for parent in ("x", 3, "A" * 40, b"a" * 40):
            self.refuse(lambda p=parent: git.commit_with(p, "f.json", b"x", "m", H.WHEN), "parent")
        for name in (None, 3, "", ".hidden", "-x", "a/b", "a b", "..", "é", "x" * 201, b"f"):
            self.refuse(lambda n=name: git.commit_with(good, n, b"x", "m", H.WHEN), "file")
        for data in ("x", None, bytearray(b"x")):
            self.refuse(lambda d=data: git.commit_with(good, "f.json", d, "m", H.WHEN), "file")
        for message in ("", None, 3, "a\nb", "é", b"m"):
            self.refuse(lambda m=message: git.commit_with(good, "f.json", b"x", m, H.WHEN), "message")
        for when in (None, 3, "2026-11-05", datetime(2026, 11, 5), datetime(2026, 11, 5, tzinfo=timezone.utc).date(),
                     datetime(1960, 1, 1, tzinfo=timezone.utc)):
            self.refuse(lambda w=when: git.commit_with(good, "f.json", b"x", "m", w), "clock")

    def test_the_parts_of_the_stores(self):
        git = self.clone.git
        for bad in (None, 3, object(), "git", self.dir):
            self.refuse(lambda b=bad: GS.GitHistoryStore(b, H.STATE, H.clock), "git")
            self.refuse(lambda b=bad: GS.GitOutbox(b, H.OUTBOX, self.clone.parent, H.clock), "git")
        for bad in (None, 3, "now", 3.5, [datetime]):
            self.refuse(lambda b=bad: GS.GitHistoryStore(git, H.STATE, b), "clock")
            self.refuse(lambda b=bad: GS.GitOutbox(git, H.OUTBOX, self.clone.parent, b), "clock")

    def test_the_parent_of_the_mirror(self):
        git = self.clone.git
        bad = list(NOT_STR) + ["", "relative", os.path.join(self.clone.parent, "nope"), self.plain_file, "/tmp\0x"]
        if self.link is not None:
            bad.append(self.link)
        for value in bad:
            self.refuse(lambda v=value: GS.GitOutbox(git, H.OUTBOX, v, H.clock), "parent")

    def test_a_good_call_is_not_refused_and_the_reprs_show_nothing(self):
        git = self.clone.git
        self.assertEqual(repr(git), "Git()")
        self.assertEqual(repr(self.clone.hist), "GitHistoryStore()")
        self.assertEqual(repr(self.clone.outbox), "GitOutbox()")
        for obj in (git, self.clone.hist, self.clone.outbox):
            self.assertNotIn(H.MARK, repr(obj))
            self.assertNotIn(self.dir, repr(obj))
        made = [n for n in os.listdir(self.clone.parent) if n.startswith("v2gitoutbox_")]
        self.assertEqual(len(made), 1)                                          # the one mirror of the one outbox

    def test_a_clock_that_does_not_return_a_time_makes_nothing_and_pushes_nothing(self):
        for bad in (lambda: None, lambda: 3, lambda: datetime(2026, 11, 5), lambda: "now"):
            remote = H.Remote(self)
            clone = H.Clone(self, remote, bad, git_cls=H.Spy)
            w = H.world()
            with self.assertRaises(H.S.LocalStoreError) as cm:
                clone.hist.initialize(H.S.genesis_pub(w))
            self.assertEqual(cm.exception.code, "store_io_error")
            self.assertEqual(clone.git.names().count("push"), 0)
            self.assertEqual(remote.refs(), {})
            good = H.Clone(self, remote, H.clock)
            good.outbox.initialize()
            before = remote.refs()
            clone2 = H.Clone(self, remote, bad, git_cls=H.Spy)
            notice = H.N.compose_error_notice(H.D[2], "x_code", "T", d_is_target=True)
            with self.assertRaises(H.N.NotifyError):
                clone2.outbox.claim(notice, H.now_at(2))
            self.assertEqual(clone2.git.names().count("push"), 0)
            self.assertEqual(remote.refs(), before)


if __name__ == "__main__":
    unittest.main()
