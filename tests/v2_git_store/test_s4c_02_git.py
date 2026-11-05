"""S4C-03 (the push: five answers of a real bare repository, the fake answers, three at the same time) and S4C-04 (the
fetch: a ref, no ref, no remote; nothing in the work directory changes) and the way git is started (the argument list, the
settings, the environment)."""
import os
import unittest
from unittest import mock

import s4c_helpers as H

GS, G, N = H.GS, H.G, H.N

REF = "v2-state"
CONCURRENT = "※別の実行が同時に動いていた可能性があります。同じDの判定が別に届いたら、そちらが有効です。"
ROUNDS = 5


def commit_on(git, parent, name="history.json", data=b"x", when=H.WHEN, message="v2 test"):
    return git.commit_with(parent, name, data, message, when)


class Push(H.Case):
    def setUp(self):
        super().setUp()
        self.remote = H.Remote(self)

    def spy(self, **kw):
        return H.Clone(self, self.remote, git_cls=H.Spy, **kw)

    def test_a_a_fast_forward_and_a_new_ref_are_ok_and_the_command_is_exactly_the_push_of_the_design(self):
        clone = self.spy()
        git = clone.git
        first = commit_on(git, None)
        self.assertEqual(git.push(first, REF), "OK")                     # a new ref
        self.assertEqual(self.remote.sha(REF), first)
        second = commit_on(git, first, data=b"y")
        self.assertEqual(git.push(second, REF), "OK")                    # a fast-forward
        self.assertEqual(self.remote.sha(REF), second)
        pushes = [c for c in git.calls if c[0] == "push"]
        self.assertEqual(pushes, [["push", "--porcelain", "origin", "%s:refs/heads/%s" % (first, REF)],
                                  ["push", "--porcelain", "origin", "%s:refs/heads/%s" % (second, REF)]])
        self.assertEqual(self.remote.files(REF), {"history.json": b"y"})

    def test_a_pushing_what_the_remote_already_has_is_ok(self):
        clone = self.spy()
        first = commit_on(clone.git, None)
        self.assertEqual(clone.git.push(first, REF), "OK")
        self.assertEqual(clone.git.push(first, REF), "OK")               # "=" up to date
        self.assertEqual(self.remote.sha(REF), first)

    def test_b_not_a_fast_forward_is_rejected_and_the_remote_does_not_change(self):
        clone = self.spy()
        git = clone.git
        base = commit_on(git, None)
        git.push(base, REF)
        winner = self.remote.plant(REF, {"history.json": b"winner"})
        late = commit_on(git, base, data=b"late")
        self.assertEqual(git.push(late, REF), "REJECTED")
        self.assertEqual(self.remote.sha(REF), winner)
        self.assertEqual(self.remote.files(REF), {"history.json": b"winner"})

    def test_c_creating_a_ref_that_already_exists_is_rejected(self):
        clone = self.spy()
        existing = self.remote.plant(REF, {"history.json": b"there"}, parent=None)
        again = commit_on(clone.git, None, data=b"again")
        self.assertEqual(clone.git.push(again, REF), "REJECTED")
        self.assertEqual(self.remote.sha(REF), existing)

    def test_d_a_pre_receive_hook_refusal_is_rejected_and_the_history_store_reads_it_as_a_rule_not_a_race(self):
        w = H.world()
        remote, clone = H.start(self, w)
        remote.hook("pre-receive", "exit 1")
        git = H.Spy(H.Clone(self, remote).dir)
        base = remote.sha(H.STATE)
        git.fetch(H.STATE)
        commit = commit_on(git, base)
        self.assertEqual(git.push(commit, H.STATE), "REJECTED")          # the remote did not change
        self.assertEqual(remote.sha(H.STATE), base)
        # the store: the head did not move -> store_io_error, not publication_stale
        sender = H.B.Sender()
        report = H.job(clone, w, 3, sender)
        self.assertEqual((report.run_outcome, report.code, report.kind), ("STOPPED", "store_io_error", "halt"))
        self.assertEqual(report.delivery, "CLAIM_FAILED")                # the outbox is refused by the same rule
        self.assertEqual(sender.texts, [])
        remote.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/%s ] && exit 1; done; exit 0' % H.STATE)
        sender = H.B.Sender()
        report = H.job(clone, w, 3, sender)
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery), ("STOPPED", "store_io_error",
                                                                                          "halt", "SENT"))
        self.assertNotIn(CONCURRENT, sender.texts[0])
        self.assertEqual(remote.sha(H.STATE), base)

    def test_e_a_post_receive_that_waits_longer_than_the_time_limit_is_uncertain_although_the_ref_moved(self):
        clone = H.Clone(self, self.remote, git_cls=H.Spy, timeout=1)
        git = clone.git
        self.remote.hook("post-receive", "sleep 4")
        commit = commit_on(git, None)
        self.assertEqual(git.push(commit, REF), "UNCERTAIN")
        self.assertEqual(self.remote.sha(REF), commit)                   # it did arrive

    def test_f_fake_answers_of_git(self):
        sha = "a" * 40
        target = "%s:refs/heads/%s" % (sha, REF)

        def verdict(returncode, out, timed_out=False):
            def rule(args):
                if args[0] != "push":
                    return None
                return H.Scripted.TIMEOUT if timed_out else H.proc(returncode, out)
            clone = H.Clone(self, self.remote, git_cls=H.Scripted)
            clone.git.rule = rule
            return clone.git.push(sha, REF)
        line = lambda flag, to=target: ("%s\t%s\t[x]\nDone\n" % (flag, to)).encode()           # noqa: E731
        self.assertEqual(verdict(1, line("*")), "UNCERTAIN")            # an OK flag, but the exit code is not 0
        self.assertEqual(verdict(1, line(" ")), "UNCERTAIN")
        self.assertEqual(verdict(1, line("=")), "UNCERTAIN")
        self.assertEqual(verdict(0, line("*")), "OK")
        self.assertEqual(verdict(0, line(" ")), "OK")
        self.assertEqual(verdict(0, line("=")), "OK")
        self.assertEqual(verdict(1, line("!")), "REJECTED")
        self.assertEqual(verdict(0, b""), "UNCERTAIN")                  # no line for the ref
        self.assertEqual(verdict(1, b""), "UNCERTAIN")
        self.assertEqual(verdict(0, line("*", "%s:refs/heads/other" % sha)), "UNCERTAIN")
        self.assertEqual(verdict(0, line("*", "%s:refs/heads/%s" % ("b" * 40, REF))), "UNCERTAIN")
        self.assertEqual(verdict(0, line("+")), "UNCERTAIN")            # a forced update is never taken as ok
        self.assertEqual(verdict(0, line("-")), "UNCERTAIN")
        self.assertEqual(verdict(0, line("*") + line("!")), "UNCERTAIN")        # two answers for the ref
        self.assertEqual(verdict(128, b"fatal: " + H.MARK.encode()), "UNCERTAIN")
        self.assertEqual(verdict(0, b"", timed_out=True), "UNCERTAIN")

    def test_g_three_pushes_from_the_same_parent_at_the_same_time_one_wins_and_two_are_rejected(self):
        for _ in range(ROUNDS):
            base = self.remote.plant(REF, {"history.json": b"base"}, parent=None)
            self.round(base)

    def round(self, base):
        signal = H.tempfile.mkdtemp(prefix="v2s4c_sig_")
        self.addCleanup(H.shutil.rmtree, signal, True)
        go = os.path.join(signal, "go")
        kids = []
        for i in range(3):
            clone = H.Clone(self, self.remote)
            kids.append(H.Child({"mode": "push", "clone": clone.dir, "parent": clone.parent, "go": go, "i": i,
                                 "ref": REF, "parent_sha": base, "name": "f%d.json" % i}))
        try:
            for kid in kids:
                kid.ready()
            H.S.signal(go)
            results = [kid.result() for kid in kids]
        finally:
            for kid in kids:
                if kid.proc.poll() is None:
                    kid.proc.kill()
                    kid.proc.communicate()
        verdicts = sorted(r["verdict"] for r in results)
        self.assertEqual(verdicts, ["OK", "REJECTED", "REJECTED"])
        winner = [r for r in results if r["verdict"] == "OK"][0]
        self.assertEqual(len(winner["porcelain"]), 1)
        names = self.remote.names(REF)
        self.assertEqual(len([n for n in names if n.startswith("f")]), 1)        # only the winner's file is there
        self.assertEqual(self.remote.log(REF)[-1]["parents"], [base])           # the winner's commit is a child of the base


class Fetch(H.Case):
    def setUp(self):
        super().setUp()
        self.remote = H.Remote(self)
        self.clone = H.Clone(self, self.remote, git_cls=H.Spy)

    def test_a_ref_gives_its_sha_and_none_is_a_missing_ref(self):
        head = self.remote.plant(REF, {"history.json": b"x"}, parent=None)
        self.assertEqual(self.clone.git.fetch(REF), head)
        self.assertIsNone(self.clone.git.fetch("v2-other"))
        self.assertEqual(H.text(H.tgit(self.clone.dir, "rev-parse", "refs/v2remote/" + REF)), head)

    def test_a_remote_that_is_not_there_or_not_a_repository_is_an_error(self):
        self.remote.plant(REF, {"history.json": b"x"}, parent=None)
        with H.Gone(self.remote):
            with self.assertRaises(GS.GitError) as cm:
                self.clone.git.fetch(REF)
        self.assertEqual((cm.exception.code, cm.exception.field), ("git_failed", "fetch"))
        self.assertCleanError(cm.exception)
        empty = os.path.join(self.clone.parent, "not_a_repo")
        os.mkdir(empty)
        H.tgit(self.clone.dir, "remote", "set-url", "origin", empty)
        with self.assertRaises(GS.GitError):
            self.clone.git.fetch(REF)

    def test_a_failed_fetch_is_none_only_when_ls_remote_says_there_is_no_ref(self):
        def case(fetch_rc, ls_rc, ls_out):
            def rule(args):
                if args[0] == "fetch":
                    return H.proc(fetch_rc, b"", b"fatal")
                if args[0] == "ls-remote":
                    return H.proc(ls_rc, ls_out)
                return None
            clone = H.Clone(self, self.remote, git_cls=H.Scripted)
            clone.git.rule = rule
            return clone.git
        self.assertIsNone(case(128, 0, b"").fetch(REF))
        for git in (case(128, 0, b"%s\trefs/heads/%s\n" % (b"a" * 40, REF.encode())), case(128, 128, b""),
                    case(128, 0, b"garbage\n")):
            with self.assertRaises(GS.GitError):
                git.fetch(REF)
        timed_out = H.Clone(self, self.remote, git_cls=H.Scripted)
        timed_out.git.rule = lambda args: H.Scripted.TIMEOUT if args[0] in ("fetch", "ls-remote") else None
        with self.assertRaises(GS.GitError):
            timed_out.git.fetch(REF)
        weird = H.Clone(self, self.remote, git_cls=H.Scripted)
        weird.git.rule = lambda args: H.proc(0, b"not a sha\n") if args[0] == "rev-parse" else (
            H.proc(0) if args[0] == "fetch" else None)
        with self.assertRaises(GS.GitError):
            weird.git.fetch(REF)

    def test_a_fetch_changes_nothing_in_the_work_directory(self):
        self.remote.plant(REF, {"history.json": b"x"}, parent=None)
        H.B.bwrite(self.clone.dir, "untouched.txt", b"mine")
        before = self.clone.state()
        for ref in (REF, "v2-none"):
            self.clone.git.fetch(ref)
        self.assertEqual(self.clone.state(), before)
        self.assertEqual(H.B.bread(self.clone.dir, "untouched.txt"), b"mine")
        self.assertEqual(H.text(H.tgit(self.clone.dir, "for-each-ref", "refs/heads/")), "")

    def test_no_command_of_a_whole_morning_changes_a_branch_the_index_or_the_work_tree(self):
        w = H.world()
        remote = H.Remote(self)
        clone = H.Clone(self, remote, git_cls=H.Spy)
        clone.hist.initialize(H.S.genesis_pub(w))
        clone.outbox.initialize()
        sender = H.B.Sender()
        before = clone.state()
        report = H.job(clone, w, 4, sender)
        self.assertEqual(report.delivery, "SENT")
        self.assertEqual(clone.state(), before)
        used = set(clone.git.names())
        self.assertLessEqual(used, {"fetch", "ls-remote", "rev-parse", "ls-tree", "cat-file", "hash-object", "mktree",
                                    "commit-tree", "push"})
        for forbidden in ("checkout", "reset", "add", "commit", "merge", "rebase", "update-ref", "symbolic-ref",
                          "pull", "clean", "stash", "branch", "switch", "restore", "init", "clone", "config"):
            self.assertNotIn(forbidden, used)
        self.assertGreater(len([c for c in clone.git.calls if c[0] == "push"]), 0)
        for call in clone.git.calls:
            if call[0] == "push":
                self.assertEqual(len(call), 4)
                self.assertEqual(call[:3], ["push", "--porcelain", "origin"])
                self.assertFalse(call[3].startswith("+"))
                for part in call:
                    self.assertNotIn(part, ("--force", "-f", "--force-with-lease", "--mirror", "--delete", "--quiet", "-q"))
            if call[0] == "fetch":
                ref = call[-1].split(":refs/v2remote/")[1]
                self.assertEqual(call[-1], "+refs/heads/%s:refs/v2remote/%s" % (ref, ref))


class Start(H.Case):
    """How git is started: the argument list, the settings, the environment (a fake subprocess.run records them)."""

    def test_the_command_the_settings_and_the_environment(self):
        remote = H.Remote(self)
        clone = H.Clone(self, remote, timeout=7)
        seen = []

        def fake(command, **kw):
            seen.append((command, kw))
            return H.proc(0, b"a" * 40 + b"\n")
        values = {"GIT_DIR": "/elsewhere", "git_work_tree": "/elsewhere", "GIT_INDEX_FILE": "/x", "GIT_SSH_COMMAND": "x",
                  "GIT_CONFIG_COUNT": "1", "PATH": os.environ["PATH"], "KEEP_ME": "yes", "GIT_AUTHOR_NAME": "someone",
                  "GIT_TERMINAL_PROMPT": "1", "LC_ALL": "de_DE.UTF-8", "GIT_CONFIG_NOSYSTEM": "0"}
        with H.with_env(**values), mock.patch.object(G.subprocess, "run", side_effect=fake):
            clone.git.run(["rev-parse", "HEAD"])
            clone.git.run(["hash-object", "-w", "--stdin"], data=b"x", env={"GIT_AUTHOR_DATE": "1 +0000"})
        self.assertEqual(len(seen), 2)
        for command, kw in seen:
            self.assertEqual(command[:5], ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false"])
            self.assertIsInstance(command, list)
            self.assertFalse(kw.get("shell", False))
            self.assertEqual(kw["cwd"], clone.dir)
            self.assertEqual(kw["timeout"], 7)
            self.assertTrue(kw["capture_output"])
            env = kw["env"]
            self.assertNotIn("GIT_DIR", env)
            self.assertNotIn("git_work_tree", env)
            self.assertNotIn("GIT_INDEX_FILE", env)
            self.assertNotIn("GIT_SSH_COMMAND", env)
            self.assertNotIn("GIT_CONFIG_COUNT", env)
            self.assertEqual(env["KEEP_ME"], "yes")
            self.assertEqual(env["PATH"], os.environ["PATH"])
            self.assertEqual((env["GIT_TERMINAL_PROMPT"], env["LC_ALL"], env["GIT_CONFIG_NOSYSTEM"]), ("0", "C", "1"))
            self.assertEqual((env["GIT_AUTHOR_NAME"], env["GIT_AUTHOR_EMAIL"]), ("v2-runner", "runner@invalid"))
            self.assertEqual((env["GIT_COMMITTER_NAME"], env["GIT_COMMITTER_EMAIL"]), ("v2-runner", "runner@invalid"))
        self.assertEqual(seen[0][1]["stdin"], H.subprocess.DEVNULL)
        self.assertNotIn("input", seen[0][1])
        self.assertEqual(seen[1][1]["input"], b"x")
        self.assertEqual(seen[1][1]["env"]["GIT_AUTHOR_DATE"], "1 +0000")

    def test_a_git_variable_of_the_parent_cannot_send_git_to_another_repository(self):
        remote = H.Remote(self)
        other = H.Remote(self)
        other.plant("v2-other", {"x": b"y"}, parent=None)
        head = remote.plant(REF, {"history.json": b"x"}, parent=None)
        clone = H.Clone(self, remote)
        with H.with_env(GIT_DIR=other.path, GIT_WORK_TREE=other.path, GIT_INDEX_FILE=os.path.join(other.path, "idx"),
                        GIT_OBJECT_DIRECTORY=os.path.join(other.path, "objects")):
            self.assertEqual(clone.git.fetch(REF), head)
            self.assertIsNone(clone.git.fetch("v2-other"))
            commit = clone.git.commit_with(head, "history.json", b"z", "v2 test", H.WHEN)
            self.assertEqual(clone.git.push(commit, REF), "OK")
        self.assertEqual(remote.sha(REF), commit)
        self.assertIsNone(other.sha(REF))

    def test_git_that_cannot_be_started_is_a_clean_error_and_a_timeout_is_not_an_error_of_run(self):
        clone = H.Clone(self, H.Remote(self))
        with mock.patch.object(G.subprocess, "run", side_effect=OSError(H.MARK)):
            with self.assertRaises(GS.GitError) as cm:
                clone.git.run(["status"])
            self.assertCleanError(cm.exception)
            with self.assertRaises(GS.GitError) as cm:
                clone.git.fetch(REF)
            self.assertCleanError(cm.exception)
        expired = G.subprocess.TimeoutExpired(["git", H.MARK], 1, output=H.MARK.encode())
        with mock.patch.object(G.subprocess, "run", side_effect=expired):
            self.assertIsNone(clone.git.run(["status"]))
            self.assertEqual(clone.git.push("a" * 40, REF), "UNCERTAIN")
            with self.assertRaises(GS.GitError) as cm:
                clone.git.tree("a" * 40)
            self.assertCleanError(cm.exception)


if __name__ == "__main__":
    unittest.main()
