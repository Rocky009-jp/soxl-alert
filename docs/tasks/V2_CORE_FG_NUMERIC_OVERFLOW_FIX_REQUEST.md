# V2 コア F&G巨大整数の入力エラー統一 限定修正依頼案

作成日：2026-10-28（日本時間）。状態：未承認・未着手。  
ユーザーがこの範囲のコア変更を指示した後にだけ実施する。S1の採用や完了報告を、この追加コア変更の承認と扱わない。

## 1. 目的・固定版

基準SHA：d44155bca65719da9fc2026ba317c231e950f1b7（fix/v2-persistence-domain-s1-review-20261028）。  
根拠：[S1限定修正の受領確認](../reviews/V2_PERSISTENCE_DOMAIN_S1_FIX_RECEIPT_20261028.md)、同版の結果文書§15.7。

S1のR-01〜R-03は修正済み。今回の対象は、注入台帳のcurrent_fg_valueが10**400等の場合に、コアのfloat変換でOverflowErrorが外へ漏れる1点である。通常のF&G値・市場ルール・保存形式・判定内容は変更しない。

担当案：Sonnet 5.5、エフォートhigh。実際の設定を開始時に記録する。使用モデルの独断変更はしない。

## 2. 許可する差分案

| 場所 | 内容 |
|---|---|
| v2_core/observations.py | _parse_valueの数値型分岐でfloat(raw)のOverflowErrorをInputError("fg_value_invalid", "current_fg_value")へ変換 |
| tests/v2_core/test_fg_numeric_overflow.py（新規） | この入力と各公開入口の回帰。既存181件と保存ドメイン170件のファイル・基準データは変更しない |
| docs/implementation/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_RESULT.md（新規） | 修正根拠、試験、完全SHA、互換性と保留 |

期待する実装差分は次だけ。boolの先行拒否、文字列の既存ValueError処理、有限性・0〜100の検査は維持する。

    if isinstance(raw, (int, float)):
        try:
            v = float(raw)
        except OverflowError:
            raise InputError("fg_value_invalid", "current_fg_value")

コード用の新規ブランチ例：fix/v2-core-fg-numeric-overflow-20261028。基準d44155bから作り、既存参照を進めない。資料は本書と受領確認を同じ固定コミットから読み、開始時に完全SHAとblob SHAを記録する。

範囲外：他のv2_coreファイル、v2_persistence、既存試験の書換え、依存・workflow・CLAUDE・STATUS、保存／復旧アダプタ、外部通信・本番・PR。必要になったら、理由と最小差分案を報告して、その変更は行わない。

## 3. 受入条件

- 正負の10**400をraw台帳に与え、parse_observation／select_decision／evaluate_dayがInputError、code=fg_value_invalid、field=current_fg_valueを送出する。OverflowErrorは外へ出ない。
- run_day_safeは上記入力をErrorResult（終了1、状態更新なし）として返す。正常なNO_SIGNALへ変換しない。
- S1のprepare_dayも同じcode／fieldで停止し、計画・ストア内容・seq・先頭を変更しない。既存の保存巨大整数は引き続きsnapshot_invalidとして拒否する。
- 0／100を含む正常なint・float・数値文字列は従来どおり。bool、非有限値、範囲外、読めない文字列の既存拒否を維持する。
- 既存181件と保存ドメイン170件を弱めずに合格させ、新規回帰の実測N件を別集計する。新規試験だけを旧d44155bへ当てると巨大整数ケースで失敗することを一度確認する。前工程の57件や他の欠陥注入は作り直さない。
- 保存入力からの再計算・正常入力の判定に差が無いことを既存回帰で確認する。3114ケースや歴史全日照合を新たに作り直す依頼ではない。

## 4. 互換基準と検証環境

v2_persistenceのCORE_SHA／schema_versionは今回変更しない。CORE_SHAはS1が準拠するb616b4eの再計算互換基準を示す定数であり、実際の全ソースHEADの自己証明ではない。この扱いも本依頼の採用時に含める。今回の実際のコード版は結果文書の完全SHAで区別する。

今回に限り、既存コアの変更許可はobservations.pyの当該入力検査に限定する。S1での「v2_core差分0」は当時の記録として残し、今回も差分0だったと書かない。許可した1ファイル以外の既存コード・試験・基準データの差分0を確認する。正常な保存入力の再生結果が変わる場合は、互換を推測せず停止して報告する。

Python 3.10／3.11／3.12／3.13、core.autocrlf=falseのクリーンクローンで、通信を遮断して既存181＋保存ドメイン170＋新規N件を実行する。完全バージョン、コマンド、件数、失敗・error・skip、終了コードを記録する。既存の隔離インタプリタを再利用し、必要な3.10取得はスクラッチ領域のuv単体インタプリタだけを認める案とする。依存・設定は変更しない。

fixtureを含む作業者のクリーンクローンでは該当1件も実行する。fixtureが無い環境の独立確認は未実施と記録し、合格やskipへ置き換えない。ユーザーPCでの181件確認、Windows実機、歴史遅延1全日照合を今回の追加完了条件にしない。

## 5. 終了時の報告

開始・試験対象・保存最終の完全SHA、変更一覧、モデル／環境、既存351件と新規N件の集計、旧版での回帰の感度、正常入力・保存形式の互換性を結果文書へ記録する。試験後に結果文書だけを追加した場合は、その差分も示す。

main 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、実装基準b616b4e、上位資料b43205c、採用資料425df80、前回レビューda24fcd、元実装b9586d6、S1修正d44155bと本依頼を読んだ資料参照を、開始・終了時に完全SHAで確認し、今回書き込まない。

最終結果を保存・報告して止める。PR作成、main反映、ジョブ起動、送信、S2以降へ続行しない。
