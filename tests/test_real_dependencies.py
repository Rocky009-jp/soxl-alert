"""実ライブラリをimportしたうえでAPIだけをモックする境界試験（実データ・実Sheets無し）。"""
import inspect
import sys

import pandas as pd
import pytest

import main
from conftest import FakePost, FakeWrite, good_env, make_frames

yf = pytest.importorskip("yfinance")
gspread = pytest.importorskip("gspread")
sa = pytest.importorskip("oauth2client.service_account")


def _yf_like(close, open_):
    """yfinance(multi_level_index=True, group_by='column') 形式の合成: 列は (Price, Ticker)。"""
    data = pd.concat({"Close": close, "Open": open_, "High": close, "Low": close, "Volume": close * 0 + 1}, axis=1)
    data.columns.names = ["Price", "Ticker"]
    return data


def test_fetch_prices_extracts_columns_with_real_yfinance_import(monkeypatch):
    close, open_ = make_frames()
    calls = []
    monkeypatch.setattr(yf, "download", lambda *a, **k: calls.append((a, k)) or _yf_like(close, open_))
    c, o = main.fetch_prices()
    assert calls == [((["SOXX", "SOXL", "SPY", "IEF"],), {"period": "1y"})]  # 従来の呼出しのまま
    assert list(c.columns) == list(close.columns) and c.index.tz is None
    assert c.equals(close) and o.equals(open_)


def test_fetch_prices_handles_tz_aware_index(monkeypatch):
    close, open_ = make_frames()
    data = _yf_like(close, open_)
    data.index = data.index.tz_localize("America/New_York")
    monkeypatch.setattr(yf, "download", lambda *a, **k: data)
    c, o = main.fetch_prices()
    assert c.index.tz is None and c.index[-1] == pd.Timestamp("2026-10-23")


def test_full_run_with_real_fetch_path_and_mocked_download(monkeypatch):
    close, open_ = make_frames()
    monkeypatch.setattr(yf, "download", lambda *a, **k: _yf_like(close, open_))
    write = FakeWrite()
    code = main.run(env=good_env(), write_row=write, post=FakePost())
    assert code == 0 and len(write.calls) == 1


def test_append_sheet_row_passes_args_and_row_to_real_libs(monkeypatch):
    seen = {}

    class WS:
        def append_row(self, row):
            seen["row"] = row

    class Book:
        def worksheet(self, name):
            seen["ws"] = name
            return WS()

    class Client:
        def open_by_key(self, key):
            seen["key"] = key
            return Book()

    def fake_creds(d, scope):
        seen["creds"], seen["scope"] = d, scope
        return "CREDS"

    monkeypatch.setattr(sa.ServiceAccountCredentials, "from_json_keyfile_dict", staticmethod(fake_creds))
    monkeypatch.setattr(gspread, "authorize", lambda c: seen.setdefault("auth", c) and Client())
    main.append_sheet_row('{"k": "v"}', "SID", [1, 2])
    assert seen == {"creds": {"k": "v"}, "scope": ["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"], "auth": "CREDS", "key": "SID",
                    "ws": "Data", "row": [1, 2]}


def test_recorded_dependency_facts():
    """実依存の既定値（インストール版から確認できる事実。実データでの検証ではない）。"""
    p = inspect.signature(yf.download).parameters
    print("python", sys.version.split()[0], "yfinance", yf.__version__, "pandas", pd.__version__,
          "auto_adjust default", p["auto_adjust"].default,
          "multi_level_index default", p["multi_level_index"].default)
    assert "auto_adjust" in p and "multi_level_index" in p
