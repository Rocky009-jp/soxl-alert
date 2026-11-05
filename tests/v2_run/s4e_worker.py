"""Independent child for the S4E-14 test. argv[1] is a JSON spec: workdir (its own clone of the remote), go (the signal file), log
(the file that this child's fake Discord appends the posted texts to), i (the number of the child: its `now` is shifted by that
many seconds, so that two children never make the same commit; the target day is the same), day (the target day), mode. It
prints READY, spins until the go file exists (no clock), runs `main morning` once and prints one JSON line."""
import json
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s4e_helpers as H  # noqa: E402  (disables sockets and the real urlopen in this process)


class LoggingNet(H.Net):
    """The fake network of the helper, whose Discord side appends every posted text to the log of this child."""

    def __init__(self, upto, log):
        super().__init__(upto)
        self.log = log

    def _discord(self, url, record):
        answer = super()._discord(url, record)
        H.B.append_line(self.log, record["content"])
        return answer


def main():
    spec = json.loads(sys.argv[1])
    now = H.aware(spec["day"]) + timedelta(seconds=spec["i"])
    net = LoggingNet(spec["day"], spec["log"])
    lines = []
    sys.stdout.write(json.dumps({"event": "READY"}) + "\n")
    sys.stdout.flush()
    while not os.path.exists(spec["go"]):
        pass
    code = H.R.main(["morning", "--mode", spec["mode"], "--workdir", spec["workdir"], "--code-version", H.CODE],
                    env={H.R.SECRET_NAME: H.WEBHOOK}, out=lines.append, now_fn=H.Clock(now), urlopen=net)
    kv = dict(l[2:].split(": ", 1) for l in "\n".join(lines).splitlines() if l.startswith("- ") and ": " in l)
    keep = ("run_outcome", "key", "delivery", "send_status", "code", "provenance.pinned_by", "provenance.market_sha256",
            "inputs_failure")
    sys.stdout.write(json.dumps({"exit": code, **{k: kv.get(k) for k in keep}}) + "\n")
    sys.stdout.flush()


main()
