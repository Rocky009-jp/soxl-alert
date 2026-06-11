import yfinance as yf
import pandas as pd
import requests
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 環境変数（GitHub Secrets）から情報を取得
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GCP_CREDENTIALS_JSON = os.environ.get("GCP_CREDENTIALS")

def main():
    print("データ取得を開始します...")
    
    # --- 1. データの取得と計算 ---
    # 200日線を計算するため1年前から取得
    tickers = ['SOXX', 'SOXL', 'SPY', 'IEF']
    data = yf.download(tickers, period="1y")

    # データ構造の平坦化処理（yfinanceの仕様変更対応）
    close_data = data['Close']
    open_data = data['Open']
    close_data.index = close_data.index.tz_localize(None)
    open_data.index = open_data.index.tz_localize(None)

    # 各種指標の計算
    soxx_200sma = close_data['SOXX'].rolling(window=200).mean().iloc[-1]
    soxx_latest = close_data['SOXX'].iloc[-1]
    soxx_kairi = ((soxx_latest - soxx_200sma) / soxx_200sma) * 100

    spy_ret = close_data['SPY'].pct_change(periods=20).iloc[-1]
    ief_ret = close_data['IEF'].pct_change(periods=20).iloc[-1]
    shd = (spy_ret - ief_ret) * 100

    delta = close_data['SOXX'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rma_up = up.ewm(alpha=1/14, adjust=False).mean()
    rma_down = down.ewm(alpha=1/14, adjust=False).mean()
    rs = rma_up / rma_down
    soxx_rsi = 100 - (100 / (1 + rs))
    latest_rsi = soxx_rsi.iloc[-1]

    soxl_latest = close_data['SOXL'].iloc[-1]
    # 翌日の始値は「今日」の時点ではまだ不明なので、今日の始値を参考値として取得
    soxl_today_open = open_data['SOXL'].iloc[-1] 
    
    today_str = close_data.index[-1].strftime('%Y/%m/%d')
    print(f"計算完了: 日付 {today_str}, SOXX {soxx_latest:.2f}, 乖離率 {soxx_kairi:.2f}%, RSI {latest_rsi:.2f}, SHD {shd:.2f}%")

    # --- 2. Googleスプレッドシートへの書き込み ---
    if GCP_CREDENTIALS_JSON and SPREADSHEET_ID:
        try:
            # 認証情報の読み込み
            creds_dict = json.loads(GCP_CREDENTIALS_JSON)
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # シートを開いてデータを追加
            sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Data")
            row_data = [
                today_str,
                round(soxx_latest, 2),
                round(soxx_200sma, 2),
                round(soxx_kairi, 2),
                round(latest_rsi, 2),
                round(shd, 2),
                round(soxl_latest, 2),
                round(soxl_today_open, 2)
            ]
            sheet.append_row(row_data)
            print("スプレッドシートへの書き込みが完了しました。")
        except Exception as e:
            print(f"スプレッドシート書き込みエラー: {e}")

    # --- 3. 買いシグナル判定とDiscord通知 ---
    # 条件: 200日線上 ＆ 乖離率20%未満 ＆ SHD<0 ＆ RSI<=55
    if soxx_latest > soxx_200sma and soxx_kairi < 20 and shd < 0 and latest_rsi <= 55:
        if DISCORD_WEBHOOK_URL:
            message = (
                "🚨 **【SOXL 買いシグナル 予備点灯】** 🚨\n"
                f"日付: {today_str}\n"
                f"・乖離率: {soxx_kairi:.2f}% (安全圏)\n"
                f"・RSI: {latest_rsi:.2f}\n"
                f"・SHD: {shd:.2f}%\n\n"
                "✅ CNN Fear & Greed Indexを確認し、**【30以下】**なら買いタイミングです！"
            )
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
            print("Discordへ通知を送信しました。")
    else:
        print("買い条件未達のため、通知は送信しません。")

if __name__ == "__main__":
    main()
