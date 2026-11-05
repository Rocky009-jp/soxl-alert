"""usage: refcheck.py <label> (inside a clone with origin). 103 read-only refs: the 102 of the S4-C implementation and the
implementation branch itself (ffa3700), compared with the remote by full SHA."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
want = dict(l.split() for l in open(os.path.join(HERE, "refs_protected103.txt")) if l.strip())
out = subprocess.run(["git", "ls-remote", "--heads", "origin"], capture_output=True, text=True, check=True).stdout
have = {r[len("refs/heads/"):]: s for s, r in (l.split("\t") for l in out.splitlines())}
bad = [(n, s, have.get(n)) for n, s in want.items() if have.get(n) != s]
print("%s: %d refs checked, %d mismatches" % (sys.argv[1], len(want), len(bad)))
for b in bad: print("  MISMATCH", b)
