import yfinance as yf
import pandas as pd
import requests
import os

# GitHubの設定からURLとポジションの有無を読み込む
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# HAS_POSITIONが "true" なら保有中(True)、それ以外なら待機中(False)
HAS_POSITION = str(os.environ.get("HAS_POSITION", "false")).strip().lower() == "true"

def check_conditions_and_notify():
    # データの取得
    tickers =['SOXX', 'SPY', 'IEF']
    data = yf.download(tickers, period="1y")['Close']
    
    # 各種指標の計算
    soxx_200sma = data['SOXX'].rolling(window=200).mean().iloc[-1]
    soxx_latest = data['SOXX'].iloc[-1]
    is_uptrend = soxx_latest > soxx_200sma

    spy_ret = data['SPY'].pct_change(periods=20).iloc[-1]
    ief_ret = data['IEF'].pct_change(periods=20).iloc[-1]
    shd = (spy_ret - ief_ret) * 100
    
    delta = data['SOXX'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rma_up = up.ewm(alpha=1/14, adjust=False).mean()
    rma_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = rma_up / rma_down
    rsi = 100 - (100 / (1 + rs))
    latest_rsi = rsi.iloc[-1]

    print(f"状態: {'[保有中]' if HAS_POSITION else '[待機中]'} -> SOXX: {soxx_latest:.2f}(200SMA:{soxx_200sma:.2f}), SHD: {shd:.2f}%, RSI: {latest_rsi:.2f}")

    message = None

    # ==========================================
    # 【待機中】買いサインの監視
    # ==========================================
    if not HAS_POSITION:
        if is_uptrend and shd < 0 and latest_rsi <= 55:
            message = (
                "🟢 **【SOXL 買いシグナル 予備点灯】** 🟢\n"
                "待機資金（MMF）を動かすチャンスです！最後の確認を行ってください。\n\n"
                f"📈 **SOXXトレンド**: OK (現在値 {soxx_latest:.2f} > 200SMA {soxx_200sma:.2f})\n"
                f"🛡️ **Safe Haven Demand**: OK ({shd:.2f}%)\n"
                f"📉 **SOXX RSI(14)**: OK ({latest_rsi:.2f})\n\n"
                "✅ **【最終手動確認】**\n"
                "CNN『Fear & Greed Index』を見て、**【30以下】**であればSOXLを購入し、\n"
                "GitHubの「HAS_POSITION」を true に変更してください！\n"
                "https://edition.cnn.com/markets/fear-and-greed"
            )

    # ==========================================
    # 【保有中】売りサインの監視
    # ==========================================
    else:
        # ①強制脱出（SHD >= 3.0）または ②通常利確（RSI >= 70）
        if shd >= 3.0 or latest_rsi >= 70:
            reason = "🚨 **強制脱出（市場過熱）**" if shd >= 3.0 else "💰 **通常利確（半導体買われすぎ）**"
            message = (
                f"🔴 **【SOXL 売りシグナル 点灯】** 🔴\n"
                f"利確（または撤退）のタイミングです！\n\n"
                f"**【理由】** {reason}\n"
                f"🛡️ **Safe Haven Demand**: {shd:.2f}%\n"
                f"📈 **SOXX RSI(14)**: {latest_rsi:.2f}\n\n"
                "💡 **【Extreme Fearでエントリーした場合のリマインド】**\n"
                "F&G Indexが『75以上』になるまで利益を引っ張る戦略もあります。\n\n"
                "✅ 売却が完了したら、資金をMMFに戻し、\n"
                "GitHubの「HAS_POSITION」を false に戻してください！"
            )

    # 条件に合致してメッセージが作られていればDiscordに送信
    if message:
        payload = {"content": message}
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
        print("Discordへ通知を送信しました。")
    else:
        print("本日はサイン点灯なし。")

if __name__ == "__main__":
    check_conditions_and_notify()
