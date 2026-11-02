# V2 S3-B-4 レビュー限定修正依頼案

作成日：2026-11-02。**レビューによる提案・修正実装は未承認**。
本書の保存は実装承認ではない。採用後もB-5/S3-C・CONSUME・保存・バッチ統合・PR・Actions・本番・通知には進まない。

## 1. 固定基準と成果物

- コード開始点：**5eede119b6729e288d188c67de900bcdfcb27cb1**。コードは47eb7c5c8c42acc8e218b3b891ce1b6a02e5a664と同じ。新しい修正ブランチをここから作り、元のfeatブランチを更新しない。
- ブランチ案：fix/v2-history-restore-plan-s3b4-review-20261102。
- 固定設計・依頼：0108131045d904b0997299fcade5929567940d6d。
- レビュー：本資料ブランチのdocs/reviews/V2_RECOVERY_S3B4_IMPLEMENTATION_REVIEW_20261102.md。
- 再現スクリプト：**1b8521cb880d10ef4316aaedbcf8a084a11cfeeb**のdocs/reviews/s3b4_review_reproduce.py。レビュー本文もこのコミットに保存済み。
- 推奨担当：Sonnet 5.5・effort high。実際に確認できたモデル・設定と、確認できないものを区別して報告する。

レビューは重大0・通常3・提案1。実Windows/Python3.12.14の標準836件は合格したが、追加再現でR-01/R-02の10観測、R-03の4単一変異の反例を確認した。標準試験の合格だけで修正不要とはしない。

## 2. 設計説明の補足（R-03）

元設計§10/P-01の「DROPなしなら全REAPPLYが同じになる」という同値説明は、現在カレンダーの追加・欠落を考慮しておらず誤りだった。本書で補足する。保護資料ブランチは変更しない。

採用済みの厳密な条件 **「DROPなし、かつ全REAPPLYのsame_as_supersededがtrueならrestore_no_effect」** を維持する。DROPなしを一律拒否する修正はしない。既存の共有日context照合・prev_session照合・候補検査は維持し、カレンダー仕様の全面変更をしない。

既知の案aの保守的な拒否、将来のACKで前の宣言を通さない規則、候補Historyまでという境界も維持する。

## 3. 修正内容

### R-01 最終的な参照でchanged_fieldsを計算する

records.pyのREPLAY作成時には参照hashが仮値である。build.pyの参照fixup後、最終記録と直接の元記録を、設計の意味上の比較項目で比べてchangesを確定する。

- 保持されたAPPLYを参照するADDED ACKでは、最終applied_refが同じなら変更項目に含めない。
- 保持されたAPPLYを参照するLATE ACKでも、最終missing_refが同じなら含めない。
- 写像によって実際に参照が変わる対照では含める。state_after等の真の変更は残す。
- seq・parent・event_hash等の連結上の差を意味上の変更項目に加えない。
- この修正で正常入力のcandidate events/digestを変えない。changesの訂正によるplan_hashの変更は認め、その理由を示す。

### R-02 plan固有の検査を現在入力より先に完了する

確認Aと再確認Bの両方で、plan自身に関する構造・安全性の検査を、現在履歴/sessions/台帳/seriesの検査前に行う。

- changesの各行の必須項目、操作enum、安全な日付・項目名の列、厳密整数と下限等を検査する。listであることだけでは足りない。
- series_inputs等もplan固有の形を点検する。入力との意味上の一致の確認は従来の段階に残す。
- opsのfrom_seq等はboolを整数として受けず、負値を受けない。
- REAPPLY元記録を取り出すためにplan自身を調べる処理も、現在入力より先に行う。生のKeyError/IndexError/TypeErrorへ漏らさない。
- 不正planは **history_plan_mismatch／plan**。hashを付け直した不正changesや負のfrom_seqとsessions=Noneを組み合わせても同じである。
- 正しいplan＋不正入力は、従来どおりsessions_invalid等の入力固有エラーを返す。正しいplan＋変更された正常入力のstale判定や、元履歴側/候補側の全basis再構築を弱めない。
- JSON深さ・巨大整数の検査順序、コピー、表示の固定表現を維持する。

### R-03 4反例を回帰に固定し、旧等価判定を訂正する

詳細な合成入力とコードは同梱再現スクリプトを正とする。旧版の公開置換をそのまま1件ずつ適用して差を確認済みである。

| 変異 | 固定すべき正常コードの結果 | 旧単一変異の結果 |
|---|---|---|
| M09c 新skipをreleased_daysから除外 | カレンダーにD1を追加＋D1decision、D3 REAPPLYとRESTART DROPでrestore_requires_consume | late_observation |
| M12b DECLARE frontierの旧値コピー | D1宣言DROP、D2宣言REPLAY、現在カレンダーからD1欠落でREADY、新frontier=D0 | history_invalid／declare_frontier |
| M16d candidate_recordsと候補末尾の一致検査を削除 | candidate_records=[{}]＋再hash＋sessions=Noneはhistory_plan_mismatch | sessions_invalid |
| M17c same条件を削除しDROPなしだけで拒否 | 現在カレンダーへD1追加、decisionなし、D3 REAPPLYのみでREADY、same=false | restore_no_effect |

M17cの正常対照はchanged_fieldsがinput_hash/skipped_sessionsで、確認A=CONFIRMED_IN_MEMORY、再確認B=NO_CHANGEまで通ることを固定する。元の全shared contextとD3のprev=D2は一致している。これらは合成カレンダーであり、実取引所の改訂事例という主張ではない。

- 旧47eb7c5の4件の「等価」は誤りと明記する。旧144件が検出済みだったとは書き換えない。
- 新試験で反例の動作を固定し、適切な感度確認をしてから新しい検出結果を書く。
- 修正後に独立した検査が追加され、ある削除変異が本当に冗長になったなら、新版・条件・理由を分ける。旧版の等価判断を正当化しない。恣意的な呼出し回数だけで検出を作らない。
- 61変異すべての再実行はこの修正の必須条件にしない。実施範囲と旧結果を分け、未実施・準備失敗を検出/等価/合格に数えない。
- 任意P-01：M16aの説明を、変更していない生成器に対する当該削除だけの単一変異という範囲へ限定する。hash鎖の自己整合だけで元prefixの同一性まで保証するとは書かない。prefix比較は削除しない。M16a非等価は今回未証明。

## 4. 変更を許す範囲

| パス | 許す変更 |
|---|---|
| v2_history_restore/records.py、build.py、confirm.py、values.py | 上のR-01/R-02に必要な内部実装・helperだけ。必要なファイルだけを変更 |
| tests/v2_history_restore/test_r4_10_review_fixes.py | 新規回帰。名称が衝突する場合は同じtest_r4_形式の未使用名 |
| tests/v2_history_restore/r4_sensitivity.py | R-03の分類・理由・反例probe・試験対応の訂正。元の変異IDと履歴を残す |
| docs/implementation/V2_RECOVERY_S3B4_RESULT.md | §10として今回の記録・旧分類訂正・設計補足を追記。元の§1〜§9は過去の記録として残す |

既存144件の試験本体、scope試験2本、既存パッケージ、fixtures、schema、公開名/引数、依存・設定・workflowを変更しない。新しいランタイムファイルは追加しない。他のファイルや挙動を変える必要が出たら、その変更を実行せず理由と最小差分案を報告する。

## 5. 受入条件

1. 旧144件を無編集で合格。旧7スイート1168件も従来のOS契約で合格。LinuxではWindows専用4件は未実施のskipとして別記する。新規N件と混同しない。
2. R-01の保持参照2例と、写像で参照が変わる対照を固定。修正前とのcandidate events/digest一致を示し、plan_hashの差はchanges訂正として説明する。
3. R-02の悪いchanges3形×確認A/Bと負from_seq×A/Bの計10観測が、--expect-fixedで未解消0・終了0。正常plan/不正入力の対照、正常確認/再確認を維持する。
4. R-03の4反例を新回帰へ固定。DROPなしカレンダー変更の正常確認A/Bを維持する。旧コード・単一変異での差と、新版の感度結果を分けて記録する。
5. 自分の修正を1件ずつ戻す等の意味のある感度確認を行う。元の61変異を全件再実行していないなら、その旨を明記する。
6. Python3.10〜3.13、core.autocrlf=falseのクリーンクローンで必要な全スイートを確認する。可能なLinuxではunshare等の通信遮断。実Windowsがない場合は未実施とし、Linux注入で実Windowsを代用したと書かない。WindowsではB-4/B-3/B-2/S3-A/B-1とS2実Windows4件が今回レビューと比較可能な836件＋新規N件となる。Linux全スイートは1312＋N件中、Windows4件をskipとして別記する。
7. 再現用スクリプトは読取専用のまま使う。--expect-fixedはR-01/R-02と正常対照、--mutationsは公開置換の存在と反例を調べる。構造変更で置換が無くなれば準備失敗であり、検出と同一視しない。
8. 変更範囲、保護参照、既存ファイル差分を確認する。試験対象SHAと、結果文書だけ追加/追記した最終SHAを分けて保存する。新しい修正ブランチだけpushし、PRを作らず停止する。

物理電源断、autocrlf=true、ユーザーPC、耐久性、CONSUME/B-5/S3-C/本番は今回の完了条件外。未確認のものを合格へ数えない。

## 6. 保護参照

開始時と保存後に次の52参照の完全SHAを照合する。加えて本依頼を受領したレビュー資料ブランチのHEADを開始時に固定し、終了時も同一と確認する（計53参照）。確認時刻・不一致・確認できなかったものを区別する。これらのブランチを更新しない。

| 参照 | 完全SHA |
|---|---|
| main | 31144d9b6af8a6c920ad53c395cd550e8c48a7fa |
| feat/interim-notification-20261026 | 920e69571cf4feda09f3f2f560e96fcb9cb09d50 |
| docs/v2-roadmap-20261023 | 647aeac34cde0d01ec27174f7620aff1724af0e1 |
| feat/v2-offline-core-20261027 | 1a54a8573023af9490017b02a8b6458f061031c7 |
| feat/v2-core-state-checks-20261028 | b616b4ec7169420e199ec7e247dd375b3603a013 |
| docs/v2-market-state-recovery-20261027 | b43205ce1a53e4560fb85f9cfb715c72a1132a75 |
| docs/v2-persistence-domain-20261028 | 425df80d04b116e25e481184069b89bed1380c3a |
| docs/v2-persistence-domain-s1-receipt-20261028 | da24fcd4fcd70a51753ff61b3f9aa1436ec431c2 |
| feat/v2-persistence-domain-offline-20261028 | b9586d65aa411bfe32ca6fe795ad4b15e972d59c |
| fix/v2-persistence-domain-s1-review-20261028 | d44155bca65719da9fc2026ba317c231e950f1b7 |
| docs/v2-persistence-domain-s1-fix-receipt-20261028 | 08400ac04bfcb4831c9ef7b8ed518c00c8987048 |
| fix/v2-core-fg-numeric-overflow-20261028 | 2d09db770d21480202c4c603e02c2aec5e030012 |
| docs/v2-core-fg-overflow-receipt-20261028 | a235b7607f5624ed84ba5427ac0f44029f41d262 |
| docs/v2-local-store-s2-20261028 | 73cec624cb73205ac63ca92e26df2b6f70019b16 |
| feat/v2-local-file-store-s2-20261028 | 00e7f84806ce34dc8754a0fc558870db145ade68 |
| docs/v2-local-store-s2-receipt-20261028 | 87f22f448c41f4ec5951122afaae729167b2f9e3 |
| fix/v2-local-store-s2-review-20261028 | d404d4df481957f89201c5169f3a75d7b9d86b66 |
| docs/v2-local-store-s2-fix-receipt-20261028 | 1b5b8ce0dcd82c9f2ff929a45e209b81e95f7d5a |
| docs/v2-user-pc-tests-20261028 | aa21dbe85a133c61e8c011a6f78db1b23af0fb13 |
| docs/v2-recovery-s3-20261029 | 2d504de7cbf4628a3760d48f70fd0228dce6a61c |
| docs/v2-recovery-s3a-adoption-20261029 | d215193065ebf110e6a77f22edf208b390138285 |
| feat/v2-recovery-resolution-s3a-20261029 | 2c246e3e485d9dcb90fb35ab1628040b484fb7c2 |
| docs/v2-recovery-s3a-receipt-20261029 | a5109e2d000b43dee96ab7019d6db92d0345ff69 |
| fix/v2-recovery-resolution-s3a-review-20261029 | e68d702de7fa80f141e14b63cf88082c15493994 |
| docs/v2-recovery-s3a-fix-receipt-20261029 | abb2e73a4980c635f0f471d1819b6b1734661fa1 |
| docs/v2-recovery-s3b-20261029 | 588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| docs/v2-recovery-s3b-review-20261029 | fd66a6dc0c04365633a0a497dced4f8ace08167e |
| docs/v2-recovery-s3b-revision-20261029 | 361904b1618ae9f9d3a672875c437a388826c253 |
| docs/v2-recovery-s3b-v2-receipt-20261029 | 225b10059bdc23a677f97fc3ac7597ca73c4b00c |
| docs/v2-recovery-s3b1-adoption-20261029 | 98e05e426b99154e7a5941c718b2b220f048e2a2 |
| feat/v2-history-s3b1-20261029 | 0fbba6c46f62a5765cf1ffb8e3646325c1787373 |
| docs/v2-history-s3b1-receipt-20261030 | 6e7f756544f9dc6f1a17f94d4f4dbcaf35def4e3 |
| fix/v2-history-s3b1-review-20261030 | adfdf765aeca0d01c8f10b596a6fac59d7c1a07e |
| docs/v2-history-s3b1-fix-receipt-20261030 | e8a94e5d415fce28f0ba7744b72a3d3dc390279b |
| docs/v2-history-s3b2-design-request-20261030 | fee48e944172950b7e58581c000f0750319a9fd7 |
| docs/v2-history-s3b2-20261030 | 62861137a28e96a361f198f5601e0f5ae77a6910 |
| docs/v2-history-s3b2-review-20261030 | ce07dbd0b2e587eb8c4cd77b847f9b53fcdb8d3e |
| docs/v2-history-s3b2-revision-20261030 | e083cd3187f17692cb081fcc1031b09551fb8cb7 |
| docs/v2-history-s3b2-v2-receipt-20261030 | c4284ffc818d79155407ce153e44e35d135659e1 |
| docs/v2-history-s3b2-adoption-20261030 | 9b290e7a25144dccd9aa1ffee5664f47ad924b5d |
| feat/v2-history-s3b2-20261030 | 132a3392115e44105895ecea92e472b49107fed3 |
| docs/v2-history-s3b2-receipt-20261030 | bd59d456cd33108e97428036a665664c04b802b5 |
| fix/v2-history-s3b2-review-20261030 | b328844fdeda235cf95bf7851ba9e3d7d55aa7bb |
| docs/v2-history-s3b2-fix-receipt-20261030 | 5743732781523ab60f1025037d99410a41285de8 |
| docs/v2-history-s3b3-20261030 | f90c2e6a2219dfac6adc2ed65f1560c1c2f87a3c |
| docs/v2-history-s3b3-revision-20261030 | d0e11d9d5158deb6bfdc11e4224fe1f77a9dedba |
| feat/v2-history-restart-s3b3-20261102 | d82a5ced64658c2e736b82b1a2f1925636055417 |
| docs/v2-history-s3b3-receipt-20261102 | 78b9b405cebfb37283bf59f35d7774ad6910b331 |
| docs/v2-history-s3b4-20261102 | f94220856c849f4a7dd91deac04b9b5a820a6239 |
| docs/v2-history-s3b4-v2-receipt-20261102 | 0108131045d904b0997299fcade5929567940d6d |
| docs/v2-history-s3b4-revision-20261102 | f353fb96557993e95049dd7dfd57286a80f1afb4 |
| feat/v2-history-restore-plan-s3b4-20261102 | 5eede119b6729e288d188c67de900bcdfcb27cb1 |

## 7. 停止点

R-01〜R-03の限定修正・試験・結果保存まで。結果は別途レビューする。本書の推奨担当と範囲、設計説明の補足を含む修正着手の採否はユーザーが判断する。
