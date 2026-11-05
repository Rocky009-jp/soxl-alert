"""Independent child for the S4-B race tests. argv[1] is a JSON spec: mode ("job" or "resend"), hist (the history root),
out (the outbox directory), log (the file this child's sender double appends the sent texts to), go (the signal file),
last (index of the day D to run for), decisions (indexes with a decision), unconfirmed (indexes of unconfirmed
sessions), rid (the resend_request_id), answer (what the sender double answers). The child builds the same synthetic
world as its parent, prints READY, spins until the go file exists (no clock), runs once and prints one JSON line."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s4b_helpers as H  # noqa: E402  (disables sockets in this process)
from v2_history_local import HistoryFileStore  # noqa: E402


class LoggingSender(object):
    def __init__(self, log, answer):
        self.log, self.answer = log, answer

    def send(self, text):
        H.append_line(self.log, text)
        return self.answer


def main():
    spec = json.loads(sys.argv[1])
    w = H.P.World(0, unconfirmed=tuple(H.D[i] for i in spec.get("unconfirmed", ())))
    H.S.decide(w, spec["decisions"])
    outbox = H.N.LocalOutbox(spec["out"], H.MODE)
    sender = LoggingSender(spec["log"], spec.get("answer", "SENT"))
    sys.stdout.write(json.dumps({"event": "READY"}) + "\n")
    sys.stdout.flush()
    while not os.path.exists(spec["go"]):
        pass
    now = H.now_at(H.D[spec["last"]])
    if spec["mode"] == "job":
        store = HistoryFileStore(spec["hist"], writable=True, durability=H.S.DURABILITY)
        report = H.N.morning_job(store, outbox, sender, now, w.series, w.sessions, w.ledger)
        out = {"run_outcome": report.run_outcome, "kind": report.kind, "delivery": report.delivery,
               "code": report.code, "exit_code": report.exit_code}
    else:
        report = H.N.resend(outbox, sender, H.D[spec["last"]], spec.get("kind", "morning"), spec["rid"], now)
        out = {"delivery": report.delivery, "original_status": report.original_status}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


main()
