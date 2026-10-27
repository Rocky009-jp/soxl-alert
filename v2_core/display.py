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
ERROR_HINT = {
    "decision_conflict": [
        "decisionは1日1件だけです。追加の観測は observation_role を supplemental にして別の行に記録してください"
        "（判断は差し替わりません）。",
        "decisionの内容の訂正は、追加観測とは別の手順です。この核は自動で差し替えません（訂正の手順は未整備）。",
        "衝突を残したまま次のセッションを処理しようとすると、中間セッション未処理（intermediate_session_unprocessed）で"
        "停止し、状態は変わりません。欠測扱いにはなりません。",
    ],
    "record_id_conflict": [
        "同じrecord_idで内容が違います。追加の観測は新しいrecord_idのsupplementalで記録してください。",
        "既存の記録の訂正は、追加観測とは別の手順です。この核は自動で差し替えません。",
        "衝突した記録が入力に残る間は、他の日を処理してもrecord_id_conflictで停止し、状態は変わりません。",
    ],
    "decision_conflict_with_applied": [
        "適用済みのdecisionと内容が違います。適用済みの状態は変更していません。",
        "追加の観測ならsupplementalで別の行に。適用済みdecisionの訂正は、追加観測とは別の明示手順が必要で、"
        "この核は自動で差し替えません（訂正の手順は未整備）。",
        "次のセッションは、適用済みの状態から通常どおり処理できます。",
    ],
    "target_mismatch": [
        "このセッションの判断窓（確定後〜次回寄付き前）にあるdecisionの対象日(target_us_session_date)が、"
        "処理するDと違います。対象日を直してください（日本時間の日付ではなく、米国セッションの日付）。",
    ],
    "intermediate_session_unprocessed": [
        "基点より後で、このDより前のセッションに有効なdecisionが入力にあります。先にそのセッションから順に処理してください。"
        "自動で過去は処理しません。欠測としても扱っていません。",
    ],
}
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


def _trend_lines(result, tag, lead):
    lines = ["  %sNO_SELL I25%s: 本人が0株の場合のみ、利用可能資金の25%%（比率のみ）。再参加は該当しません。" % (lead, tag)]
    lines.append("  %sP20_ONLY I25/R25%s: 初回（0株・売却歴なし）か全売却後の再参加か、どちらでもないかは手元確認。25%%"
                 % (lead, tag))
    if result.wait_session_date:
        wait = ("全売却の約定セッションS・合図D・手動購入next(D)を区別します。再参加はD−S≧3（最短でS+4に購入）。"
                "今回のD=%s では、Sが%s以前ならD−S≧3です。購入予定はnext(D)=%s の寄付き（目安）。"
                "本人のSは未入力のため、待機の成立は未判定です。"
                % (result.d, result.wait_session_date, result.next_session_date))
    else:
        wait = "セッション列が短く、待機の目安日を算出できません。本人のSは未入力のため待機の成立は未判定です。"
    lines.append("  待機の表示: " + wait)
    return lines


def _profile_lines(result):
    met = [r for r in result.rules.values() if r.status in (RuleStatus.MET, RuleStatus.UNCONFIRMED)]
    lines = ["プロファイル別（案U: 保有・原価・現金・余力は入力していません）"]
    pending_trend = result.rules["TREND"].status is RuleStatus.PENDING_FG
    if not met and not pending_trend:
        lines.append("  条件が成立した場合の口座条件は、手元で確認してください。")
        return lines
    if not met:
        # F&G not observed yet, but the trend rule can still fire: show what the user must check by hand
        lines.append("  F&Gが30以上でトレンド参加の条件が成立する場合（観測後に手元で判断。再通知はありません）:")
        lines += _trend_lines(result, "", "")
    else:
        rule = met[0]
        tag = "" if rule.status is RuleStatus.MET else "（参考・未確認）"
        if rule.name in ("EXFEAR", "NORMAL"):
            lines.append("  NO_SELL I25／P20_ONLY I25/R25 とも共通%s: 利用可能資金の100%%（比率のみ）" % tag)
            lines.append("  100%は保有を全部買い換える意味ではなく、本人が確認した利用可能資金の条件付き投入割合です。"
                         "注文拘束・未受渡・MMF利用可否は確定しません。")
        else:
            lines += _trend_lines(result, tag, "")
    lines.append("  P20保有があり本人にP20が成立し得る場合は、売却側の手元確認が先です（同日の売買両建ての推奨ではありません）。")
    lines.append("  手元確認: 保有株数／全売却歴／利用可能USD／未約定注文")
    return lines


def render_message(result):
    if isinstance(result, ErrorResult):
        out = [
            "【SOXL日次・ローカルプレビュー（実送信なし）】 対象D=%s ／実行区分: %s"
            % (result.d, CLASS_LABEL[result.run_class]),
            "  コード: %s%s" % (result.code, "" if result.field is None else "（%s）" % result.field),
            "  条件未達ではありません。古い日付に落とした判定や前日補完は行っていません。市場状態は変更していません。",
        ]
        if result.detail:
            out.append("  先に処理するセッション: %s" % result.detail)
        out += ["  " + t for t in ERROR_HINT.get(result.code, [])]
        return "\n".join(out)
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
        lines.append("  ※この日のdecision観測を記録しないと（合図なしの日も）、次のセッションを処理するときにarmedが不明、"
                     "連続数が0になります。毎日記録してください。")
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
        check = ("観測記録の検査: 衝突（価格データの異常ではありません。コード=%s）" % result.code
                 if result.run_class is RunClass.CONFLICT else "データ検査: 異常（コード=%s）" % result.code)
        lines += [
            "実行区分: %s" % CLASS_LABEL[result.run_class],
            "対象D: %s" % result.d,
            check,
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
