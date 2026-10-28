# V2 保存ドメイン S1 限定修正の受領確認

作成日：2026-10-28（日本時間）。対象：d44155bca65719da9fc2026ba317c231e950f1b7。  
結論：前回R-01〜R-03の限定修正を受領する。この差分の確認で新たな重大・通常の問題は見つからなかった。  
S1はメモリ上の限定実装として完了扱い。既知のコア入力例外は別件として残し、本番接続やS2以降の実装完了とは区別する。

## 1. 固定版・差分

| 項目 | 値 |
|---|---|
| 修正ブランチ | fix/v2-persistence-domain-s1-review-20261028 |
| 修正前 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| 試験対象 | e37275df1208a8c896954645e1997826f80a139e |
| 保存最終 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| 採用資料 | 425df80d04b116e25e481184069b89bed1380c3a（第4版） |
| 前回レビュー | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| 結果文書 | [第2版§15](https://github.com/Rocky009-jp/soxl-alert/blob/d44155bca65719da9fc2026ba317c231e950f1b7/docs/implementation/V2_PERSISTENCE_DOMAIN_RESULT.md) |

b9586d6からは、events.py／recompute.py／既存の新規試験test_a07_failure_independence.py／追加回帰test_s1_review_fixes.py／結果文書の5ファイルだけ。既存v2_coreと既存181件は変更されていない。e37275dから最終版の差分は結果文書の更新1本のみ。基準b616b4eに対しては追加18ファイルだけである。

## 2. 指摘の解消

| ID | 差分の確認 | 独立確認 |
|---|---|---|
| R-01 参照共有 | validate_snapshotの入口をsnapshot.to_dict()へ変更。内部辞書に結び付いた検査結果・MarketStateを外へ渡さない | 前回の4経路で戻り値を編集しても保存内容・先頭・encode結果は不変。encode→decodeと直接読取も一致し、再検査も成功 |
| R-02 市場bool | float変換前にboolと数値以外を拒否。D行と前日行のruleを区別 | 前回D行5フィールドを拒否。追加16件に含まれるD／前日行のTrue・Falseと正常数値の回帰も合格 |
| R-03 保存巨大整数 | _numのOverflowErrorと保存decisionのparse_observationからのOverflowErrorをsnapshot_invalidへ変換 | 前回の保存row巨大整数はPersistenceError／snapshot_invalid、rule=row。回帰試験の他フィールド・decision・JSON往復も合格 |
| P-01 集計 | 総数57へ訂正し、検出55・対象外1・同値1を明記 | 記載された検出名55件は重複なし、区分合計57。57件の実際の欠陥注入は主担当側では再実行していない |

修正は市場ルールの変更ではなく、戻り値の独立性と入力検査の補正に収まっている。

## 3. 試験の主体と範囲

| 主体 | 確認内容 |
|---|---|
| 作業者報告 | Linuxのクリーンクローン、core.autocrlf=false、通信遮断でPython 3.10.20／3.11.17／3.12.3／3.13.17、既存181＋保存ドメイン170件、skip0・失敗0。16件を旧版へ適用した13失敗と、修正を戻す6通りの感度確認も報告あり。これら全てを主担当が独立再実行した意味ではない |
| 主担当のソース確認 | GitHubの固定版を用い、一時ソース29本（v2_core 12、v2_persistence 8、新規試験9）のGit blob SHA一致を確認。GitHub compareで差分と最終文書のみの更新を確認 |
| 主担当の独立実行 | Windows／Python 3.12.14。保存ドメイン170件を探索し、fixture依存1件を除く169件が合格。失敗0・error0・skip0・終了0。追加16件もこの169件に含む |
| 前回の再現スクリプト | da24fcdの再現スクリプト相当を変更せず実行。--expect-fixedで10観測すべてissue_present=false、終了0 |
| 独立未実施 | 既存181件の今回の再実行、fixture依存1件、他Python版、旧版13失敗の再実行、6通り／57通りの欠陥注入、40回の競合反復 |
| ユーザーPC | 181件確認は後日のまま。主担当のWindows環境による実行とは別 |

169件の実行はp_helpersでプロセス内のソケットを禁止した。OSレベルのネットワーク名前空間による遮断は、このWindows確認には用いていない。既存の新規試験を編集・skip化していない。

未実施の1件はtest_a03_recompute.RoundTrip.test_research_fixture_chain_matches_core_and_survives_json。作業者はfixtureを含むクリーンクローンで合格を確認しているが、こちらの一時ソースではfixtureを揃えていないため明示的に実行対象から外した。

    discovered=170, selected=169
    Ran 169 tests in 5.098s
    OK
    failures=0, errors=0, skip=0, exit=0
    previous_repro: probe_cases=10, issue_observations=0, expect_fixed=true, exit=0

## 4. 別件：台帳の巨大整数に対するコア例外

結果文書§15.7の所見を確認した。変更していないv2_core/observations.pyの_parse_valueは、数値型のrawにfloatを適用する箇所でOverflowErrorを捕捉していない。

syntheticな台帳へcurrent_fg_value=10**400／-10**400をそれぞれ入れ、prepare_dayで独立再現した。両方ともOverflowError、規定codeなし、保存状態は不変。保存済み入力に対するR-03の修正は機能しており、今回は注入する生台帳の別経路である。

これは今回新しく入った不具合ではなく、S1の変更禁止範囲だった既存コアの残件として記録する。正常な入力の判定結果や、今回修正した保存入力検査を再び未完了には戻さない。一方、入力エラーを統一して返すため、本番接続前に最小のコア修正を行うことを推奨する。

[別の限定修正依頼案](../tasks/V2_CORE_FG_NUMERIC_OVERFLOW_FIX_REQUEST.md)に、数値型のfloat変換の例外1経路、新規回帰試験、結果文書だけの範囲を具体化した。S1の依頼書はv2_core変更を対象外としているため、この依頼は未承認の案であり着手しない。

## 5. 保存・不変参照・残件

レビュー保存用の別資料ブランチdocs/v2-persistence-domain-s1-fix-receipt-20261028へ本書とコア修正依頼案だけを保存する。実装・既存結果・設計・依頼・前回レビュー・再現スクリプトは変更しない。

保護5参照はmain 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、実装基準b616b4e。加えて上位資料b43205c、採用資料425df80、前回レビューda24fcd、元実装b9586d6、今回修正d44155bを読取専用とし、保存の前後に不変を確認する。

PC実機確認、実ファイル保存、耐久性、複数プロセス、台帳完全性、配信、ACK／復元、実カレンダー、歴史遅延1全日照合は保留のまま。PR、main反映、Actions起動、送信、本番接続、S2以降の実装は行っていない。
