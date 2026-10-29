# V2 S3-B設計・B-1限定実装依頼 初版レビュー（2026-10-29）

対象：**588c84102ab8d55793a6e9bb38e5a8cba3ff36af**。  
結論：**重大0・通常2・提案2。通常2件を文書で補正してから、B-1の採否判断へ進む。**  
本レビューは読取りによる整合性確認であり、S3-Bの実装承認・試験合格ではない。

## 1. 対象と確認範囲

| 項目 | 固定参照・結果 |
|---|---|
| 資料ブランチ | docs/v2-recovery-s3b-20261029、先頭588c84102ab8d55793a6e9bb38e5a8cba3ff36af |
| コード基準 | e68d702de7fa80f141e14b63cf88082c15493994 |
| 設計 | docs/specs/V2_RECOVERY_S3B_HISTORY_RESTORE_DESIGN_DRAFT.md、blob 19d2fd406abf9e92a85906647a772a815cf5a242 |
| 依頼 | docs/tasks/V2_RECOVERY_S3B_LIMITED_IMPLEMENTATION_REQUEST.md、blob 62f4d8a9ec88e81dcef8fcd48ef2bd4abbf3d0bb |
| 差分 | e68d702..588c841は上記の新規2文書だけ、+539行／+174行＝713行 |
| 上位 | e3e90947a718cca877b543739ca60539207ca7a7の保存・復旧設計、特にstate_after／I-15／IB-04／有効・退避履歴。S3境界第3版2d504deの§9・§10 |
| コード照合 | 固定コードのv2_persistence/events.py、recompute.py、runner.py、v2_recovery/validate.pyと、v2_core/transition.pyの状態生成部分 |
| 読解 | 設計・依頼の全文。移行、鎖ビューとS1射影、制御記録、復元・再初期化、例M／R／U、受入条件を突き合わせた |
| 未取得 | レビューに必要なファイルはなし |

主担当の今回の参照照合では、依頼§7の25件（元24参照＋abb2e73）と資料588c841の計26参照が一致した。作成担当の開始・終了時照合は受領報告として区別する。

## 2. 良い構成と実装前に残る点

監査鎖と有効親を分ける形式、復元直前ビューも検査して退避記録を取りこぼさない構成、APPLYの区間ごとのS1射影、移行範囲から旧Snapshot／ResolutionSetを逆検証する構成は妥当である。既存のmake_apply_event／snapshot_of／validate_snapshotの公開名でS1側を組み立てる方針も、コードの形に合う。

移行の参照写像は、S3-Aの元のrequest_basisとhashを保ち、記録上の参照だけv2へ写すと明記している。復元バッチに未完了検査を置き、B-1はメモリ値と検査・移行計画に限るため、S2へ直接つなぐ誤接続も避けている。

ただし、例Rを受入fixtureにするには、次の通常2件の補正が必要。どちらも形式の全面変更や範囲拡大は不要で、文言と対応する受入条件を絞って直せる。

## 3. 通常の指摘

### N-01：REPLAYの「元記録と同じ」がstate_afterまで固定してしまう

根拠：設計§8.5（370行付近）、§6のI-15、§8.9例R、依頼H-06／H-07。

§8.5はREPLAYで変えてよいものをseq・parent・event_hash・参照・replay_ofとし、例外としてDECLAREのfrontier／contextとRESTARTのfloorを挙げている。しかし**state_afterが例外にない**。このままなら、ACK／DECLAREを再生するときも旧state_afterをコピーする契約になる。

例Rでは、旧#4 APPLY D3は#3 RESTART_UNKNOWN直後から計算するので、state_after.base.as_of_dはnull。一方、新#8 APPLY D3はRESTARTをDROPしてD2から計算するので、state_after.base.as_of_dはD2。したがって、旧#5 ACKと同じstate_afterを新#9 ACKへコピーすると、新#8の状態とは必ず異なる。§6の「ACKは新しい親のstate_afterと同じ」および上位I-15を同時に満たせない。市場値をどのように選ぶかとは別に、baseの開始日で反例が確定する。

**最小補正案**：REPLAYで再計算する項目にstate_afterを追加する。ACK／DECLAREは新しい有効親のstate_after、RESTARTは初期状態とする。request_id／request_hash／request_basisや指紋は引き続き元のまま。旧記録は変更・削除しない。state_afterを持たせない案や、I-15を弱める案にしない。

**受入追加**：例Rの#9で、state_after==#8、state_after!=旧#5を明示する。旧#5のstate_afterを新#9へコピーした履歴は、hashを付け直してもstate_afterで拒否する。DECLAREの親状態が変わる再生も同じ規則で確認する。RESTARTは初期状態のままであることも対照にする。

### N-02：移行記録の無い新規v2履歴で、復元点の下限が未定義

根拠：設計§5.3（MIGRATIONなしの新規v2を許す）、§7のmake_history_genesis、§8.1（PはMIGRATION以後）、§8.9例R、依頼H-04〜H-06。

§8.1は復元点をSCHEMA_MIGRATION以後と無条件に定めている。しかし新規v2履歴にはMIGRATIONが無く、必須の例RにもMIGRATIONは存在しない。そのままでは、例Rを受理する検査器と、復元点制限を文字どおり守る検査器が分かれる。B-1は復元計画を作らなくても、復元記録の検査器を実装するため、この条件は今固定する必要がある。

**最小補正案**：D-2の制限を「MIGRATIONがある履歴ではP ≥ MIGRATIONのseq。ない新規v2履歴ではGENESISを下限」と明記する。有効な復元点だけ、P != k−1、requestバッチの途中は不可、という既存条件は維持する。新規履歴に意味のない移行記録を必須にしたり、例Rのseqを全面的に振り直したりしない。

**受入追加**：MIGRATIONなしの例Rは現行のseqのまま通る。MIGRATIONありではMIGRATION前を拒否、MIGRATION自身を含めた以後の適法な点を受理する。新規v2ではGENESISへの復元も他の条件を満たせば受理し、退避済み・直前・request途中の拒否は両方の履歴で維持する。

## 4. 任意提案

| ID | 根拠と提案 |
|---|---|
| P-01 schemaとPython型の試験を分ける | 依頼H-02の「Snapshotをvalidate_historyへ」「既存validate_snapshotはv2をunsupported_schema」は、渡すオブジェクトの型を具体化するとよい。既存validate_snapshotはまずisinstance(snapshot, Snapshot)を検査するため、新しいHistoryを直接渡すとsnapshot_invalid／typeになる。schema拒否の試験はHistory.from_dict(v1.to_dict())とSnapshot.from_dict(v2_history.to_dict())で行い、異なるクラスの直接渡しは型拒否として分ける。既存検査器を変更しない |
| P-02 確認時の不正入力とstaleの優先順 | 設計§5.6／依頼H-12の「入力が一つでも変わればstale」と、入力を再検査して既存エラーを保持する契約の関係を明記する。S3-Aと同じく、入力自体が不正なら再検査の既存エラー、有効な入力のdigest変更ならmigration_plan_stale、を推奨。あるいは確認時にstaleへ統一するならその変換を明記する。正常な変更・不正な変更を別の受入例にする |

提案を必須修正に混ぜない。取り込む場合も2文書内の補正だけでよい。

## 5. D-1／D-2／D-4への主担当の推奨（未採用）

| 判断 | 主担当の推奨 |
|---|---|
| D-1 形式とB-1の範囲 | 通常2件の補正後、この形式とB-1の限定範囲を採用することを推奨。7種の検査までで、計画生成は移行だけ、公開・B-2以降を含めない |
| D-2 復元点の制限 | **移行した履歴ではMIGRATION以後に限る**ことを推奨。N-02のとおり、新規v2にはGENESISを下限として明記する。既に退避した記録への再接続は引き続き禁止 |
| D-4 担当 | 仕様を補正・固定した後の実装はSonnet 5.5・highを推奨。範囲内で矛盾が見つかったら主担当へ返し、仕様変更を独断で実装しない |

これはユーザー採用ではない。今回のレビューをB-1実装の承認回答に置き換えない。D-3／D-5〜D-7は後続の留保のままでよい。

## 6. 実施・未実施

実施したのは固定文書と既存コードの読解、差分・blob・参照SHAの確認だけ。N-01は文書の再生条件と、既存transition.pyがbase_snapshotをどの状態から作るかの照合、N-02は新規履歴と復元点条件の突き合わせによる。S3-Bのコードはまだ無いため、実行による再現や合格確認はしていない。

実装・コード変更・試験実行・新市場計算・PR・Actions・本番接続・送信は行っていない。

## 7. 次の最小作業と保存

[Opus 5.5・highへの文書限定補正依頼](../tasks/V2_RECOVERY_S3B_DESIGN_CORRECTION_REQUEST.md)を具体化した。通常N-01／N-02を設計・依頼書へ反映し、例Rと受入条件の整合を確認する。追加の新保存機能・市場試験・B-1実装は行わない。補正後は指摘箇所を中心に確認して採否判断へ進み、全面設計レビューを自動で繰り返さない。

保存は別のレビュー資料ブランチへの本書と補正依頼の新規2文書だけ。対象588c841と既存参照を変更しない。保存前に25参照＋今回資料の計26件を照合し一致。保存後も同じ26件を照合する。
