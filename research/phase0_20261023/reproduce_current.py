"""Offline characterization of the pinned production script; no production fix.

Use a disposable environment with pandas==2.3.3 and numpy==2.2.6.
All remote adapters are replaced, and Python socket connections are blocked.
The fixture is synthetic. It is not a reconstruction of Yahoo's original payload.
"""
import ast
import contextlib
import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import socket
import sys
import types
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
if (BASE / "site_packages").exists():
    sys.path.insert(0, str(BASE / "site_packages"))
import numpy as np
import pandas as pd

SOURCE = BASE / "current_main.py"
EXPECTED_BLOB = "7926aa563455822dceb0fd09c43033e21e7198bc"


def git_blob(blob):
    return hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()


def fixture(kind="buy", count=260, end="2026-10-22"):
    dates = pd.bdate_range(end=end, periods=count)
    prices = [100 + .3 * i if i < count - 30
              else 100 + .3 * (count - 31) - .1 * (i - (count - 31))
              for i in range(count)]
    if kind == "sell":
        prices = [100 + .3 * i for i in range(count)]
    close = pd.DataFrame({"SOXX": prices, "SOXL": np.linspace(30, 45, count),
                          "SPY": np.full(count, 100.),
                          "IEF": np.linspace(100, 125, count)}, index=dates)
    return pd.concat({"Close": close, "Open": close * .99}, axis=1)


def execute(frame, *, webhook=True, http_status=204, sheet_failure=False,
            repeats=1):
    calls = {"download": 0, "post": [], "sheet_rows": [], "sheet_attempts": 0,
             "credentials": 0, "network_attempts": 0}
    yf = types.ModuleType("yfinance")

    def download(*args, **kwargs):
        calls["download"] += 1
        return frame.copy(deep=True)

    yf.download = download
    requests = types.ModuleType("requests")

    class Response:
        status_code = http_status
        text = "synthetic response"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("synthetic HTTP failure")

    def post(url, **kwargs):
        calls["post"].append({"status": http_status, "content": kwargs["json"]["content"],
                              "timeout_configured": "timeout" in kwargs})
        return Response()

    requests.post = post
    gspread = types.ModuleType("gspread")

    class Sheet:
        def open_by_key(self, _key):
            return self

        def worksheet(self, name):
            assert name == "Data"
            return self

        def append_row(self, row):
            calls["sheet_attempts"] += 1
            if sheet_failure:
                raise RuntimeError("synthetic spreadsheet failure")
            calls["sheet_rows"].append(row)

    gspread.authorize = lambda creds: Sheet()
    oauth = types.ModuleType("oauth2client")
    service = types.ModuleType("oauth2client.service_account")

    class Credentials:
        @staticmethod
        def from_json_keyfile_dict(creds, scope):
            calls["credentials"] += 1
            return object()

    service.ServiceAccountCredentials = Credentials
    oauth.service_account = service
    modules = {"yfinance": yf, "requests": requests, "gspread": gspread,
               "oauth2client": oauth, "oauth2client.service_account": service}
    env = {"DISCORD_WEBHOOK_URL": "https://example.invalid/mock" if webhook else "",
           "SPREADSHEET_ID": "synthetic-only", "GCP_CREDENTIALS": "{}"}

    def block(*args, **kwargs):
        calls["network_attempts"] += 1
        raise AssertionError("NETWORK BLOCKED BY OFFLINE HARNESS")

    output = io.StringIO()
    exception = None
    namespace = {"__name__": "offline_subject", "__file__": str(SOURCE)}
    with patch.dict(sys.modules, modules), patch.dict(os.environ, env), \
            patch.object(socket.socket, "connect", block), \
            patch.object(socket, "create_connection", block), \
            contextlib.redirect_stdout(output):
        exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), namespace)
        try:
            for _ in range(repeats):
                namespace["main"]()
        except Exception as error:
            exception = {"type": type(error).__name__, "message": str(error)}
    assert calls["network_attempts"] == 0
    return {"exception": exception, "stdout": output.getvalue().splitlines(), **calls}


def run():
    blob = SOURCE.read_bytes()
    assert git_blob(blob) == EXPECTED_BLOB, "Pinned source differs"
    cases = []

    def check(name, result, assertion):
        assert assertion(result), (name, result)
        cases.append({"id": name, "characterization_confirmed": True, **result})

    good = fixture()
    check("complete_buy_fixture_control", execute(good),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and "買い" in r["post"][0]["content"] and len(r["sheet_rows"]) == 1)
    empty_tail = good.copy()
    empty_tail.iloc[-1, :] = np.nan
    check("nan_tail_silently_reported_as_no_signal", execute(empty_tail),
          lambda r: r["exception"] is None and not r["post"] and not r["sheet_rows"]
          and any("条件未達" in s for s in r["stdout"])
          and any("SOXX nan" in s for s in r["stdout"]))
    check("http_404_reported_as_sent", execute(good, http_status=404),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and any("Discordへ通知を送信しました" in s for s in r["stdout"]))
    check("http_429_reported_as_sent", execute(good, http_status=429),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and not r["post"][0]["timeout_configured"])
    check("webhook_missing_normal_return", execute(good, webhook=False),
          lambda r: r["exception"] is None and not r["post"]
          and any("URLが設定されていない" in s for s in r["stdout"]))
    check("sheet_failure_normal_return", execute(good, sheet_failure=True),
          lambda r: r["exception"] is None and r["sheet_attempts"] == 1
          and not r["sheet_rows"] and len(r["post"]) == 1)
    check("repeated_run_duplicates_same_day", execute(good, repeats=2),
          lambda r: r["exception"] is None and len(r["post"]) == 2
          and len(r["sheet_rows"]) == 2
          and r["sheet_rows"][0] == r["sheet_rows"][1])
    check("stale_complete_data_still_generates_alert", execute(fixture(end="2026-10-01")),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and "2026/10/01" in r["post"][0]["content"])
    check("empty_download_unhandled_index_error", execute(good.iloc[:0]),
          lambda r: r["exception"] is not None
          and r["exception"]["type"] == "IndexError")
    sell_nan = fixture("sell")
    sell_nan.iloc[-1, :] = np.nan
    check("nan_tail_can_still_emit_sell_from_retained_rsi", execute(sell_nan),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and "売り" in r["post"][0]["content"] and not r["sheet_rows"])
    short = fixture("sell", count=50)
    check("under_200_rows_can_still_emit_sell", execute(short),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and not r["sheet_rows"])
    mixed = good.copy()
    for ticker in ["SPY", "IEF"]:
        mixed.loc[mixed.index[-1], ("Close", ticker)] = np.nan
    check("mixed_indicator_dates_still_emit_alert", execute(mixed),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and any("日付=2026/10/21" in s for s in r["stdout"])
          and "2026/10/22" in r["post"][0]["content"])
    check("sell_without_position_or_cost_basis_input", execute(fixture("sell")),
          lambda r: r["exception"] is None and len(r["post"]) == 1
          and "全額売却" in r["post"][0]["content"])
    previous = BASE / "broken_indent_main.py"
    if previous.exists():
        try:
            ast.parse(previous.read_text(encoding="utf-8"))
        except IndentationError as error:
            cases.append({"id": "historical_966c323_syntax_error", "characterization_confirmed": True,
                          "exception": {"type": type(error).__name__, "line": error.lineno}})
        else:
            raise AssertionError("Historical syntax error not reproduced")
    result = {"production_commit": "7731ef0c4e02a3a26ae80dcb7ed79f2842c0c2cb",
              "production_blob": EXPECTED_BLOB,
              "source_sha256": hashlib.sha256(blob).hexdigest(),
              "fixture_type": "synthetic: missing trailing row and adapter faults",
              "historical_payload_recovered": False,
              "environment": {"python": sys.version.split()[0], "pandas": pd.__version__,
                              "numpy": np.__version__},
              "checked": len(cases), "cases": cases,
              "note": "Confirmed defect characterizations, not fixed-production acceptance tests."}
    (BASE / "reproduction_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"checked": len(cases), "network_calls": 0,
                      "production_modified": False,
                      "cases": [case["id"] for case in cases]}, ensure_ascii=False))


if __name__ == "__main__":
    run()
