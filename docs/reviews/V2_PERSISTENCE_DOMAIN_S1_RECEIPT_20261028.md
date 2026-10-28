# V2 保存ドメイン S1 実装受領レビュー

作成日：2026-10-28（日本時間）。対象：b9586d65aa411bfe32ca6fe795ad4b15e972d59c。  
判定：修正後に再確認。重大0・通常3・提案1。本番接続・S2以降への着手を承認する文書ではない。  
コードは変更していない。読取り、独立した一時ソースでの試験・再現、レビュー成果物の保存のみ。

## 1. 対象版と結論

| 項目 | 対象 |
|---|---|
| リポジトリ | Rocky009-jp/soxl-alert |
| 実装ブランチ・最終SHA | feat/v2-persistence-domain-offline-20261028、b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| 試験対象SHA（作業者報告） | 5083b376b6a082afe94380d88dba43ef999d86e1 |
| 実装基準 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| 採用した設計・依頼 | 第4版、425df80d04b116e25e481184069b89bed1380c3a |
| 結果文書 | [V2_PERSISTENCE_DOMAIN_RESULT.md](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/docs/implementation/V2_PERSISTENCE_DOMAIN_RESULT.md) |
| 再現用スクリプト | [V2_PERSISTENCE_DOMAIN_S1_REPRO_20261028.py](V2_PERSISTENCE_DOMAIN_S1_REPRO_20261028.py) |

b616b4eからの差分は追加17ファイルだけ。既存ファイルの変更・削除は0で、5083b37からb9586d6への差分も結果文書の追加だけだった。メモリ上の単日準備、コアへの委譲、保存入力からの再計算、ロック内の比較更新、後工程との分離は依頼の範囲内である。

一方、戻り値から保存状態を書き換えられる経路、市場boolの受理、保存した巨大整数での規定外例外を独立に再現した。A-07の独立性・数値拒否、および保存入力の検査契約を満たさないため、「A-01〜A-08の全条件を満たした」とは現時点で受領しない。既存試験の合格と、これらの追加ケースの検出は両立する。

## 2. 確認範囲と証拠の区別

| 確認主体 | 内容 |
|---|---|
| 作業者報告 | Linux、Python 3.10.20／3.11.17／3.12.3／3.13.17で既存181＋新規154、失敗0・skip0・終了0。core.autocrlf=falseのクリーンクローン、OSレベル通信遮断。全4版の実行は主担当が再現した結果ではない |
| 主担当の読解 | 新規パッケージ8本、新規試験8本、結果文書、固定された設計・依頼。GitHub compareで差分を確認。coreの名前束縛と保存状態の参照経路を確認 |
| 主担当の独立環境 | Windows、Python 3.12.14。一時ソースのv2_core 12本と新規Python 16本についてGit blob SHAを照合し、GitHubの対象版と一致。Git cloneによる全リポジトリの取得ではない |
| 主担当の試験 | 新規154件を探索し、fixture依存1件を除く153件を実行。153合格、失敗0・error0・skip0、終了0。p_helpersによるプロセス内のソケット禁止。Linuxのunshare等によるOSレベル遮断はこの確認には使っていない |
| 主担当の未実施 | 既存181件の今回の再実行、研究fixture依存の新規1件、他のPython版、作業者の58件の欠陥注入、40回の競合反復の独立再実行 |
| ユーザーPC | b616b4eの181件確認は後日実施のまま。主担当のWindows環境の確認でユーザーPC確認済みにしない |

未実施の1件は test_a03_recompute.RoundTrip.test_research_fixture_chain_matches_core_and_survives_json。必要な研究fixtureを今回の一時ソースに揃えていないため、実行対象から明示的に外した。skip／合格として集計していない。新規試験は編集していない。

実行した153件の出力要旨：

    discovered=154, selected=153
    Ran 153 tests in 5.239s
    OK
    failures=0, errors=0, skip=0, exit=0

## 3. 修正事項

### R-01：通常／公開APIの戻り値から、commit無しで保存状態が変わる

根拠：[recompute.py:131](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/v2_persistence/recompute.py#L131)、同173／192／272〜273、[runner.py:106](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/v2_persistence/runner.py#L106)、[store.py:24](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/v2_persistence/store.py#L24)。設計§4／§8、依頼A-07の独立性に対応する。

validate_snapshotはsnapshot._internal()の辞書を読んで、境界、各APPLYのtransition_result／state_after、current_stateから作ったMarketState等への参照を戻り値へ残す。MarketState.from_dictもfixed_decisionの辞書をコピーしない。その状態がdecision無しのevaluate_dayを経てcore_result.next_stateとして返る。MemoryStore.readは同じSnapshotを共有するため、公開された戻り値の入れ子を書き換えるだけでストア内の辞書まで変わる。

最短の再現（wはsynthetic World、D1適用済み、D2のdecision無し）：

    result = w.prepare(D2)
    assert result.status == "NO_COMMIT"
    result.core_result.next_state.fixed_decision["record_id"] = "REVIEW-EDIT"

この後、保存内容が変化し、validate_snapshotはsnapshot_invalid／current_stateで停止した。同様にvalidate_snapshotのboundary_session、applies[0].transition_result、applies[0].state_afterからの変更でもevent_hash不整合になった。private属性を直接操作していない。

4経路とも、head_seq／head_hashとencode_snapshotの文字列は変更前のままで、to_dictで読んだ内容だけが変わった。encode→decodeした内容と直接読んだ内容も食い違う。Snapshotの__eq__は文字列を比べるため、同じSnapshot参照とのassertEqualだけではこの破損を見逃す。

最小の修正案：validate_snapshotが扱うデータをSnapshotから独立した深い写しにし、公開される検査結果・MarketState・NO_COMMIT結果がストアの内部を参照しないようにする。例えば入口をsnapshot.to_dict()にする方法を検討できる。既存v2_coreを変更する必要はない。privateへの意図的な直接操作を防ぐセキュリティ機構を追加する依頼ではない。

確認条件：上記4経路の入れ子を変更しても、元Snapshotのto_dict・encode結果・先頭は不変で、再検査も正常。変更を拒否する不変値にする方法でもよい。比較用の変更前データを深く保存し、同じSnapshot参照やencode結果だけを比較しない。

### R-02：通常／市場値のboolが正規化でfloatとなり受理される

根拠：[events.py:34](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/v2_persistence/events.py#L34)。設計§5.2の「市場の数値はboolを拒否」に対応する。

row_dictが型検査前にfloatを呼ぶため、Trueは1.0となる。その後の再計算・正準形検査では元がboolだったことを判別できない。synthetic MarketRowのD行でsoxx、sma、rsi、shd、prev_rsiをそれぞれTrueにした5ケースすべてがPREPAREDになり、保存候補には1.0が入った。

通常のMarketSeries生成側にも価格検査はあるが、S1の明示した市場入力検査と合成入力での契約を満たす根拠にはならない。市場入力の型を黙って別の意味へ変えない。

修正案：D行・前日行の市場数値をfloatへ変換する前にboolを拒否する。文字列等を含む入力型と有限性も、共有する検査で確認する。市場ルールの条件式を複製せず、v2_coreも変更しない。

確認条件：D行・前日行の全数値フィールドにTrue／Falseを与え、規定された安全なCoreError系で準備前に拒否、計画なし・状態不変。正常なint／float入力の正規化と既存ケースは維持する。今回再現したのはD行Trueの5件であり、その他は修正時に追加確認する範囲である。

### R-03：通常／保存入力の巨大整数がsnapshot_invalidでなくOverflowErrorとなる

根拠：[recompute.py:86](https://github.com/Rocky009-jp/soxl-alert/blob/b9586d65aa411bfe32ca6fe795ad4b15e972d59c/v2_persistence/recompute.py#L86)。設計§6／§9の保存入力検査と安全なcodeに対応する。

保存APPLYのrow.soxxを10**400に変更し、input_hash・event_hash・親・ヘッダーを整えたSnapshotで、_numのfloat(x)がOverflowErrorをそのまま送出した。これは401桁のJSON整数で、JSONとしては表現できる。巨大値を受理すべきという指摘ではなく、snapshot_invalidとして拒否する経路が欠けているという指摘である。

修正案：保存入力の数値正規化の変換例外を安全なsnapshot_invalidへ写像する。保存decisionなど同じ変換を呼ぶ新パッケージ側の境界も確認する。既存コア側へ無関係な例外処理の改修を広げない。

確認条件：JSON往復した巨大整数でも規定されたPersistenceError／snapshot_invalidで拒否し、raw値を例外文へ出さない。計画・保存状態は不変。想定外のOverflowError／ValueError／TypeErrorを単に黙殺して正常扱いしない。

## 4. 提案P-01：欠陥注入の集計を整える

報告は58通りに対し、検出55＋対象外1＋同値の未検出1＝57で、1件の区分が読み取れない。スクリプトが保存されていないため、主担当は残り1件や55件の実測を独立確認できない。

総数・適用数・検出数・対象外・同値の区分を確認し、報告の数を揃える。残り1件を推測で「検出済み」に足さない。今回の3件を直すために58件全部や前工程の43件を自動的に再実行する依頼ではない。

保存窓select_decisionの省略が投影一致後に同値になる説明は、コード上のD.close_at／next.open_atの一致と整合する。この同値の1件を試験不足と認定するものではない。

## 5. 再現方法

対象の実装ブランチのb9586d6を別のチェックアウトで固定し、隣の再現用スクリプトにそのルートを渡す。

    <python> -B <review-dir>/V2_PERSISTENCE_DOMAIN_S1_REPRO_20261028.py --repo-root <b958-checkout> --expect-fixed

今回の実行環境では、10観測ケースすべてで指摘の現象を再現した（R-01=4経路、R-02=5フィールド、R-03=1入力）。--expect-fixedでの終了コードは1。これは回帰条件が満たされないことを示す想定どおりの結果であり、S1の合格試験に数えない。フラグ無しは観測をJSONで報告して終了0とするだけで、終了0をS1合格と解釈しない。

ネットワークはp_helpersによってプロセス内で無効化される。実ファイルへの状態保存・実データ・ユーザー口座値・外部通知は使わない。

## 6. 次の最小作業（限定修正案）

Sonnet 5.5・highで、b9586d6を基準とする別の修正ブランチに、R-01〜R-03の新規パッケージ内の修正と回帰試験を追加する案。実装担当が本文を確認して修正内容を具体化するための依頼案であり、このレビューをもってS2以降を許可しない。

- 変更範囲はv2_persistence、新規tests/v2_persistence、今回の結果文書。既存v2_core・既存181件・基準データ・依存・workflowを変えない。
- 現行新規154件を弱めずに上記の回帰ケースを加える。規定エラーと不変性を検査し、公開APIのすべての構造化戻り値に同じ参照共有が無いか確認する。
- Python 3.10／3.11／3.12／3.13で既存181件・現行154件・追加回帰を実行し、依頼どおりクリーンクローンで最終版を確認する。実機Windows、歴史照合、全欠陥注入を追加の完了条件へ広げない。
- 結果文書のA-07・数値検査・独立性の主張を修正後の根拠へ更新し、欠陥注入の集計も確認する。新しい合格件数を実測し、推測で増やさない。
- 試験対象と結果文書追加後の保存最終SHAを区別して報告し止める。本番接続・PR作成・送信・復旧操作は引き続き対象外。

## 7. 参照と変更範囲

主担当確認時に、保護5参照はmain 31144d9、候補920e695、資料正本647aeac、旧コア1a54a85、実装基準b616b4eで不変。採用資料425df80、上位資料b43205c、レビュー対象の実装b9586d6も固定した。完全SHAは結果文書§11および本書§1の固定版に対応する。

レビュー成果物は実装ブランチを変更せず、別の資料ブランチdocs/v2-persistence-domain-s1-receipt-20261028へ本書と再現用スクリプトだけを保存する。既存の設計・依頼・レビュー原文・結果文書は上書きしない。実装修正、PR、Actions起動、通知送信は行っていない。

未確認：ユーザーPCでの181件、実ファイル保存、耐久性、複数プロセス、台帳完全性、配信、ACK／復元、実カレンダー、歴史遅延1全日照合。これらは今回のレビュー結果で完了扱いにしない。
