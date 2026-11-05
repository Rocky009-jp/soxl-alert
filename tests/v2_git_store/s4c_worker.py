"""Independent child for the S4-C tests. argv[1] is a JSON spec: mode, clone (its work directory), parent (the mirror
parent), go (the signal file), log (the file this child's sender double appends the sent texts to), i (the number of the
child, which shifts its clock by that many seconds so that two children never make the same commit), last, decisions and
unconfirmed (as in the S4-B worker), rid, answer, and for the modes "push" / "claim": parent_sha / ref / name. It prints
READY, spins until the go file exists (no clock), runs once and prints one JSON line."""
import json
import os
import sys
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s4c_helpers as H  # noqa: E402  (disables sockets in this process)

GS, G, N, S = H.GS, H.G, H.N, H.S


class LoggingSender(object):
    def __init__(self, log, answer):
        self.log, self.answer = log, answer

    def send(self, text):
        H.B.append_line(self.log, text)
        return self.answer


class Recording(H.Spy):
    pass


def main():
    spec = json.loads(sys.argv[1])
    clk = lambda: H.WHEN + timedelta(seconds=spec.get("i", 0))  # noqa: E731
    git = Recording(spec["clone"], timeout=spec.get("timeout", 120))
    mode = spec["mode"]
    if mode in ("job", "resend", "claim", "init", "publish"):
        hist = GS.GitHistoryStore(git, H.STATE, clk)
        outbox = GS.GitOutbox(git, H.OUTBOX, spec["parent"], clk)
    w = H.P.World(0, unconfirmed=tuple(H.D[i] for i in spec.get("unconfirmed", ())))
    S.decide(w, spec.get("decisions", ()))
    if mode == "publish":                           # the publication is made from the history read before the signal
        pub = S.U.publish_day(hist.read(), H.D[spec["last"]], w.series, w.sessions, w.ledger)
    if mode == "push":
        git.fetch(spec["ref"])
        commit = git.commit_with(spec["parent_sha"], spec["name"], spec["name"].encode(), "v2 outbox " + spec["name"],
                                 clk(), replace=False)
    sender = LoggingSender(spec.get("log", os.devnull), spec.get("answer", "SENT"))
    sys.stdout.write(json.dumps({"event": "READY"}) + "\n")
    sys.stdout.flush()
    while not os.path.exists(spec["go"]):
        pass
    if mode == "job":
        report = N.morning_job(hist, outbox, sender, H.now_at(spec["last"]), w.series, w.sessions, w.ledger)
        out = {"run_outcome": report.run_outcome, "kind": report.kind, "delivery": report.delivery, "code": report.code,
               "existing": report.existing_status}
    elif mode == "resend":
        report = N.resend(outbox, sender, H.D[spec["last"]], spec.get("kind", "morning"), spec["rid"], H.now_at(spec["last"]))
        out = {"delivery": report.delivery, "original_status": report.original_status}
    elif mode == "push":
        out = {"verdict": git.push(commit, spec["ref"]), "porcelain": git.push_out}
    elif mode == "publish":
        try:
            hist.publish(pub)
            out = {"result": "PUBLISHED"}
        except H.GS.GitError as e:
            out = {"result": e.code}
        except Exception as e:
            out = {"result": getattr(e, "code", type(e).__name__)}
    elif mode == "init":
        try:
            outbox.initialize()
            out = {"result": "OK"}
        except Exception as e:
            out = {"result": getattr(e, "code", type(e).__name__)}
    elif mode == "claim":
        try:
            notice = N.compose_error_notice(H.D[spec["last"]], "x_code", "T", d_is_target=True)
            value = outbox.claim(notice, H.now_at(spec["last"]))
            out = {"result": "CLAIMED" if value else "NOT_CLAIMED"}
        except Exception as e:
            out = {"result": getattr(e, "code", type(e).__name__)}
    else:
        raise AssertionError(mode)
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


main()
