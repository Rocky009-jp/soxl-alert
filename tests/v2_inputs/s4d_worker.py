"""Independent child for the S4D-13(d) test. argv[1] is a JSON spec: clone (its work directory), parent (the mirror parent of
its outbox), go (the signal file), log (the file this child's sender double appends the sent texts to), i (the number of
the child, which shifts its clock by that many seconds so that two children never make the same commit), day (the target
day), start (the start of the history) and scale (the revision of the adjusted close that this child's source shows). It
prints READY, spins until the go file exists (no clock), runs load_inputs and the morning once and prints one JSON line."""
import json
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s4d_helpers as H  # noqa: E402  (disables sockets in this process)

I, N, GS = H.I, H.N, H.GS


class LoggingSender(object):
    def __init__(self, log):
        self.log = log

    def send(self, text):
        H.B.append_line(self.log, text)
        return "SENT"


def main():
    spec = json.loads(sys.argv[1])
    clk = lambda: H.C.WHEN + timedelta(seconds=spec["i"])  # noqa: E731
    git = GS.Git(spec["clone"])
    hist = GS.GitHistoryStore(git, H.C.STATE, clk)
    outbox = GS.GitOutbox(git, H.C.OUTBOX, spec["parent"], clk)
    day = spec["day"]
    provider = H.Provider(day, scale=spec["scale"])
    now = H.jst_morning(day)
    sys.stdout.write(json.dumps({"event": "READY"}) + "\n")
    sys.stdout.flush()
    while not os.path.exists(spec["go"]):
        pass
    inp = I.load_inputs(git, provider, now, H.REFS, clk)
    report = N.morning_job(I.guarded_store(hist, inp.failure), outbox, LoggingSender(spec["log"]), now, inp.series,
                           inp.sessions, inp.raw_observations)
    out = {"failure": None if inp.failure is None else inp.failure.code,
           "pinned_by": inp.provenance.get("pinned_by"), "sha": inp.provenance.get("market_sha256"),
           "fetch_count": inp.provenance.get("fetch_count"),
           "run_outcome": report.run_outcome, "code": report.code, "kind": report.kind, "delivery": report.delivery}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


main()
