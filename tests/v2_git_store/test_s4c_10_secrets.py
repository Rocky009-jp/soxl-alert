"""S4C-17: the mark SECRETMARK_ is in the path of every remote (and the hooks and fake answers of git print it as well).
Over all the scenes below no exception text, argument or repr, no report, no notice text, no outbox file, no commit message
or file on the remote and no file in the mirror or the work directory shows it; the errors of git have fixed words only, and no
exception was chained to an error of this package."""
import re
import unittest

import s4c_helpers as H

GS, G, N, S, D, B = H.GS, H.G, H.N, H.S, H.D, H.B

FIXED = re.compile(r"git_(args_invalid|failed)(:[a-z-]+)?")
CODES = re.compile(r"[a-z_]+")


class Scenes(H.Case):
    def setUp(self):
        super().setUp()
        self.w = H.world([1, 2, 3])
        self.remotes, self.clones, self.errors = [], [], []

    def track(self, remote, *clones):
        self.remotes.append(remote)
        self.clones.extend(clones)

    def attempt(self, call):
        """Run a call that may raise an error of this package; keep what it shows."""
        raised = None
        try:
            value = call()
        except H.CoreError as e:
            raised, value = e, None
        self.see(value)
        if raised is not None:
            self.errors.append(raised)
            self.see(raised)
        return value, raised

    def test_the_mark_never_leaves_in_any_scene(self):
        w = self.w
        # a normal morning, a second clone, a resend
        remote, clone = H.start(self, w)
        other = H.Clone(self, remote)
        self.track(remote, clone, other)
        self.see(H.job(clone, w, 3, self.sender), H.job(other, w, 3, self.sender),
                 N.resend(other.outbox, self.sender, D[3], "morning", "r1", H.now_at(3, 22)),
                 N.outbox_status(other.outbox, D[3]), self.sender.texts)
        # the remote goes away at every network step; the commands print the mark
        for k in range(1, 9):
            r = H.Remote(self)
            seed = H.Clone(self, r)
            seed.hist.initialize(S.genesis_pub(w))
            seed.outbox.initialize()
            c = H.Clone(self, r, git_cls=H.Scripted)
            n = []

            def before(git, args, r=r, n=n, k=k):
                n.append(1)
                if len(n) == k:
                    H.os.rename(r.path, r.path + "_moved")
            c.git.hooks["fetch"] = c.git.hooks["push"] = before
            sender = B.Sender()
            self.see(H.job(c, w, 3, sender), sender.texts)
            self.track(r, seed, c)
            if H.os.path.exists(r.path + "_moved"):
                H.os.rename(r.path + "_moved", r.path)
        # refusals by a rule: the hook names the mark in what the client prints
        for ref in (H.STATE, H.OUTBOX):
            r, c = H.start(self, w)
            r.hook("pre-receive", 'while read old new ref; do [ "$ref" = refs/heads/%s ] && { echo "%s no" >&2; exit 1; }; done; exit 0'
                   % (ref, H.MARK))
            sender = B.Sender()
            self.see(H.job(c, w, 3, sender), sender.texts)
            self.attempt(lambda: c.hist.initialize(S.genesis_pub(w)))
            self.attempt(lambda: c.outbox.initialize())
            self.track(r, c)
        # pushes that are lost, late or delivered
        r, seed = H.start(self, w)
        for nth, deliver in ((1, True), (1, False), (2, True), (2, False)):
            c = H.Clone(self, r, git_cls=H.Lost, nth=nth, deliver=deliver)
            self.see(H.job(c, w, 3, B.Sender()))
            self.track(r, c)
        r.hook("post-receive", "echo %s >&2; sleep 3" % H.MARK)
        c = H.Clone(self, r, timeout=1)
        w4 = H.world([1, 2, 3, 4])
        self.see(H.job(c, w4, 4, B.Sender(TimeoutError("late"))))
        self.track(r, c)
        # the lower layer, on its own
        r = H.Remote(self)
        c = H.Clone(self, r)
        self.track(r, c)
        git = c.git
        with H.Gone(r):
            for call in (lambda: git.fetch("v2-state"), lambda: c.hist.read(), lambda: c.outbox.initialize(),
                         lambda: c.outbox.resend_ids(D[3], "morning"), lambda: c.hist.initialize(S.genesis_pub(w)),
                         lambda: N.outbox_status(c.outbox, D[3])):
                self.attempt(call)
            self.see(c.outbox.status(D[3], "morning"))
        for call in (lambda: git.tree("a" * 40), lambda: git.blob_of("b" * 40), lambda: git.blob("c" * 40, "history.json"),
                     lambda: git.commit_with("d" * 40, "history.json", b"x", "m", H.WHEN),
                     lambda: git.run(["definitely-not-a-git-command"]).returncode):
            self.attempt(call)
        self.see(git.push("e" * 40, "v2-state"))
        # the checks
        self.assertNoMark()
        for err in self.errors:
            self.assertIsNone(err.__context__, repr(err))
            self.assertIsNone(err.__cause__, repr(err))
            if isinstance(err, GS.GitError):
                self.assertRegex(err.args[0], FIXED)
            self.assertRegex(err.code, CODES)
        self.assertGreater(len(self.errors), 8)
        self.assertTrue(any(isinstance(e, GS.GitError) for e in self.errors))
        for remote_ in self.remotes:                     # what the code under test wrote on a remote
            if not H.os.path.exists(remote_.path):
                continue
            for ref in remote_.refs():
                out = H.tgit(remote_.path, "log", "--format=%H%n%an%n%ae%n%cn%n%ce%n%B", ref).stdout.decode("utf-8")
                self.assertNotIn(H.MARK, out)
                name = ref[len("refs/heads/"):]
                for fname, data in remote_.files(name).items():
                    self.assertNotIn(H.MARK, fname)
                    self.assertNotIn(H.MARK, data.decode("utf-8", "replace"))
        for clone_ in self.clones:                        # the mirrors, and nothing in the work directory but git's own
            for name in H.os.listdir(clone_.parent):
                path = H.os.path.join(clone_.parent, name)
                for fname in H.os.listdir(path):
                    self.assertNotIn(H.MARK, B.bread(path, fname).decode("utf-8", "replace"))
            self.assertEqual([n for n in H.os.listdir(clone_.dir) if n != ".git"], [])


if __name__ == "__main__":
    unittest.main()
