import yfinance as yf
import pandas as pd
import requests
import os

# GitHubのSecretからDiscordのURLを読み込む
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def check_conditions_and_notify():
    # 約1年分のデータを取得（200日移動平均線を計算するため）
    tickers = ['SOXX', 'SPY', 'IEF']
    data = yf.download(tickers, period="1y")['Close']
    
    # 1. 200日移動平均線の計算と判定
    soxx_200sma = data['SOXX'].rolling(window=200).mean().iloc[-1]
    soxx_latest = data['SOXX'].iloc[-1]
    is_uptrend = soxx_latest > soxx_200sma

    # 2. Safe Haven Demand (SHD) の計算
    spy_ret = data['SPY'].pct_change(periods=20).iloc[-1]
    ief_ret = data['IEF'].pct_change(periods=20).iloc[-1]
    shd = (spy_ret - ief_ret) * 100
    
    # 3. SOXXのRSI(14)の計算
    delta = data['SOXX'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rma_up = up.ewm(alpha=1/14, adjust=False).mean()
    rma_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = rma_up / rma_down
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = rsi.iloc[-1]

    print(f"現在値確認 -> SOXX: {soxx_latest:.2f} (200SMA: {soxx_200sma:.2f}), SHD: {shd:.2f}%, RSI: {latest_rsi:.2f}")

    # ★すべての条件を判定（トレンド上 ＆ SHD<0 ＆ RSI<=55）
    if is_uptrend and shd < 0 and latest_rsi <= 55:
        message = (
            "🚨 **【SOXL 買いシグナル 予備点灯】** 🚨\n"
            "指標の条件が揃いました！最後の確認を行ってください。\n\n"
            f"📈 **SOXXトレンド**: OK (現在値 {soxx_latest:.2f} > 200SMA {soxx_200sma:.2f})\n"
            f"🛡️ **Safe Haven Demand**: OK ({shd:.2f}%)\n"
            f"📉 **SOXX RSI(14)**: OK ({latest_rsi:.2f})\n\n"
            "✅ **【最終手動確認】**\n"
            "以下のリンクから『Fear & Greed Index』を見て、**【30以下】**であればMMFを解約してSOXLを買ってください！\n"
            "https://edition.cnn.com/markets/fear-and-greed"
        )
        
        # Discordへ通知を送信
        payload = {"content": message}
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print("条件達成！Discordへ通知を送信しました。")
    else:
        print("条件未達のため、本日は通知しません。ゆっくりMMFの金利を楽しみましょう。")

if __name__ == "__main__":
    check_conditions_and_notify()
