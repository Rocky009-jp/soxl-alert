"""ad83f9b のレビュー指摘 IR-01〜IR-05 の回帰試験（旧48件とは別）。"""
import http.server
import os
import shutil
import subprocess
import threading

import numpy as np
import pandas as pd
import pytest
import requests
import yaml

import main
import soxl_checks
import soxl_notify
from conftest import SECRETS, FakePost, FakeWrite, good_env, make_frames

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET_TS = pd.Timestamp("2026-10-23")


def run(frames=None, env=None, post=None, write=None, fetch=None):
    close, open_ = frames or make_frames()
    post = post or FakePost()
    write = write or FakeWrite()
    code = main.run(env=env or good_env(), fetch=fetch or (lambda: (close, open_)),
                    write_row=write, post=post)
    return code, post, write


# ---------- IR-02: RSI入力の全履歴検査 ----------
@pytest.mark.parametrize("pos", [0, 1, 30, 59])  # 直近200行より古い位置（n=260）
@pytest.mark.parametrize("bad", [-5.0, 0.0, float("nan"), float("inf"), -float("inf")])
def test_ir02_old_history_bad_price_rejected(monkeypatch, capsys, pos, bad):
    close, open_ = make_frames()
    close.iloc[pos, close.columns.get_loc("SOXX")] = bad
    judged = []
    monkeypatch.setattr(soxl_checks, "technical_conditions", lambda i: judged.append(1))
    code, post, write = run((close, open_))
    assert code == 1 and judged == [] and write.calls == []
    assert len(post.calls) == 1 and "運用エラー" in post.calls[0]["json"]["content"]
    assert "全体を検査" in post.calls[0]["json"]["content"]


def test_ir02_valid_input_still_matches_legacy():
    close, open_ = make_frames(seed=3)
    ind = soxl_checks.validate_and_compute(close, open_, TARGET_TS)
    d = close["SOXX"].diff()
    rs = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-1 * d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    assert ind.rsi == (100 - 100 / (1 + rs)).iloc[-1]


# ---------- IR-03: リダイレクト禁止（実Requests＋ローカルサーバ） ----------
@pytest.fixture
def redirect_server():
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        code = 302

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            hits.append(self.path)
            if self.path.startswith("/hook"):
                self.send_response(type(self).code)
                self.send_header("Location", "/target")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/hook", H, hits
    httpd.shutdown()


def test_ir03_post_passes_allow_redirects_false():
    code, post, _ = run()
    assert post.calls[0]["allow_redirects"] is False


@pytest.mark.parametrize("status", [302, 307, 308])
def test_ir03_real_requests_does_not_follow_redirect(redirect_server, capsys, status):
    url, H, hits = redirect_server
    H.code = status
    result, st = soxl_notify.post_message(url, "x")
    assert (result, st) == (soxl_notify.SENT_HTTP_ERROR, status)
    assert hits == ["/hook"]  # 遷移先へ要求しない・1回のみ


def test_ir03_main_with_real_requests_redirect_is_nonzero(redirect_server, capsys):
    url, H, hits = redirect_server
    H.code = 307
    close, open_ = make_frames()
    code = main.run(env=good_env(DISCORD_WEBHOOK_URL=url), fetch=lambda: (close, open_),
                    write_row=FakeWrite())
    out = capsys.readouterr().out
    assert code == 1 and hits == ["/hook"] and "送信成功" not in out and "HTTP 307" in out


def test_ir03_real_requests_500_and_timeout_kept(redirect_server):
    url, H, hits = redirect_server
    H.code = 500
    assert soxl_notify.post_message(url, "x")[0] == soxl_notify.SENT_HTTP_ERROR
    assert soxl_notify.post_message("http://127.0.0.1:9/hook", "x")[0] == soxl_notify.SENT_UNKNOWN


# ---------- IR-04: 対象日の紐付け ----------
def test_ir04_error_and_logs_carry_target_date(capsys):
    close, open_ = make_frames()
    close.iloc[-1, 0] = float("nan")
    code, post, _ = run((close, open_), post=FakePost(status=500))
    out = capsys.readouterr().out
    assert code == 1
    assert "対象取引日: 2026/10/23" in post.calls[0]["json"]["content"]
    assert "通知（2026/10/23）: HTTP失敗（HTTP 500）" in out


def test_ir04_fetch_failure_and_unknown_delivery_carry_date(capsys):
    def boom():
        raise RuntimeError("x")
    code, post, _ = run(fetch=boom, post=FakePost(raises=TimeoutError("t")))
    out = capsys.readouterr().out
    assert "対象取引日: 2026/10/23" in post.calls[0]["json"]["content"]
    assert "通知（2026/10/23）: 配信不明（TimeoutError）" in out


def test_ir04_success_log_carries_date(capsys):
    run()
    assert "通知（2026/10/23）: 送信成功（HTTP 204）" in capsys.readouterr().out


@pytest.mark.parametrize("raw", [None, "SECRET_BAD_DATE_VALUE", "2026-13-99"])
def test_ir04_missing_or_invalid_date_is_unconfirmed_without_raw_value(capsys, raw):
    code, post, _ = run(env=good_env(TARGET_SESSION_DATE=raw))
    out = capsys.readouterr().out
    text = out + post.calls[0]["json"]["content"]
    assert code == 1 and "対象日未確定" in text and "通知（対象日未確定）" in out
    if raw:
        assert raw not in text


# ---------- IR-01: curl の秘密漏れ ----------
WF = os.path.join(ROOT, ".github", "workflows", "schedule.yml")


def _reporter_script():
    with open(WF, encoding="utf-8") as f:
        return yaml.safe_load(f)["jobs"]["run-bot"]["steps"][-1]["run"]


def _run_reporter(url):
    env = {"PATH": os.environ["PATH"], "DISCORD_WEBHOOK_URL": url}
    return subprocess.run(["bash", "-e", "-c", _reporter_script()], env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash/curl が必要")
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:1/[SYNTHETIC_WEBHOOK_TOKEN",          # 不正な括弧
    "http://127.0.0.1:1/api/SYNTHETIC_WEBHOOK_TOKEN]]",     # 閉じ括弧
    "ht!tp://SYNTHETIC_WEBHOOK_TOKEN",                      # 不正なスキーム
    "http://SYNTHETIC_WEBHOOK_TOKEN:99999999/x",            # 不正なポート
    "http://127.0.0.1:1/a\nSYNTHETIC_WEBHOOK_TOKEN",        # 改行
    "http://127.0.0.1:1/ SYNTHETIC_WEBHOOK_TOKEN {a}",      # 空白・波括弧
    "SYNTHETIC_WEBHOOK_TOKEN",                              # スキームなし
])
def test_ir01_malformed_urls_do_not_leak_to_stdout_or_stderr(url):
    r = _run_reporter(url)
    assert r.returncode != 0
    assert "SYNTHETIC_WEBHOOK_TOKEN" not in r.stdout + r.stderr
    assert "curl:" not in r.stdout + r.stderr
    assert "失敗報告:" in r.stdout


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash/curl が必要")
def test_ir01_redirect_and_location_not_followed_or_printed():
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            hits.append(self.path)
            self.send_response(307)
            self.send_header("Location", "/SYNTHETIC_LOCATION_TOKEN")
            self.end_headers()

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        r = _run_reporter(f"http://127.0.0.1:{httpd.server_address[1]}/hook")
    finally:
        httpd.shutdown()
    assert r.returncode != 0 and hits == ["/hook"]
    assert "SYNTHETIC_LOCATION_TOKEN" not in r.stdout + r.stderr
    assert "HTTP失敗（HTTP 307）" in r.stdout


# ---------- IR-05: 生成物の除外 ----------
def test_ir05_generated_files_not_tracked_and_ignored():
    if not shutil.which("git") or not os.path.isdir(os.path.join(ROOT, ".git")):
        pytest.skip("git チェックアウトが必要")
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert not [f for f in tracked if "__pycache__" in f or f.endswith((".pyc", ".pyo", ".pyd"))]
    ignore = open(os.path.join(ROOT, ".gitignore"), encoding="utf-8").read()
    assert "__pycache__/" in ignore and "*.py[cod]" in ignore
