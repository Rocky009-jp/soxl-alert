import json
import os
import sys
from datetime import date

import soxl_checks
import soxl_notify

# 環境変数（GitHub Secrets / ワークフロー）。値は表示しない。
ENV_WEBHOOK = "DISCORD_WEBHOOK_URL"
ENV_SPREADSHEET = "SPREADSHEET_ID"
ENV_GCP = "GCP_CREDENTIALS"
ENV_SHEETS_ENABLED = "SHEETS_ENABLED"  # "true" / "false" を明示
ENV_TARGET = "TARGET_SESSION_DATE"  # YYYY-MM-DD（対象セッションを独立に指定）


class ConfigError(Exception):
    """設定不備。reasons は設定名のみを含む非秘密の文言。"""

    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)


def read_config(env):
    reasons = []
    webhook = env.get(ENV_WEBHOOK) or ""
    if not webhook:
        reasons.append(f"必須設定 {ENV_WEBHOOK} が未設定です")

    target = None
    raw_target = env.get(ENV_TARGET) or ""
    if not raw_target:
        reasons.append(f"必須設定 {ENV_TARGET}（対象セッション日 YYYY-MM-DD）が未設定です")
    else:
        try:
            target = date.fromisoformat(raw_target)
        except ValueError:
            reasons.append(f"{ENV_TARGET} の形式が不正です（YYYY-MM-DD）")

    flag = (env.get(ENV_SHEETS_ENABLED) or "").strip().lower()
    sheets_enabled = None
    if flag == "true":
        sheets_enabled = True
        if not env.get(ENV_GCP):
            reasons.append(f"Sheets有効なのに {ENV_GCP} が未設定です")
        if not env.get(ENV_SPREADSHEET):
            reasons.append(f"Sheets有効なのに {ENV_SPREADSHEET} が未設定です")
    elif flag == "false":
        sheets_enabled = False
    else:
        reasons.append(f"{ENV_SHEETS_ENABLED} は true / false のどちらかを明示してください")

    # 検証済みの対象日だけを表示用ラベルにする。不正な生値は載せない。
    target_label = target.strftime("%Y/%m/%d") if target else "対象日未確定"
    cfg = {
        "target_label": target_label,
        "webhook": webhook,
        "target": target,
        "sheets_enabled": sheets_enabled,
        "gcp": env.get(ENV_GCP) or "",
        "spreadsheet_id": env.get(ENV_SPREADSHEET) or "",
    }
    return cfg, reasons


def fetch_prices():
    """従来どおりの取得（実依存は yfinance）。ネットワーク境界。"""
    import yfinance as yf

    data = yf.download(["SOXX", "SOXL", "SPY", "IEF"], period="1y")
    close = data["Close"]
    open_ = data["Open"]
    close.index = close.index.tz_localize(None)
    open_.index = open_.index.tz_localize(None)
    return close, open_


def append_sheet_row(creds_json, spreadsheet_id, row):
    """Sheets書込。書込境界（実アクセスはここだけ）。"""
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    creds_dict = json.loads(creds_json)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(spreadsheet_id).worksheet("Data")
    sheet.append_row(row)


def _notify(cfg, content, post):
    result, _status = soxl_notify.post_message(
        cfg["webhook"], content, post=post, target_label=cfg["target_label"]
    )
    return result


def run(env=None, fetch=None, write_row=None, post=None):
    """実行本体。戻り値が終了コード。境界（取得・書込・送信）は差し替え可能。"""
    env = os.environ if env is None else env
    fetch = fetch or fetch_prices
    write_row = write_row or append_sheet_row
    post = post or soxl_notify.requests.post

    cfg, config_errors = read_config(env)
    if config_errors:
        for r in config_errors:
            print(f"設定エラー: {r}")
        if cfg["webhook"]:
            _notify(cfg, soxl_notify.build_error(config_errors, "設定確認", cfg["target_label"]), post)
        print("終了コード: 1（設定エラー）")
        return 1

    print("データ取得を開始します...")
    try:
        close, open_ = fetch()
    except Exception as exc:  # 生例外メッセージは出さない
        reasons = [f"データ取得に失敗しました（{type(exc).__name__}）"]
        print(f"運用エラー: {reasons[0]}")
        _notify(cfg, soxl_notify.build_error(reasons, "データ取得", cfg["target_label"]), post)
        print("終了コード: 1（取得失敗）")
        return 1

    try:
        ind = soxl_checks.validate_and_compute(close, open_, cfg["target"])
    except soxl_checks.DataValidationError as exc:
        for r in exc.reasons:
            print(f"運用エラー: {r}")
        _notify(cfg, soxl_notify.build_error(exc.reasons, "データ検査", cfg["target_label"]), post)
        print("終了コード: 1（データ検査NG）")
        return 1
    except Exception as exc:
        reasons = [f"検査中に想定外の失敗が発生しました（{type(exc).__name__}）"]
        print(f"運用エラー: {reasons[0]}")
        _notify(cfg, soxl_notify.build_error(reasons, "データ検査", cfg["target_label"]), post)
        print("終了コード: 1（検査失敗）")
        return 1

    print(
        f"計算完了: 日付 {ind.target_date}, SOXX {ind.soxx_close:.2f}, "
        f"乖離率 {ind.soxx_kairi:.2f}%, RSI {ind.rsi:.2f}, SHD {ind.shd:.2f}%"
    )
    cond = soxl_checks.technical_conditions(ind)

    if cfg["sheets_enabled"]:
        row = [
            ind.target_date,
            round(ind.soxx_close, 2),
            round(ind.soxx_sma200, 2),
            round(ind.soxx_kairi, 2),
            round(ind.rsi, 2),
            round(ind.shd, 2),
            round(ind.soxl_close, 2),
            round(ind.soxl_open, 2),
        ]
        try:
            write_row(cfg["gcp"], cfg["spreadsheet_id"], row)
            sheets_state = "ok"
            print("スプレッドシートへの書き込みが完了しました。")
        except Exception as exc:  # 生例外・認証情報は出さない
            sheets_state = "failed"
            print(f"スプレッドシート書き込みエラー（{type(exc).__name__}）")
    else:
        sheets_state = "disabled"
        print("スプレッドシートへの書き込みは明示的に無効設定のためスキップしました。")

    notified = _notify(cfg, soxl_notify.build_summary(ind, cond, sheets_state), post)
    notify_ok = notified == soxl_notify.SENT_OK

    if sheets_state == "failed":
        print("終了コード: 1（部分失敗: 記録失敗）")
        return 1
    if not notify_ok:
        label = "通知HTTP失敗" if notified == soxl_notify.SENT_HTTP_ERROR else "配信不明"
        print(f"終了コード: 1（{label}）")
        return 1
    print("終了コード: 0")
    return 0


def main():
    return run()


if __name__ == "__main__":
    sys.exit(main())
