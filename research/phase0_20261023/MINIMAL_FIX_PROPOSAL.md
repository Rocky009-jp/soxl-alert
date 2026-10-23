# 最小修正の具体案（未適用）

対象はmain.py `7731ef0`。これはレビュー用の差分案であり、適用・本番送信の承認を得たものではない。戦略基準は変更しない。データ不備時の売買通知を抑止し、失敗の可視性を改善する。

## A：計算より前にデータを検査

`yf.download` の直後、`close_data` の計算前に、少なくとも以下を検査する。

- DataFrameが空でないこと、Close/Openと必要な銘柄列があること。
- 最後の対象行に必要な4銘柄Close・SOXL Openがそろい、正の有限値であること。
- SOXXのSMAに使う直近200本、RSIに必要な履歴、SHDの共通21観測が有効であること。対象日・列ごとの最終有効日を記録する。
- 値が欠けていれば `DATA_INVALID` として非0終了し、売買候補・シート価格行は作らない。情報不足を通常の「条件未達」と表示しない。

レビュー用コード例（この関数だけで日付鮮度や全履歴の検査が完了するわけではない）：

```python
def require_latest_prices(data, tickers):
    if data.empty:
        raise RuntimeError("DATA_INVALID: empty download")
    try:
        close = data["Close"].loc[:, tickers]
        soxl_open = data["Open"]["SOXL"]
    except KeyError:
        raise RuntimeError("DATA_INVALID: required columns missing") from None
    latest = {name: close[name].iloc[-1] for name in tickers}
    latest["SOXL Open"] = soxl_open.iloc[-1]
    invalid = [name for name, value in latest.items()
               if not math.isfinite(float(value)) or float(value) <= 0]
    if invalid:
        raise RuntimeError("DATA_INVALID: latest missing/invalid: " + ",".join(invalid))
    return close, soxl_open
```

値の型が数値でないケース、日付索引の重複・未整列なども実装時の確認に含める。取得元の構造を根拠なく決め打ちしない。

## B：全指標の検査を判定前へ移す

シート書き込みの内部にある有限性検査を、共通の計算検証として判定前に置く。価格・SMA・RSI・SHD・日付のすべてが有効でなければ `INDICATOR_INVALID` とする。シート連携を無効にしても検査を省略しない。

SHDだけ古い日付になっている場合も判定しない。完全な最終行が古い場合を検知するため、工程2で定義した期待取引日と照合する。初回修正で取引カレンダー全体を実装しない場合は、対象取引日を明示入力する診断用途に限定するか、鮮度未保証であることを明記し、本番復旧完了とはしない。

## C：Discordの失敗を成功表示しない

```python
def send_discord_message(content):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("NOTIFY_CONFIG_MISSING")
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            params={"wait": "true"},
            json={"content": content},
            timeout=(5, 15),
        )
        response.raise_for_status()
    except requests.RequestException as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        print(f"event=NOTIFY_FAILED http_status={status if status is not None else 'none'}")
        # 非秘密ステータスだけを記録。URL・本文・元例外は出さない。
        raise RuntimeError("NOTIFY_FAILED") from None
    if response.status_code != 200:
        print(f"event=NOTIFY_UNCONFIRMED http_status={response.status_code}")
        raise RuntimeError("NOTIFY_UNCONFIRMED")
    try:
        message_id = response.json().get("id")
    except (ValueError, AttributeError):
        message_id = None
    if not message_id:
        raise RuntimeError("NOTIFY_UNCONFIRMED")
    print("Discord側のメッセージ作成応答を確認しました。")
```

この例は応答の確認まで。接続タイムアウト後など、Discord側では作成済みで応答を受け取れない状態もあるため、自動再送で二重通知しない設計を別に検討する。429の即時無制限再送は入れない。読了を保証する表現はしない。

## D：保存失敗と成功の区別

Sheets連携が有効な構成では、書き込み失敗を記録の成功として扱わない。売買候補の通知を継続するか、部分成功として非0終了するかは仕様化する。シートで失敗したためDiscordまで停止する変更を暗黙に行わない。全体の無条件再実行は、通知済み・記録済みを重複させるので先に状態保存方針を決める。

## 初回修正の受入条件

1. 末尾欠損、空データ、履歴不足、日付不一致では売買通知なし・理由と失敗終了が確認できる。
2. HTTP200＋message idの場合だけ確認済み表示。404／429・タイムアウト・無効応答は失敗として分かり、秘密URLがログに出ない。
3. 完全な固定データでは技術指標・条件判定の差を照合する。ただし旧「全額売却」文言の維持を受入条件にはしない。R-02の暫定仕様の採否を明示し、売却可否未確認時の推奨抑止を別途レビューする。
4. 期待取引日と実データの一致、データ取得元の欠損原因、実通知先の有効性が確認されるまで「全面復旧」としない。
5. 現行の全額売却案内が損切り禁止を満たさないことを解決するまで、V2の売却機能の受入合格とはしない。

今回の成果は提案まで。受入条件に対応する修正版テストや本番確認を実施済みとはしない。


## Sonnetレビュー反映と未決仕様

RSIが数値でも対象日のClose欠損時は有効扱いにしない。4銘柄すべて欠損と断定せず、銘柄・項目別に調べる。HTTP失敗は非秘密ステータスを記録し、接続失敗などステータスなしと区別する。

R-01障害通知経路とR-02原価未確認時の案内は[判断案](../../docs/decisions/DECISION_OPTIONS_R01_R02.md)を作成。非0終了だけで復旧としない。両案とも未採用・未適用。データ検査だけ加え旧全額売却案内をそのまま本番へ戻す提案ではない。

[診断モード仕様案](../phase0_review1_20261023/DIAGNOSTIC_MODE_SPEC.md)に銘柄別末尾・最終有効日・期待取引日・取得エラー・必要履歴の記録を定義。未実装。上のコード例も未適用で、更新後の受入試験を実施済みとはしない。
