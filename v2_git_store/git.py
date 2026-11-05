"""The only place that runs git. Every git command is an argument list handed to subprocess.run (no shell); the output of
git (standard output and standard error) can name the remote and its credentials, so it is read here and never leaves:
no exception argument, repr, report, text, file or commit message holds any of it.

The working directory is never changed: a commit is made with hash-object, mktree and commit-tree, the remote is read
into refs/v2remote/<ref> only, and refs/heads/*, HEAD, the index and the work tree are not touched. The remote is changed by
one command only, `git push --porcelain <remote> <sha>:refs/heads/<ref>`: a fast-forward, never forced, never quiet.
No time is read here (a commit gets the time it is given), nothing is retried, nothing sleeps."""
import os
import re
import subprocess

from v2_core.errors import CoreError

OK, REJECTED, UNCERTAIN = "OK", "REJECTED", "UNCERTAIN"
ARGS_INVALID = "git_args_invalid"
FAILED = "git_failed"
REGULAR_MODES = ("100644", "100755")

_REF = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_SHA = re.compile(r"[0-9a-f]{40}")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_REMOTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_FIXED_ENV = {"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "v2-runner",
              "GIT_AUTHOR_EMAIL": "runner@invalid", "GIT_COMMITTER_NAME": "v2-runner",
              "GIT_COMMITTER_EMAIL": "runner@invalid"}


class GitError(CoreError):
    """A git command failed, timed out, or an argument is wrong. The arguments are fixed words only (a code and a field)."""


def check_ref(ref):
    """The name of a ref (refs/heads/<ref>): 1 to 40 of a-z 0-9 -, not starting with -. Returns it, or raises GitError."""
    if type(ref) is not str or _REF.fullmatch(ref) is None:
        raise GitError(ARGS_INVALID, "ref")
    return ref


def check_clock(clock):
    if not callable(clock):
        raise GitError(ARGS_INVALID, "clock")
    return clock


def is_absolute_dir(path):
    """True for an absolute path of an existing directory (the value is never shown in an error)."""
    return type(path) is str and bool(path) and "\0" not in path and os.path.isabs(path) and os.path.isdir(path)


def valid_name(name):
    """A file name of a tree that this package reads or writes: ASCII letters, digits, . _ - (not starting with one of the
    last three), at most 200 characters."""
    return type(name) is str and _NAME.fullmatch(name) is not None


def _sha(text):
    return type(text) is str and _SHA.fullmatch(text) is not None


def _stamp(when):
    """The time of a commit in git's raw form: seconds since the epoch and the offset of the given time zone."""
    offset = when.utcoffset() if callable(getattr(when, "utcoffset", None)) else None
    epoch = when.timestamp() if offset is not None and callable(getattr(when, "timestamp", None)) else None
    if not hasattr(offset, "total_seconds") or type(epoch) is not float or epoch < 0:
        raise GitError(ARGS_INVALID, "clock")
    seconds = int(offset.total_seconds())
    minutes = abs(seconds) // 60
    epoch = int(epoch)
    return "%d %s%02d%02d" % (epoch, "-" if seconds < 0 else "+", minutes // 60, minutes % 60)


def _environment():
    """A copy of the parent's environment without any GIT_ variable, plus the fixed ones."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(_FIXED_ENV)
    return env


def _verdict(proc, commit, ref):
    """OK / REJECTED / UNCERTAIN from the porcelain lines of one push (flag TAB from:to TAB summary)."""
    if proc is None:
        return UNCERTAIN
    out = proc.stdout if isinstance(proc.stdout, (bytes, bytearray)) else b""
    target = "%s:refs/heads/%s" % (commit, ref)
    flags = []
    for line in bytes(out).decode("utf-8", "replace").splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1] == target:
            flags.append(fields[0])
    if len(flags) != 1:
        return UNCERTAIN
    if flags[0] in ("*", " ", "="):
        return OK if proc.returncode == 0 else UNCERTAIN
    if flags[0] == "!":
        return REJECTED
    return UNCERTAIN


class Git(object):
    """workdir: an absolute path of an existing directory that is a git repository whose `remote` is configured.
    remote: the name of that remote. timeout: seconds, a positive int (a push that times out is UNCERTAIN)."""

    def __init__(self, workdir, remote="origin", timeout=120):
        if not is_absolute_dir(workdir):
            raise GitError(ARGS_INVALID, "workdir")
        if type(remote) is not str or _REMOTE.fullmatch(remote) is None:
            raise GitError(ARGS_INVALID, "remote")
        if type(timeout) is not int or timeout <= 0:
            raise GitError(ARGS_INVALID, "timeout")
        self.workdir, self.remote, self.timeout = workdir, remote, timeout

    def __repr__(self):
        return "Git()"

    # --- the one place that starts a process ----------------------------------------------------------------------------
    def run(self, args, data=None, env=None):
        """One git command. Returns the CompletedProcess, or None when it timed out. Raises GitError when git could not
        be started. data: bytes for standard input (otherwise standard input is closed). env: extra variables."""
        command = ["git", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false"] + list(args)
        environment = _environment()
        environment.update(env or {})
        kwargs = {"input": data} if data is not None else {"stdin": subprocess.DEVNULL}
        proc, timed_out, failed = None, False, False
        try:
            proc = subprocess.run(command, cwd=self.workdir, capture_output=True, timeout=self.timeout,
                                  env=environment, **kwargs)
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError:
            failed = True
        if failed:
            raise GitError(FAILED, "start")
        return None if timed_out else proc

    def _must(self, args, data=None, env=None):
        """The standard output of a command that must succeed (a GitError says only that a command failed)."""
        proc = self.run(args, data, env)
        if proc is None or proc.returncode != 0:
            raise GitError(FAILED, "command")
        return proc.stdout

    def _sha_of(self, out):
        text = out.decode("ascii", "replace").strip() if isinstance(out, (bytes, bytearray)) else ""
        if not _sha(text):
            raise GitError(FAILED, "sha")
        return text

    # --- reading ------------------------------------------------------------------------------------------------------------
    def fetch(self, ref):
        """The head SHA of refs/heads/<ref> of the remote, read into refs/v2remote/<ref> (nothing else changes), or None
        when the remote certainly has no such ref. A failed fetch is None only when ls-remote then answers an empty list;
        every other failure is a GitError (a failure is never read as "no ref")."""
        check_ref(ref)
        proc = self.run(["fetch", "--no-tags", "--quiet", self.remote, "+refs/heads/%s:refs/v2remote/%s" % (ref, ref)])
        if proc is not None and proc.returncode == 0:
            return self._sha_of(self._must(["rev-parse", "--verify", "refs/v2remote/%s" % ref]))
        listing = self.run(["ls-remote", "--heads", self.remote, "refs/heads/%s" % ref])
        if listing is not None and listing.returncode == 0 and not listing.stdout.strip():
            return None
        raise GitError(FAILED, "fetch")

    def tree(self, commit):
        """{name: (mode, type, object SHA)} of the top level of a commit's tree."""
        if not _sha(commit):
            raise GitError(ARGS_INVALID, "commit")
        entries = {}
        for item in self._must(["ls-tree", "-z", commit]).split(b"\0"):
            if not item:
                continue
            meta, _tab, name = item.partition(b"\t")
            parts = meta.decode("ascii", "replace").split(" ")
            if _tab != b"\t" or len(parts) != 3:
                raise GitError(FAILED, "ls-tree")
            entries[os.fsdecode(name)] = (parts[0], parts[1], parts[2])
        return entries

    def blob_of(self, sha):
        """The bytes of one blob object."""
        if not _sha(sha):
            raise GitError(ARGS_INVALID, "object")
        return self._must(["cat-file", "blob", sha])

    def blob(self, commit, name):
        """The bytes of the regular file `name` in the top level of a commit, or None when the tree has no such file."""
        entry = self.tree(commit).get(name)
        if entry is None or entry[1] != "blob" or entry[0] not in REGULAR_MODES:
            return None
        return self.blob_of(entry[2])

    # --- making a commit (no ref, index or work tree is touched) ------------------------------------------------------
    def commit_with(self, parent, name, data, message, when, replace=True):
        """A new commit whose tree is the parent's tree with the file `name` set to `data` (the other entries are kept
        as they are). parent: a SHA, or None for a first commit. With replace=False the file must be new: when the
        parent's tree already has that name no commit is made and None is returned. Returns the SHA of the commit."""
        if parent is not None and not _sha(parent):
            raise GitError(ARGS_INVALID, "parent")
        if not valid_name(name) or type(data) is not bytes:
            raise GitError(ARGS_INVALID, "file")
        if type(message) is not str or not message.isascii() or not message.isprintable() or not message:
            raise GitError(ARGS_INVALID, "message")
        stamp = _stamp(when)
        entries = {} if parent is None else self.tree(parent)
        if not replace and name in entries:
            return None
        blob = self._sha_of(self._must(["hash-object", "-w", "--stdin"], data))
        entries[name] = ("100644", "blob", blob)
        listing = b"".join(("%s %s %s\t" % entries[n]).encode("ascii") + os.fsencode(n) + b"\0"
                           for n in sorted(entries, key=os.fsencode))
        tree = self._sha_of(self._must(["mktree", "-z"], listing))
        args = ["commit-tree", tree, "-m", message] + ([] if parent is None else ["-p", parent])
        return self._sha_of(self._must(args,
                                                      env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}))

    # --- the only command that changes the remote -------------------------------------------------------------------
    def push(self, commit, ref):
        """Push `commit` to refs/heads/<ref> of the remote as a fast-forward (never forced). OK: the remote took it.
        REJECTED: the remote refused it (not a fast-forward, the ref exists when it was to be created, a rule or hook, or
        the ref was updated by another push first). UNCERTAIN: anything else (a timeout, no line for the ref, an OK flag
        with a failing exit code); the push may or may not have arrived."""
        if not _sha(commit):
            raise GitError(ARGS_INVALID, "commit")
        check_ref(ref)
        proc = self.run(["push", "--porcelain", self.remote, "%s:refs/heads/%s" % (commit, ref)])
        return _verdict(proc, commit, ref)
