"""通知の送信と本文組み立て。ログには非秘密の情報だけを出す。"""
import requests

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15

SENT_OK = "ok"
SENT_HTTP_ERROR = "http_error"
SENT_UNKNOWN = "unknown"


def post_message(url, content, post=requests.post):
    """1回だけ送信する。再送・再帰はしない。

    戻り値: (結果, HTTPステータスまたはNone)。
    URL・応答本文・例外メッセージはログに出さない（例外は型名のみ）。
    """
    try:
        resp = post(url, json={"content": content}, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    except Exception as exc:  # タイムアウト・接続断など。結果不明
        print(f"通知: 配信不明（{type(exc).__name__}）。自動再送はしません。")
        return SENT_UNKNOWN, None
    status = getattr(resp, "status_code", None)
    if isinstance(status, int) and 200 <= status < 300:
        print(f"通知: 送信成功（HTTP {status}）。")
        return SENT_OK, status
    print(f"通知: HTTP失敗（HTTP {status}）。自動再送はしません。")
    return SENT_HTTP_ERROR, status


def _mark(ok):
    return "満たす" if ok else "満たさない"


def build_summary(ind, cond, sheets_state):
    """正常／部分失敗の実行サマリ。sheets_state: ok / disabled / failed。"""
    if sheets_state == "failed":
        head = "⚠️ **【SOXL 実行サマリ：部分失敗（記録失敗）】**"
    else:
        head = "✅ **【SOXL 実行サマリ】**"
    sheets_text = {
        "ok": "成功",
        "disabled": "無効設定（明示的に無効）",
        "failed": "失敗（Sheetsへの記録は完了していません）",
    }[sheets_state]
    verdict = "技術条件3つすべて成立" if cond["all"] else "技術条件は未達"
    lines = [
        head,
        f"対象取引日: {ind.target_date}（指定）",
        "データ検査: OK（SOXX/SOXL/SPY/IEFの元価格・履歴を確認）",
        f"・SOXX終値 {ind.soxx_close:.2f} / 200SMA {ind.soxx_sma200:.2f}: {_mark(cond['trend'])}（SOXX>200SMA）",
        f"・SHD {ind.shd:.2f}%: {_mark(cond['shd'])}（SHD<0）",
        f"・RSI {ind.rsi:.2f}: {_mark(cond['rsi'])}（RSI<=55）",
        f"判定: {verdict}",
        f"Sheets記録: {sheets_text}",
        "F&G: 目視未確認（CNN Fear & Greedを確認してください）",
        "※購入推奨・購入可否の確定ではありません。保有状態は確認していません。",
    ]
    return "\n".join(lines)


def build_error(reasons, stage):
    """運用エラー通知。reasons は非秘密の固定文言のみを渡す。"""
    body = "\n".join(f"・{r}" for r in reasons)
    return (
        "🚫 **【SOXL 運用エラー】**\n"
        f"段階: {stage}\n"
        "売買の判定とSheetsの価格行追記は実行していません（条件未達ではありません）。\n"
        f"{body}\n"
        "F&G: 目視未確認"
    )
