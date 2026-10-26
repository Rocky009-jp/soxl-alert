import os
import socket
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TARGET = pd.Timestamp("2026-10-23")
SECRET_URL = "https://discord.example/api/webhooks/SECRET_WEBHOOK_TOKEN_123"
SECRET_GCP = '{"private_key": "SECRET_PRIVATE_KEY_456"}'
SECRET_BODY = "SECRET_RESPONSE_BODY_789"
SECRETS = ["SECRET_WEBHOOK_TOKEN_123", "SECRET_PRIVATE_KEY_456", "SECRET_RESPONSE_BODY_789",
           "discord.example"]


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """ループバック以外への接続・名前解決を禁止する。"""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost") and not str(host).startswith("/"):
            raise OSError("network blocked in tests")
        return real_connect(self, address)

    def blocked_getaddrinfo(host, *a, **k):
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError("network blocked in tests")
        return real_getaddrinfo(host, *a, **k)

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", blocked_getaddrinfo)


def make_frames(n=260, soxx="up", spy_ret=-0.02, ief_ret=0.01, seed=1, end=TARGET):
    """合成の終値・始値（4銘柄）。土日を除く営業日。"""
    idx = pd.bdate_range(end=end, periods=n)
    rng = np.random.default_rng(seed)
    if soxx == "up":  # 上昇基調＋直近押し目（RSI<=55・SOXX>200SMA を狙う）
        base = np.linspace(100, 200, n) + rng.normal(0, 0.2, n)
        base[-12:] = np.linspace(base[-13], base[-13] * 0.93, 12)
    elif soxx == "down":
        base = np.linspace(200, 100, n) + rng.normal(0, 0.2, n)
    elif soxx == "hot":  # 直近急騰でRSI高
        base = np.linspace(100, 150, n) + rng.normal(0, 0.1, n)
        base[-15:] = np.linspace(base[-16], base[-16] * 1.3, 15)
    else:
        raise ValueError(soxx)
    spy = np.full(n, 100.0)
    ief = np.full(n, 100.0)
    spy[-21:] = np.linspace(100, 100 * (1 + spy_ret), 21)
    ief[-21:] = np.linspace(100, 100 * (1 + ief_ret), 21)
    close = pd.DataFrame({"SOXX": base, "SOXL": base * 0.3, "SPY": spy, "IEF": ief}, index=idx)
    open_ = close * 0.995
    return close, open_


class FakePost:
    def __init__(self, status=204, body=SECRET_BODY, raises=None, log=None):
        self.status, self.body, self.raises = status, body, raises
        self.calls = []
        self.log = log if log is not None else []

    def __call__(self, url, json=None, timeout=None, allow_redirects=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout,
                           "allow_redirects": allow_redirects})
        self.log.append("post")
        if self.raises:
            raise self.raises
        return type("R", (), {"status_code": self.status, "text": self.body})()


class FakeWrite:
    def __init__(self, raises=None, log=None):
        self.raises, self.calls = raises, []
        self.log = log if log is not None else []

    def __call__(self, creds, sid, row):
        self.calls.append(row)
        self.log.append("write")
        if self.raises:
            raise self.raises


def good_env(**over):
    env = {
        "DISCORD_WEBHOOK_URL": SECRET_URL,
        "SHEETS_ENABLED": "true",
        "GCP_CREDENTIALS": SECRET_GCP,
        "SPREADSHEET_ID": "sheet-id",
        "TARGET_SESSION_DATE": "2026-10-23",
    }
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}
