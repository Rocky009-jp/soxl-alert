"""usage: refcheck108.py <protected list> <label>  (run inside a clone with the origin remote). Compares the 108 read-only refs of
this review (the 107 of the S4-D implementation and the implementation branch at 9bdd421) with the remote by full SHA."""
import subprocess
import sys

path, label = sys.argv[1], sys.argv[2]
want = dict(line.split() for line in open(path) if line.strip())
out = subprocess.run(["git", "ls-remote", "origin"], capture_output=True, text=True, check=True).stdout
have = {}
for line in out.splitlines():
    sha, ref = line.split("\t")
    have[ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref] = sha
bad = [(n, s, have.get(n)) for n, s in want.items() if have.get(n) != s]
print("%s: %d refs checked, %d mismatches" % (label, len(want), len(bad)))
for b in bad:
    print("  MISMATCH", b)
sys.exit(1 if bad else 0)
