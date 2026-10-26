"""データ検査と指標計算（ネットワーク・Sheets・通知に依存しない）。"""
import math
from dataclasses import dataclass

import pandas as pd

TICKERS = ["SOXX", "SOXL", "SPY", "IEF"]
SMA_WINDOW = 200
SHD_LOOKBACK = 21  # 既存実装の iloc[-21] と同じ（20日騰落率）


class DataValidationError(Exception):
    """検査NG。reasons は非秘密の固定文言のみ。"""

    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


@dataclass(frozen=True)
class Indicators:
    target_date: str
    soxx_close: float
    soxx_sma200: float
    soxx_kairi: float
    rsi: float
    shd: float
    soxl_close: float
    soxl_open: float


def _finite_positive(value):
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(v) and v > 0


def _normalize_index(frame, label, reasons):
    """DatetimeIndex・tz無し・昇順・重複なしを確認し、正規化した表を返す。"""
    if not isinstance(frame, pd.DataFrame):
        reasons.append(f"{label}: 表形式のデータではありません")
        return None
    if frame.empty:
        reasons.append(f"{label}: データが空です")
        return None
    if not isinstance(frame.index, pd.DatetimeIndex):
        reasons.append(f"{label}: 日付インデックスではありません")
        return None
    out = frame.copy()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    if not out.index.is_monotonic_increasing:
        reasons.append(f"{label}: 日付の順序が不正です")
        return None
    if out.index.has_duplicates:
        reasons.append(f"{label}: 日付が重複しています")
        return None
    return out


def compute_indicators(close, open_, target_date):
    """検査済みの表から指標を計算する。式は従来の main.py と同一。"""
    soxx = close["SOXX"]
    sma = soxx.rolling(window=SMA_WINDOW).mean().iloc[-1]
    latest = soxx.iloc[-1]
    kairi = ((latest - sma) / sma) * 100

    shd_prices = close[["SPY", "IEF"]].dropna()
    spy_ret = (shd_prices["SPY"].iloc[-1] / shd_prices["SPY"].iloc[-SHD_LOOKBACK]) - 1
    ief_ret = (shd_prices["IEF"].iloc[-1] / shd_prices["IEF"].iloc[-SHD_LOOKBACK]) - 1
    shd = (spy_ret - ief_ret) * 100

    delta = soxx.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rma_up = up.ewm(alpha=1 / 14, adjust=False).mean()
    rma_down = down.ewm(alpha=1 / 14, adjust=False).mean()
    rs = rma_up / rma_down
    rsi = (100 - (100 / (1 + rs))).iloc[-1]

    return Indicators(
        target_date=target_date.strftime("%Y/%m/%d"),
        soxx_close=float(latest),
        soxx_sma200=float(sma),
        soxx_kairi=float(kairi),
        rsi=float(rsi),
        shd=float(shd),
        soxl_close=float(close["SOXL"].iloc[-1]),
        soxl_open=float(open_["SOXL"].iloc[-1]),
    )


def validate_and_compute(close, open_, target_date):
    """指定した対象セッション target_date（date）に対する検査と指標計算。

    NG の場合は DataValidationError。対象日はデータの最終行から決めず、
    呼び出し側が独立に与えた値と一致することを確認する。
    """
    reasons = []
    target = pd.Timestamp(target_date).normalize()

    close = _normalize_index(close, "終値", reasons)
    open_ = _normalize_index(open_, "始値", reasons)
    if close is None or open_ is None:
        raise DataValidationError(reasons)

    for label, frame in (("終値", close), ("始値", open_)):
        missing = [t for t in TICKERS if t not in frame.columns]
        if missing:
            reasons.append(f"{label}: 銘柄列が不足しています ({', '.join(missing)})")
    if reasons:
        raise DataValidationError(reasons)

    if target not in close.index:
        reasons.append("終値: 指定した対象日の行がありません")
    if target not in open_.index:
        reasons.append("始値: 指定した対象日の行がありません")
    if reasons:
        raise DataValidationError(reasons)

    if close.index[-1] != target:
        reasons.append("終値: 最新行が指定した対象日と一致しません（古い/先の日付）")
    if open_.index[-1] != target:
        reasons.append("始値: 最新行が指定した対象日と一致しません（古い/先の日付）")
    if reasons:
        raise DataValidationError(reasons)

    # 対象日の元価格（4銘柄の終値、SOXLの始値）
    for t in TICKERS:
        if not _finite_positive(close[t].iloc[-1]):
            reasons.append(f"{t}: 対象日の終値が欠損または不正です")
    if not _finite_positive(open_["SOXL"].iloc[-1]):
        reasons.append("SOXL: 対象日の始値が欠損または不正です")

    # 履歴の妥当性。直近の窓が全て有限でなければ、古い日への後退や
    # NaN越しの持ち越しが起き得るため通さない。
    if len(close) < SMA_WINDOW:
        reasons.append(f"SOXX: 履歴不足（200日移動平均に{SMA_WINDOW}行必要、{len(close)}行）")
    else:
        window = close["SOXX"].iloc[-SMA_WINDOW:]
        if not all(_finite_positive(v) for v in window):
            reasons.append("SOXX: 直近200行に欠損または不正な終値があります")
    for t in ("SPY", "IEF"):
        if len(close) < SHD_LOOKBACK:
            reasons.append(f"{t}: 履歴不足（SHDに{SHD_LOOKBACK}行必要、{len(close)}行）")
        else:
            window = close[t].iloc[-SHD_LOOKBACK:]
            if not all(_finite_positive(v) for v in window):
                reasons.append(f"{t}: 直近{SHD_LOOKBACK}行に欠損または不正な終値があります")
    if reasons:
        raise DataValidationError(reasons)

    ind = compute_indicators(close, open_, target)
    for name in ("soxx_close", "soxx_sma200", "soxx_kairi", "rsi", "shd", "soxl_close", "soxl_open"):
        if not math.isfinite(getattr(ind, name)):
            reasons.append(f"指標が有限値になりません ({name})")
    if reasons:
        raise DataValidationError(reasons)
    return ind


def technical_conditions(ind):
    """保有に依存しない技術条件（従来の買い予備条件と同じ閾値）。"""
    trend = ind.soxx_close > ind.soxx_sma200
    shd_neg = ind.shd < 0
    rsi_ok = ind.rsi <= 55
    return {
        "trend": trend,
        "shd": shd_neg,
        "rsi": rsi_ok,
        "all": trend and shd_neg and rsi_ok,
    }
