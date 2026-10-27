"""Text for the local preview: conditional NO_SELL / P20 display, ratios only, b* reference, summary.

Preview text only. Nothing here is sent anywhere. No shares, amounts, sale floor, order method or
sale recommendation is produced, and the user's own P20 / first-entry / re-entry status is never asserted.
"""
from decimal import ROUND_FLOOR, Decimal

from .engine import DayResult, ErrorResult, RuleStatus, RunClass
from .errors import InputError
from .fixture import PRICE_DEF_SOXL_CLOSE
from .tri import Tri

RULE_LABEL = {"EXFEAR": "極端恐怖", "NORMAL": "通常買い", "TREND": "トレンド参加"}
CLASS_LABEL = {
    RunClass.NO_SIGNAL: "合図なし",
    RunClass.WAITING_FG: "F&G観測待ち",
    RunClass.CONDITION_MET: "市場条件成立（確認済み）",
    RunClass.REFERENCE_UNCONFIRMED: "参考・未確認",
    RunClass.DATA_ERROR: "データ異常",
    RunClass.CONFLICT: "観測記録の衝突",
}
TRI_LABEL = {Tri.TRUE: "確認済みtrue", Tri.FALSE: "確認済みfalse", Tri.UNKNOWN: "不明"}
REASON_TEXT = {
    "armed_confirmed_false": "armedが確認済みfalse（消費済み）",
    "armed_confirmed_true": "armedは確認済みtrue",
    "armed_unknown": "armedは不明",
    "market_side_not_met": "市場側の条件が不成立",
    "market_side_met": "市場側の条件は成立",
    "not_a_rise_prev_normal_raw": "前日もnormal_raw成立で立上がりでない",
    "rise_confirmed": "前日normal_rawは確認済みfalse（立上がり）",
    "prev_normal_raw_unknown": "前日normal_rawは不明",
    "fg_below_25": "F&Gは25未満",
    "fg_not_below_25": "F&Gは25以上",
    "fg_in_25_30": "F&Gは25以上30未満の帯",
    "fg_not_in_25_30": "F&Gは25以上30未満の帯にない",
    "fg_at_least_30": "F&Gは30以上",
    "fg_below_30": "F&Gは30未満",
}

BSTAR_NOTE = (
    "費用込み1株平均原価がこの値以下ならP20のD価格条件（含み益20%以上、手数料なし）を満たします。"
    "売却下限・指値・売却推奨ではありません。保有を入力していないため、本人のP20成立は未判定です。"
)
FORBIDDEN_HINT = "株数・金額は出しません。売却推奨・注文方式は出しません。"


def bstar(d_close, definition):
    """b* = D close / 1.2, floored to the cent (Decimal). Only the raw split-adjusted close is accepted."""
    if definition != PRICE_DEF_SOXL_CLOSE:
        raise InputError("soxl_price_definition_unknown", "soxl_close")
    value = d_close if isinstance(d_close, Decimal) else Decimal(str(d_close))
    if not value.is_finite() or value <= 0:
        raise InputError("price_not_finite_positive", "soxl_close")
    return (value / Decimal("1.2")).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)


def _manifest_text(meta):
    items = meta.get("input_manifest") or []
    if not items:
        return ""
    return "、入力SHA256先頭12桁=" + "/".join(m["sha256"][:12] for m in items)


def _reasons(rule):
    return "、".join(REASON_TEXT.get(r, r) for r in rule.reasons)


def _rule_line(rule):
    label = RULE_LABEL[rule.name]
    if rule.status is RuleStatus.MET:
        return "  %s: 条件成立（確認済み）→ 利用可能資金の%d%%（比率のみ）" % (label, rule.ratio)
    if rule.status is RuleStatus.NOT_MET:
        return "  %s: 不成立（%s）" % (label, _reasons(rule))
    if rule.status is RuleStatus.UNCONFIRMED:
        return "  %s: 条件に該当するが参考・未確認（%s）" % (label, _reasons(rule))
    extra = "。成立してもarmed等が不明のため参考・未確認" if rule.may_be_unconfirmed else ""
    return "  %s: F&G次第（%s%s）" % (label, _reasons(rule), extra)


def _branch_lines(result):
    ex, nm, tr = (result.rules[k] for k in ("EXFEAR", "NORMAL", "TREND"))

    def text(rule, name):
        if rule.status is RuleStatus.NOT_MET:
            return "%sは不成立" % name
        tail = "（参考・未確認）" if rule.may_be_unconfirmed else ""
        return "%sの条件成立%s → 利用可能資金の%d%%（比率のみ）" % (name, tail, rule.ratio)

    return [
        "  F&Gの値による分岐（目視した値で手元判定できます。再通知はありません）",
        "    25未満       → " + text(ex, "極端恐怖"),
        "    25以上30未満 → " + text(nm, "通常買い"),
        "    30以上       → " + text(tr, "トレンド参加") if tr.status is not RuleStatus.NOT_MET
        else "    30以上       → トレンド参加は不成立（RSIの55上抜けまたはSMA200条件を満たさない）",
    ]


def _profile_lines(result):
    met = [r for r in result.rules.values() if r.status in (RuleStatus.MET, RuleStatus.UNCONFIRMED)]
    lines = ["プロファイル別（案U: 保有・原価・現金・余力は入力していません）"]
    if not met:
        lines.append("  条件が成立した場合の口座条件は、手元で確認してください。")
        return lines
    rule = met[0]
    tag = "" if rule.status is RuleStatus.MET else "（参考・未確認）"
    if rule.name in ("EXFEAR", "NORMAL"):
        lines.append("  NO_SELL I25／P20_ONLY I25/R25 とも共通%s: 利用可能資金の100%%（比率のみ）" % tag)
        lines.append("  100%は保有を全部買い換える意味ではなく、本人が確認した利用可能資金の条件付き投入割合です。"
                     "注文拘束・未受渡・MMF利用可否は確定しません。")
    else:
        lines.append("  NO_SELL I25%s: 本人が0株の場合のみ、利用可能資金の25%%（比率のみ）。再参加は該当しません。" % tag)
        lines.append("  P20_ONLY I25/R25%s: 初回（0株・売却歴なし）か全売却後の再参加か、どちらでもないかは手元確認。25%%" % tag)
        if result.wait_session_date:
            wait = ("全売却の約定セッションS・合図D・手動購入next(D)を区別します。再参加はD−S≧3（最短でS+4に購入）。"
                    "今回のD=%s では、Sが%s以前ならD−S≧3です。購入予定はnext(D)=%s の寄付き（目安）。"
                    "本人のSは未入力のため、待機の成立は未判定です。"
                    % (result.d, result.wait_session_date, result.next_session_date))
        else:
            wait = "セッション列が短く、待機の目安日を算出できません。本人のSは未入力のため待機の成立は未判定です。"
        lines.append("  待機の表示: " + wait)
    lines.append("  P20保有があり本人にP20が成立し得る場合は、売却側の手元確認が先です（同日の売買両建ての推奨ではありません）。")
    lines.append("  手元確認: 保有株数／全売却歴／利用可能USD／未約定注文")
    return lines


def render_message(result):
    if isinstance(result, ErrorResult):
        return "\n".join([
            "【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=%s ／実行区分: %s"
            % (result.d, CLASS_LABEL[result.run_class]),
            "  コード: %s%s" % (result.code, "" if result.field is None else "（%s）" % result.field),
            "  条件未達ではありません。古い日付に落とした判定や前日補完は行っていません。市場状態は変更していません。",
        ])
    meta = result.series_meta
    lines = [
        "【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=%s ／実行区分: %s"
        % (result.d, CLASS_LABEL[result.run_class]),
        "データ: 検査済み（SOXX価格定義=%s、前史 %s〜%s、%d行%s）"
        % (meta.get("price_definition"), meta.get("first_date"), meta.get("last_date"), meta.get("rows"),
           _manifest_text(meta)),
        "市場側（F&G以外の条件を含む判定）",
    ]
    lines += [_rule_line(result.rules[k]) for k in ("EXFEAR", "NORMAL", "TREND")]
    if result.decision is None:
        lines.append("F&G現在値（目視）: 未記録 → 購入条件は未確定です。")
        if result.run_class is RunClass.WAITING_FG:
            lines += _branch_lines(result)
    else:
        lines.append("F&G現在値（目視）: %s（decision、observed_at=%s、対象D=%s）"
                     % (("%g" % result.decision.value), result.decision.observed_at.isoformat(), result.d))
    lines.append("市場状態: armed=%s、連続数（確認済み観測）=%d、前日normal_raw=%s"
                 % (TRI_LABEL[result.effective_armed], result.effective_streak,
                    TRI_LABEL[result.effective_prev_normal_raw]))
    if result.gap:
        lines.append("  前日までの観測が途切れたため、armedを不明・連続数を0にしました（F&G=0という意味ではありません）。")
    lines += _profile_lines(result)
    if result.soxl_close is not None:
        lines.append("P20の原価目安 b*=%s（SOXL D終値%s÷1.2、%s、セント未満切り捨て）"
                     % (bstar(result.soxl_close, result.series_meta.get("soxl_close_definition")),
                        result.soxl_close, PRICE_DEF_SOXL_CLOSE))
        lines.append("  " + BSTAR_NOTE)
        lines.append("  b*と原価の差が0.01未満の境界付近は、表示だけで断定せず n×D終値÷B−1≧0.20 を直接確認してください。")
    else:
        lines.append("P20の原価目安 b*: SOXL D終値が入力にないため表示しません。")
    lines.append(FORBIDDEN_HINT)
    return "\n".join(lines)


def render_summary(result):
    lines = ["――完了サマリ（ローカルプレビュー・実送信なし）――"]
    if isinstance(result, ErrorResult):
        lines += [
            "実行区分: %s" % CLASS_LABEL[result.run_class],
            "対象D: %s" % result.d,
            "データ検査: 異常（コード=%s）" % result.code,
            "状態更新: なし（既存の市場状態は変更していません）",
            "記録・通知: 本コアは保存・送信しません（Sheets/Discord未接続）",
            "終了コード: %d" % result.exit_code,
        ]
        return "\n".join(lines)
    if result.decision is None:
        update = "保留（decision観測が未記録のため前日までの状態を維持）"
    elif result.state_updated:
        update = "次状態候補あり（as_of_d=%s。保存はしません）" % result.next_state.as_of_d
    else:
        update = "変更なし（同じDの再実行。保存済みの基点と固定decisionから再計算）"
    lines += [
        "実行区分: %s" % CLASS_LABEL[result.run_class],
        "対象D: %s（確定: %s、次回寄付き: %s）" % (result.d, result.close_at.isoformat(), result.next_open_at.isoformat()),
        "データ検査: 正常",
        "F&G: %s" % ("decision記録あり" if result.decision else "未記録"),
        "状態更新: " + update,
        "記録・通知: 本コアは保存・送信しません（Sheets/Discord未接続）",
        "終了コード: %d" % result.exit_code,
    ]
    return "\n".join(lines)


def render(result):
    return render_message(result) + "\n\n" + render_summary(result)
