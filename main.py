import yfinance as yf
import pandas as pd
import requests
import os

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
HAS_POSITION = str(os.environ.get("HAS_POSITION", "false")).strip().lower() == "true"

def check_conditions_and_notify():
    # データを少し多めに取得して欠損を防ぐ
    tickers =['SOXX', 'SPY', 'IEF']
    data = yf.download(tickers, period="2y")['Close']
    
    # 欠損値を前の日のデータで埋める
    data = data.ffill()
    
    # 指標の計算
    soxx_200sma = data['SOXX'].rolling(window=200).mean().iloc[-1]
    soxx_latest = data['SOXX'].iloc[-1]
    is_uptrend = soxx_latest > soxx_200sma

    # SHDの計算（最新がNaNなら一つ前を採用）
    spy_ret_series = data['SPY'].pct_change(periods=20)
    ief_ret_series = data['IEF'].pct_change(periods=20)
    shd_series = (spy_ret_series - ief_ret_series) * 100
    shd = shd_series.dropna().iloc[-1]
    
    delta = data['SOXX'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rma_up = up.ewm(alpha=1/14, adjust=False).mean()
    rma_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = rma_up / rma_down
    rsi_series = 100 - (100 / (1 + rs))
    latest_rsi = rsi_series.dropna().iloc[-1]

    print(f"状態: {'[保有中]' if HAS_POSITION else '[待機中]'} -> SHD: {shd:.2f}%, RSI: {latest_rsi:.2f}")

    message = None

    # 【待機中】買いサイン
    if not HAS_POSITION:
        if is_uptrend and shd < 0 and latest_rsi <= 55:
            message = (
                "@everyone\n"  # ← ここで通知を鳴らします
                "🟢 **【SOXL 買いシグナル 予備点灯】** 🟢\n"
                "指標の条件が揃いました！\n\n"
                f"📈 **SOXXトレンド**: OK (現在値 {soxx_latest:.2f} > 200SMA {soxx_200sma:.2f})\n"
                f"🛡️ **Safe Haven Demand**: OK ({shd:.2f}%)\n"
                f"📉 **SOXX RSI(14)**: OK ({latest_rsi:.2f})\n\n"
                "✅ **【最終手動確認】**\n"
                "F&G Indexが **30以下** か確認してください！\n"
                "https://edition.cnn.com/markets/fear-and-greed"
            )

    # 【保有中】売りサイン
    else:
        if shd >= 3.0 or latest_rsi >= 70:
            reason = "🚨 **強制脱出（市場過熱）**" if shd >= 3.0 else "💰 **通常利確（買われすぎ）**"
            message = (
                "@everyone\n"  # ← ここで通知を鳴らします
                f"🔴 **【SOXL 売りシグナル 点灯】** 🔴\n"
                f"利確・撤退のタイミングです！\n\n"
                f"**【理由】** {reason}\n"
                f"🛡️ **Safe Haven Demand**: {shd:.2f}%\n"
                f"📈 **SOXX RSI(14)**: {latest_rsi:.2f}\n"
                "\n✅ 売却したら「HAS_POSITION」を false に戻してください。"
            )

    if message:
        payload = {"content": message}
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    else:
        # テスト時以外は、条件に合わない時は何も送らない（通知を汚さないため）
        print("本日はサインなし。")

if __name__ == "__main__":
    check_conditions_and_notify()
