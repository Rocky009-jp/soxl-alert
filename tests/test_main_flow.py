import math

import pandas as pd
import pytest

import main
import soxl_checks
from conftest import (SECRETS, SECRET_GCP, FakePost, FakeWrite, good_env, make_frames)


def run(close_open=None, env=None, post=None, write=None, fetch=None):
    close, open_ = close_open or make_frames()
    post = post or FakePost()
    write = write or FakeWrite()
    fetch = fetch or (lambda: (close, open_))
    code = main.run(env=env or good_env(), fetch=fetch, write_row=write, post=post)
    return code, post, write


def assert_no_secrets(capsys):
    out = capsys.readouterr()
    text = out.out + out.err
    for s in SECRETS:
        assert s not in text, s
    return text


def msg(post, i=0):
    return post.calls[i]["json"]["content"]


# --- #1 正常・条件未達 ---
def test_case1_normal_condition_unmet(capsys):
    code, post, write = run(make_frames(soxx="down"))
    assert code == 0
    assert len(post.calls) == 1 and len(write.calls) == 1
    m = msg(post)
    assert "実行サマリ" in m and "2026/10/23" in m and "データ検査: OK" in m
    assert "技術条件は未達" in m and "F&G: 目視未確認" in m and "Sheets記録: 成功" in m
    assert post.calls[0]["timeout"] is not None
    assert_no_secrets(capsys)


# --- #2 技術条件成立でも購入推奨にしない ---
def test_case2_technical_met_is_not_recommendation(capsys):
    close, open_ = make_frames(soxx="up")
    ind = soxl_checks.validate_and_compute(close, open_, pd.Timestamp("2026-10-23"))
    assert soxl_checks.technical_conditions(ind)["all"], (ind.rsi, ind.shd)
    code, post, _ = run((close, open_))
    m = msg(post)
    assert code == 0 and "技術条件3つすべて成立" in m
    assert "購入推奨・購入可否の確定ではありません" in m
    for bad in ("買いシグナル", "買いタイミング", "購入してください", "数量", "初回", "再エントリー"):
        assert bad not in m


# --- #3 元価格欠損でRSIは数値が残る ---
def _spy_judge(monkeypatch):
    called = []
    monkeypatch.setattr(soxl_checks, "technical_conditions", lambda i: called.append(1))
    return called


@pytest.mark.parametrize("col,which", [("SOXX", "close"), ("SOXL", "close"), ("SPY", "close"),
                                        ("IEF", "close"), ("SOXL", "open")])
def test_case3_missing_latest_raw_price_blocks_judgement(monkeypatch, capsys, col, which):
    close, open_ = make_frames()
    (close if which == "close" else open_).iloc[-1, (close if which == "close" else open_).columns.get_loc(col)] = float("nan")
    # 従来方式（NaN越しのRSI）では数値が残ることを確認
    if col == "SOXX":
        delta = close["SOXX"].diff()
        rs = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        assert math.isfinite((100 - 100 / (1 + rs)).iloc[-1])
    judged = _spy_judge(monkeypatch)
    code, post, write = run((close, open_))
    assert code == 1 and judged == [] and write.calls == []
    assert len(post.calls) == 1 and "運用エラー" in msg(post) and "条件未達ではありません" in msg(post)
    assert_no_secrets(capsys)


def test_case3_nan_inside_window_not_carried_over(monkeypatch):
    close, open_ = make_frames()
    close.iloc[-5, close.columns.get_loc("SOXX")] = float("nan")
    judged = _spy_judge(monkeypatch)
    code, post, write = run((close, open_))
    assert code == 1 and judged == [] and write.calls == []


def test_case3_shd_does_not_fall_back_to_older_common_date(monkeypatch):
    close, open_ = make_frames()
    close.iloc[-3, close.columns.get_loc("IEF")] = float("nan")
    judged = _spy_judge(monkeypatch)
    code, post, write = run((close, open_))
    assert code == 1 and judged == [] and write.calls == []


# --- #4 日付不一致・履歴不足・構造不正 ---
def _bad_frames():
    c, o = make_frames()
    yield "stale_last_row", (c.iloc[:-1], o.iloc[:-1])
    yield "future_row", make_frames(end=pd.Timestamp("2026-10-26"))
    yield "open_stale", (c, o.iloc[:-1])
    yield "short_history", make_frames(n=150)
    yield "missing_ticker", (c.drop(columns=["IEF"]), o)
    yield "empty", (c.iloc[0:0], o.iloc[0:0])
    yield "unsorted", (c.iloc[::-1], o.iloc[::-1])
    dup = c.copy(); dup.index = list(dup.index[:-1]) + [dup.index[-2]]
    yield "duplicate_dates", (dup, o)
    yield "not_datetime_index", (c.reset_index(drop=True), o.reset_index(drop=True))
    yield "not_a_frame", (None, None)


@pytest.mark.parametrize("name,frames", list(_bad_frames()), ids=[n for n, _ in _bad_frames()])
def test_case4_invalid_structure_or_dates(monkeypatch, capsys, name, frames):
    judged = _spy_judge(monkeypatch)
    code, post, write = run(frames)
    assert code == 1 and judged == [] and write.calls == []
    assert len(post.calls) == 1 and "運用エラー" in msg(post)
    assert_no_secrets(capsys)


def test_case4_tz_aware_index_is_normalized():
    c, o = make_frames()
    c.index, o.index = c.index.tz_localize("America/New_York"), o.index.tz_localize("America/New_York")
    code, post, _ = run((c, o))
    assert code == 0


def test_fetch_exception_is_operational_error(capsys):
    def boom():
        raise RuntimeError("internal detail with SECRET_WEBHOOK_TOKEN_123")
    judged = []
    code, post, write = run(fetch=boom)
    assert code == 1 and write.calls == [] and len(post.calls) == 1
    assert "RuntimeError" in msg(post) and "SECRET" not in msg(post)
    assert_no_secrets(capsys)


# --- #5 Sheets ---
def test_case5_sheets_failure_notifies_then_nonzero(capsys):
    log = []
    post, write = FakePost(log=log), FakeWrite(raises=RuntimeError("auth failed SECRET_PRIVATE_KEY_456"), log=log)
    code, post, write = run(post=post, write=write)
    assert code == 1 and log == ["write", "post"]
    m = msg(post)
    assert "部分失敗" in m and "記録失敗" in m and "判定:" in m and "SECRET" not in m
    text = assert_no_secrets(capsys)
    assert "RuntimeError" in text


def test_sheets_failure_and_notify_failure_still_nonzero():
    code, post, write = run(post=FakePost(status=500), write=FakeWrite(raises=OSError("x")))
    assert code == 1 and len(post.calls) == 1


def test_sheets_explicitly_disabled_is_normal(capsys):
    code, post, write = run(env=good_env(SHEETS_ENABLED="false", GCP_CREDENTIALS=None, SPREADSHEET_ID=None))
    assert code == 0 and write.calls == []
    assert "無効設定" in msg(post)


@pytest.mark.parametrize("over", [
    {"SHEETS_ENABLED": None},
    {"SHEETS_ENABLED": "maybe"},
    {"GCP_CREDENTIALS": None},
    {"SPREADSHEET_ID": None},
    {"TARGET_SESSION_DATE": None},
    {"TARGET_SESSION_DATE": "2026/10/23"},
])
def test_required_config_missing_is_error_not_disabled(capsys, over):
    fetched = []
    code, post, write = run(env=good_env(**over), fetch=lambda: fetched.append(1))
    assert code == 1 and fetched == [] and write.calls == []
    assert len(post.calls) == 1 and "運用エラー" in msg(post) and "設定確認" in msg(post)
    assert_no_secrets(capsys)


def test_missing_webhook_is_nonzero_and_not_silent(capsys):
    code, post, write = run(env=good_env(DISCORD_WEBHOOK_URL=None))
    assert code == 1 and post.calls == [] and write.calls == []
    assert "DISCORD_WEBHOOK_URL" in capsys.readouterr().out


# --- #6 通知失敗 ---
def test_case6_explicit_http_failure(capsys):
    code, post, _ = run(post=FakePost(status=500))
    text = assert_no_secrets(capsys)
    assert code == 1 and len(post.calls) == 1  # 自動再送なし
    assert "HTTP失敗（HTTP 500）" in text and "配信不明（" not in text and "通知HTTP失敗" in text


def test_case6_delivery_unknown_on_timeout(capsys):
    import requests
    code, post, _ = run(post=FakePost(raises=requests.Timeout("timed out for https://discord.example/api/webhooks/SECRET_WEBHOOK_TOKEN_123")))
    text = assert_no_secrets(capsys)
    assert code == 1 and len(post.calls) == 1
    assert "配信不明（Timeout）" in text


def test_notify_failure_on_error_path_keeps_original_failure_without_recursion(capsys):
    close, open_ = make_frames()
    close.iloc[-1, 0] = float("nan")
    code, post, _ = run((close, open_), post=FakePost(raises=ConnectionError("down")))
    assert code == 1 and len(post.calls) == 1
    assert "運用エラー" in capsys.readouterr().out


def test_non_2xx_is_not_logged_as_success(capsys):
    run(post=FakePost(status=302))
    assert "送信成功" not in capsys.readouterr().out


# --- #9 保有を読まない・0株にしない ---
def test_case9_no_holding_dependent_output():
    code, post, _ = run(make_frames(soxx="up"))
    m = msg(post)
    for bad in ("0株", "非保有", "数量", "配分", "初回", "再エントリー", "追加買い"):
        assert bad not in m
    assert "保有状態は確認していません" in m


# --- #11 / #12a 売却系の抑止 ---
SELL_WORDS = ("売りシグナル", "売却", "全額", "緊急脱出", "利益確定", "過熱", "参考")


@pytest.mark.parametrize("make", [
    lambda: make_frames(soxx="hot"),                       # RSI高
    lambda: make_frames(soxx="down", spy_ret=0.08, ief_ret=-0.01),  # SHD>=3.0
])
def test_case11_12a_old_sell_condition_gives_no_sell_or_reference(make):
    close, open_ = make()
    ind = soxl_checks.validate_and_compute(close, open_, pd.Timestamp("2026-10-23"))
    assert ind.rsi >= 70 or ind.shd >= 3.0
    code, post, _ = run((close, open_))
    assert code == 0 and len(post.calls) == 1
    for w in SELL_WORDS:
        assert w not in msg(post), w


# --- 計算式が従来と同一 ---
def test_indicators_match_legacy_formulas():
    close, open_ = make_frames(soxx="hot", spy_ret=0.05, ief_ret=-0.02, seed=7)
    ind = soxl_checks.validate_and_compute(close, open_, pd.Timestamp("2026-10-23"))
    sma = close["SOXX"].rolling(window=200).mean().iloc[-1]
    kairi = ((close["SOXX"].iloc[-1] - sma) / sma) * 100
    sp = close[["SPY", "IEF"]].dropna()
    shd = ((sp["SPY"].iloc[-1] / sp["SPY"].iloc[-21] - 1) - (sp["IEF"].iloc[-1] / sp["IEF"].iloc[-21] - 1)) * 100
    d = close["SOXX"].diff()
    rs = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-1 * d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + rs)).iloc[-1]
    assert (ind.soxx_sma200, ind.soxx_kairi, ind.shd, ind.rsi) == (sma, kairi, shd, rsi)


# --- 境界・import ---
def test_import_has_no_network_or_heavy_deps():
    import subprocess
    import sys
    root = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, %r); import main; "
            "assert 'yfinance' not in sys.modules and 'gspread' not in sys.modules")
    r = subprocess.run([sys.executable, "-c", code % root], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_network_is_actually_blocked():
    import requests
    with pytest.raises(Exception):
        requests.get("http://example.com", timeout=1)
