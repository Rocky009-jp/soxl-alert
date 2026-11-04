"""Independent child for the S4-A race test. argv[1] is a JSON spec: root, last (index of D to run for), decisions
(indexes with a decision), go (path of the signal file). The child builds the same synthetic world as its parent, prints
READY, spins until the go file exists (no clock), runs the morning once and prints one JSON line."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s4a_helpers as S  # noqa: E402  (disables sockets in this process)
from v2_history_local import HistoryFileStore  # noqa: E402


def main():
    spec = json.loads(sys.argv[1])
    w = S.P.World(0)
    S.decide(w, spec["decisions"])
    store = HistoryFileStore(spec["root"], writable=True, durability=S.DURABILITY)
    sys.stdout.write(json.dumps({"event": "READY"}) + "\n")
    sys.stdout.flush()
    while not os.path.exists(spec["go"]):
        pass
    report = S.run(store, w, S.now_at(S.D[spec["last"]]))
    sys.stdout.write(json.dumps({"outcome": report.outcome, "code": report.code,
                                 "consumed": [c.d for c in report.consumed]}) + "\n")
    sys.stdout.flush()


main()
