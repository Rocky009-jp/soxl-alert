# V2 C-2 公開値と照合 設計案

作成日：2026-11-03（日本時間）。版：**第2版**（初版9dd64b8へのレビュー［docs/v2-history-publish-c2-review-20261103］の通常R-01〜R-03と提案P-01〜P-03を反映。方式・パッケージ・変更境界・件数は初版と同じ。改訂の一覧は§10）。
状態：**第2版・設計案・採否判断待ち。C-2の限定実装は未承認。C-3・C-4は対象外。**
Rockyさんの「C-2（公開値の照合）の設計・依頼書に進んでください」を受けて作成した。今回の作業は、設計書と限定実装依頼書の作成、一時環境での試行まで。文書の保存、推奨、試行の合格を、実装の承認とは扱わない。作成担当はClaude Opus 5.5、effort high（このスレッドのセッション設定）。

## 0. 要約

- **C-2の範囲**：v2履歴を後段のストア（C-3・C-4）が書く前に、何を書いてよいかを1つの不変の値「公開値」（HistoryPublication）として作る。あわせて、現在のバイト列に対する比較交換の検査（CAS）と、成否不明の後の読取り専用の照合を、純粋関数で定める。ファイル、ロック、パス、時計、乱数、通信は使わない。新しいパッケージ`v2_history_publish`だけを足し、既存のパッケージは変えない（D-1）。
- **作り方（D-2、レビューの提案P-01）**：公開値を作る関数（publish_\*）は、受け取った入力で**確認の手順そのものを自分で実行し**、その成功（日次はPREPARED、計画はCONFIRMED_IN_MEMORY）からだけ公開値を作る。History・確認結果・dictを受け取る関数は作らない。公開値に`from_dict`を設けない。こうすると、履歴の検査器（validate_history）は通るが計画は拒否する履歴（C-1レビュー§4.5の例）は公開値にならない。試行で確かめた（§7）。
- **公開値の形（D-3）**：書き方は3つ。APPEND（今の履歴に記録を足す）、CREATE（history.jsonが無いところに作る）、REPLACE（今のバイト列を置き換える）。作る元は7種で、DAILY・RESOLUTION・RESTART・RESTOREがAPPEND、GENESIS・MIGRATIONがCREATE、ADOPTIONがREPLACE。GENESISは前の方針案（a6340c3 §5.2）に無かった元で、C-3の空のrootの初期化に要るので加える。
- **バイトの形（D-4）**：書くバイトは正規化テキストのUTF-8（BOMなし、末尾改行なし）。読むときは厳格に（UTF-8、既存decode_history、既存validate_history）読むが、正規化されていない有効なテキストも受け付ける（S2の読み方とB-5aの診断に合わせる）。APPENDの「今」は正規化digestと先頭で、REPLACEは生バイトのsha256と長さで、CREATEはファイルが無いことで照合する。
- **照合（D-5）**：成否不明の後に読み直したバイト列を、PUBLISHED（候補そのもの）、PUBLISHED_THEN_EXTENDED（候補が物理prefixで後に記録が続く）、NOT_PUBLISHED（まだ期待した今のまま）、CONFLICT（それ以外。読めないファイルを含む）の4つに分ける。誰が書いたかは示さず、通知の権利も与えない。
- **P-02の規則1〜4（D-6）**：NO_CHANGEからは公開値を作らない。採用の公開値は元バイトでCONFIRMED_IN_MEMORYを得たときだけ作り、期待する生バイトの識別値は受け取ったバイトから計算する（計画の値は一致を確かめるだけ）。公開値の本文に`discarded`・`diagnosis_digest`を持たせない。規則4の退避の部分はC-4の受入条件に残す。
- **範囲試験（D-7）**：C-1の範囲試験test_c1_09のENDをde6549aに固定する。試行で、**ENDの1行だけではC-1の範囲試験が1件失敗する**ことが分かった（自分のファイルをREVで読み直す試験が、固定後はEND=Noneの版を読む。§6.2）。読み直しをHEADにする1行を足して、計2行の補正とする。C-2の範囲試験は新しい開いた範囲（START=de6549a、END=None）で書き、自分の読み直しはHEADから行い、「次の段階がENDを1行で固定し、自分の開いた範囲試験を足しても通る」ことを使い捨てのコミットで確かめる（第2版で仮の開いた範囲試験を足す形に改めた。§6.3）。C-1レビューの提案P-03（r4_09）は、r4_09を触らないので戻さない。
- **一時環境での試行**：de6549aのコピーにC-2を試作した（pushしない）。既存12スイート1780件がPython 3.12.3と3.13.18で全件合格（test_c1_09の2行の補正を含む）。7種の作り方・CAS・照合・P-01・P-02の53項目（使い捨てのプローブ）がすべて期待どおりだった。公開値の各欄を変な型にする2,660通りの試しで、最初の試作に想定外の例外（sourceがlist・dictのときのTypeError）が見つかり、1行直して0件になった。受入C2-14はこの種の漏れを見るためのもの（§7）。ただしこの試しは型だけを替えたもので、整数の値の範囲は見ていない。レビューで、負のcandidate_head_seqで照合がIndexErrorを漏らすことが分かった（第2版で形の規則とC2-14に加えた。§5.2、§10）。
- 運用方針は日足のみ（早朝に米国の確定日足で通知し、夜の寄付きで手動購入）。分足・NBBOは前提にしない。公開値も日次の処理1つと人の保守操作だけを書き手として想定する。
- 採否はD-1〜D-8の一組（§8）。

## 1. 目的と固定入力

| 用途 | 固定版 |
|---|---|
| 起点（コード・試験） | **de6549acb4ecea759cc771300fd0bef59dd5456a**（feat/v2-history-consume-c1-20261103）。C-1の試験対象3f780c1に結果文書1本を足した保存最終 |
| C-1の受領 | レビューb473db46ad3dbf3ad76fa76f50c49b03b558936d（docs/v2-consume-c1-review-20261103、docs/reviews/V2_CONSUME_C1_REVIEW_20261103.md、重大0・通常0・提案3、受領推奨）。de6549aで受領済み（2026-11-03） |
| 上位の分割と方針 | a6340c3937092e4cb658913b9acfb4973a084326（docs/v2-consume-s3c-20261103）のdocs/specs/V2_CONSUME_S3C_DESIGN_DRAFT.md。D-1〜D-6はRockyさんが2026-11-03に採用。特に§4（P-02の規則1〜5）、§5.1（日足の運用から決まること）、§5.2（C-2の方針案）。D-4のとおり§5は方針案で、C-2の中身は本書で決める |
| 範囲試験の規則 | 08072cc47aa12340ed947d40f02ca8741a4060d6のdocs/specs/V2_SCOPE_RANGE_FREEZE_DESIGN_DRAFT.md §6（D-3）、再レビュー9fe3e1931ea88dc7b4cf46a20e82ad01dd42827d §4 |
| B-5b再レビュー | 003b6dc9ab16a0a615fb653bed1b2b78e2ba822b §5 P-02 |
| S3-B第2版 | 361904b1618ae9f9d3a672875c437a388826c253 §9（公開・照合の方針、D-7） |
| 運用方針 | 日足単位の判定。早朝に米国市場の終値で通知し、夜の寄付きで買う。分足・NBBOは前提にしない（2026-10-26） |

読解対象：de6549aのv2_history（values.py、validate.py、migrate.py、genesis.py）、v2_history_ops（batch.py、plan.py、daily.py、values.py、errors.py）、v2_history_restart（values.py、confirm.py）、v2_history_restore（confirm.py、errors.py、values.py）、v2_history_adopt（confirm.py、build.py、values.py）、v2_history_diagnose（diagnose.py）、v2_persistence（errors.py、codec.py、local/store.pyの読込み）、試験のc1_helpers・r4_helpers・r3_helpers・ho_helpers・a5_helpers・h_helpers・test_c1_09・test_sc_02・sc_helpers、上の各文書、C-1のレビューと確認スクリプトc1_division.py。共通のCLAUDE.mdも確認した。取得できなかったファイルは無い。

## 2. C-2の範囲（D-1）

### 2.1 前の段階が残したもの

- B-2のHistoryAppendBatchは「追記する記録」の値で、check_append_batchで純粋に検査できる。ただし作り手はDAILYとRESOLUTIONだけで、ストアは受け付けない（committedは常にFalse）。
- B-3（再開始）・B-4（復元、C-1でCONSUMEを含む）の確認結果は、候補Historyだけを返し、追記の値を持たない。
- 移行（B-1のconfirm_migration_plan）は、v1のSnapshot値から候補Historyを作る。元のsnapshot.jsonのバイトとは結び付いていない。
- 採用（B-5b）は元バイトから候補Historyを作るが、元バイトとの照合と退避はS3-Cへ送られた。
- S3-B第2版§9.4は、成否不明の後の照合を「同じ親hash」で判断する案を退け、照合をS3-Cで決めるとした。

### 2.2 C-2がすること・しないこと

| する | しない（C-3・C-4・S4） |
|---|---|
| 7種の確認済みの結果から、1種類の公開値を作る | ファイルの読み書き、ロック、一時ファイル、fsync、replace、パス |
| 今のバイト列（または「無い」）に対するCASの検査を、純粋関数で行い、候補Historyを返す | v1のsnapshot.jsonの退避、MANIFEST、quarantine |
| 成否不明の後に読み直したバイト列を4つに分ける | 自動の再試行、解錠、再開の実行 |
| 書くバイトの形と、厳格な読み方を1か所に定める | 本番の保存先、通知、Actions |

C-2はC-3の前提だが、C-3がまだ無くても、公開値の作り方とCASの規則を独立に試験できる。

### 2.3 パッケージ

新しいパッケージ`v2_history_publish`（ファイル案：`__init__.py`、`values.py`、`errors.py`、`read.py`、`build.py`、`check.py`の6本）。依存は標準ライブラリ（copy、hashlib）と、変更しないv2_core・v2_persistence・v2_recovery・v2_history・v2_history_ops・v2_history_restart・v2_history_restore・v2_history_adopt。v2_history_diagnoseは直接importしない（採用の確認が内部で使うだけ）。hashlibは生バイトの識別値を計算する`read.py`だけで使う（B-5aの診断と同じ扱い）。

既存のパッケージ・試験・ヘルパーは変えない。例外は§6の範囲試験の補正（test_c1_09の2行）だけ。

## 3. 公開値の作り方（D-2、P-01）

### 3.1 原則

1. **確認を自分で実行する**：publish_\*は、受け取った入力で既存の確認の関数を呼ぶ。呼び出し側が持ってきた確認結果を信用しない。確認結果のクラス（RestoreConfirmResult等）は誰でも作れるので、型やstatusを見ても、確認が行われたことの証明にならないからである。
2. **肯定の結果からだけ作る**：日次はPREPARED、計画はCONFIRMED_IN_MEMORYだけ。NO_CHANGE、NO_COMMIT、ALREADY_APPLIEDは`publication_refused`で拒否する（呼び出し側は「書くものが無い」と分かる）。確認の拒否（plan_mismatch、stale、restore_invalid等）は、既存のcode・ruleのまま返す。
3. **Historyやdictから作る関数を作らない**：検査器を通っただけの履歴を書く経路を、APIとして持たない。公開値には`from_dict`を設けない（B-2のHistoryAppendBatchには伝言・試験用のfrom_dictがあるが、公開値は同じプロセスの中で作って使うだけ。中断後の再開は、C-4で計画と入力から作り直す）。値を作る内部の関数（`_make`）を呼ぶのは`build.py`だけとし、範囲試験で静的に確かめる。
4. **候補を作り直さない**：候補は確認の関数が返したものを使う。公開値の関数は、候補が今の履歴の物理的な延長であること（APPEND）と、候補の各digestを計算し直して書くだけで、戦略の式・台帳の規則・記録の作り方を複製しない。

### 3.2 7つの関数

| 関数 | 実行する確認 | 書き方 | 公開値に入れる元の値 |
|---|---|---|---|
| `publish_day(history, d, series, sessions, raw_observations)` | prepare_history_day → PREPAREDのbatchをcheck_append_batch | APPEND | d |
| `publish_resolution(plan, confirmed_plan_hash, history, sessions, raw_observations)` | confirm_history_resolution_plan → CONFIRMED_IN_MEMORYのbatchをcheck_append_batch（確認結果のhistoryと一致） | APPEND | request_id、plan_hash |
| `publish_restart(plan, confirmed_plan_hash, history, sessions, raw_observations)` | confirm_restart_plan | APPEND | request_id、plan_hash |
| `publish_restore(plan, confirmed_plan_hash, history, sessions, raw_observations, series)` | confirm_restore_plan（C-1のCONSUMEを含む） | APPEND | request_id、plan_hash |
| `publish_genesis(start_after, sessions)` | make_history_genesis | CREATE | なし |
| `publish_migration(plan, confirmed_plan_hash, snapshot_data, resolutions, sessions, raw_observations)` | snapshot_dataをS2と同じ厳格さで読む（UTF-8、decode_snapshot、validate_snapshot）→confirm_migration_plan | CREATE（v1の元バイトつき） | request_id、plan_hash、source_v1 |
| `publish_adoption(plan, confirmed_plan_hash, data)` | confirm_prefix_adoption → CONFIRMED_IN_MEMORYだけ | REPLACE | request_id、plan_hash |

APPENDの共通処理：今の履歴を検査し、候補の物理記録の先頭n件（nは今の履歴の記録数）で作った履歴のdigestが今の履歴のdigestと同じことを確かめ（候補が今の延長であること）、n件目以降を`records`とする。

移行の元は、v1のsnapshot.jsonの**バイト**で受け取る（P-02の規則3と同じ考え方で、公開値を作るときに使ったバイトと、C-4が退避するバイトを、識別値で結ぶため）。resolutions（S3-Aの値）は従来どおり値で受け取る。

### 3.3 P-01の境界（C-1レビュー§4.5）

再開始をREPLAYし、REAPPLY D4の後にD5をCONSUMEする復元を考える。計画は`restore_consume_not_released`（D5）で拒否するが、独立のビルダーで書いた同じ履歴を、検査器は受け付ける（D-2(ii)の分担どおり）。C-2では次のどの経路でも、この履歴は公開値にならない。

- `publish_restore`に、正しい計画（同じ入力でREADYになる計画）のbasisを書き換えてこの履歴を候補にし、hashを付け直した計画を渡す → 確認の作り直しで拒否される。
- RestoreConfirmResult(CONFIRMED_IN_MEMORY, この履歴, …)を作って渡す → 計画ではないので確認の段階1で拒否（history_plan_mismatch）。
- この履歴を直接受け取る関数は無い。公開値のfrom_dictも無い。

試行のプローブで3つとも確かめた（§7）。受入条件C2-10で固定する。

## 4. 公開値の形（D-3）

### 4.1 値

`HistoryPublication`は不変の`{body, publication_hash}`。publication_hashはbodyの正規化JSONのSHA-256（B-2のbatch_hashと同じ作り方）。既存の_Frozen（v2_history_ops.values）の型に乗る。committedは常にFalse。summary()とreprは、書き方・元・日・依頼ID・記録数・候補の先頭番号・hashだけを出す（市場値、F&G、決定、自由文、ファイル名を出さない）。

### 4.2 body（14キー、operation "soxl-v2-history-publication/1"）

| キー | APPEND | CREATE | REPLACE |
|---|---|---|---|
| operation | 固定語 | 同左 | 同左 |
| mode | "APPEND" | "CREATE" | "REPLACE" |
| source | DAILY／RESOLUTION／RESTART／RESTORE | GENESIS／MIGRATION | ADOPTION |
| d | DAILYだけ日付、他はnull | null | null |
| request_id・plan_hash | 計画の元だけ値、DAILYはnull | MIGRATIONだけ値、GENESISはnull | 値 |
| expected | {head_seq, head_hash, history_digest} | null | {raw_sha256, raw_size} |
| source_v1 | null | MIGRATIONだけ{raw_sha256, raw_size}、GENESISはnull | null |
| records | 足す記録（1件以上） | null | null |
| candidate_history | null | 候補全体 | 候補全体 |
| candidate_head_seq・candidate_head_hash・candidate_digest・candidate_state_digest | 候補から計算 | 同左 | 同左 |

sourceとmodeの対応は固定（表のとおり）で、違えば`publication_invalid`／mode。

### 4.3 B-2の追記値との関係

DAILY・RESOLUTIONの公開値は、B-2のHistoryAppendBatchをcheck_append_batchで検査して得た候補から作る。batchの値はそのまま使わず、公開値は別の型にする（batchはcommittedを持たない検査用の値として残し、B-2の型・規則を変えない）。試行で、DAILYの公開値のrecordsがbatchのrecordsと同じ文字であることを確かめた。

## 5. バイト・CAS・照合（D-4、D-5）

### 5.1 バイトの形と読み方（`read.py`）

- `history_bytes(history)`：既存encode_historyの正規化テキストをUTF-8にしたもの。BOMも末尾改行も付けない。
- `read_history_bytes(data)`：`bytes`だけを受け付け、UTF-8（BOMは取り除かない）→既存decode_history（重複キー、NaN、深さ、巨大整数を拒否）→既存validate_historyで完全に検査し、(History, HistoryCheck)を返す。拒否は既存の`history_invalid`（UTF-8の誤りはrule="utf8"）。
- 正規化されていない有効なテキスト（例：字下げ付き）も読む。S2のsnapshot.jsonの読み方とB-5aの診断（canonical_textは情報として出すだけ）に合わせる。読んだ内容の識別は正規化テキストのdigestで行い、書くときは正規化する。
- `raw_identity(data)`：`{raw_sha256, raw_size}`を、受け取ったバイトからhashlibで計算する。計画の値は写さない。

### 5.2 CASの検査 `check_publication(current, publication, source_v1=None)`

currentは、C-3・C-4がロックの下で読み直したhistory.jsonのバイト、または「無い」ことを表すNone。source_v1は移行のときだけ、同じロックの下で読んだsnapshot.jsonのバイト。

順序：
1. 公開値そのもの：型（HistoryPublicationだけ）、bodyの14キー、operation、sourceとmodeの対応、publication_hash、各hashの形、書き方ごとの欄の形。違えば`publication_invalid`。**整数の欄の範囲も形に含める**（第2版、レビューR-03）：candidate_head_seqは0以上で、APPENDでは`expected.head_seq + len(records)`、CREATE・REPLACEでは`candidate_history`の`events`の件数−1と同じ（eventsがlistでなければ形の誤り）。expected.head_seqは0以上、raw_sizeは0以上。違えば`publication_invalid`／shape。照合（§5.3）も同じ形の検査を共有する。
   続けて**引数の誤用**を見る（第2版、レビューP-03。今の比較より先）：currentが`bytes`でもNoneでもなければ`publication_invalid`／current_type。移行以外の公開値にsource_v1（None以外）を渡したら`publication_invalid`／source_v1。移行の公開値でsource_v1が`bytes`でもNoneでもなければ`publication_invalid`／source_v1。
2. 今との比較：

   | 書き方 | 受け付ける今 | 違うとき |
   |---|---|---|
   | APPEND | currentを厳格に読み、正規化digest・head_seq・head_hashがexpectedと同じ | 無い→`publication_stale`／absent、違う→／head。読めない・無効は既存のhistory_invalid |
   | CREATE | currentがNone。MIGRATIONはsource_v1の識別値がsource_v1と同じ | ある→／present、v1が無い・違う→／source_v1 |
   | REPLACE | currentの生バイトの識別値がexpectedと同じ（今のバイトは壊れていてよい） | 無い・違う→／raw |

   （source_v1の誤用は手順1で見る。移行でsource_v1がNone、または識別値が違うときが／source_v1のstale。）
3. 候補：APPENDは今の記録＋records（seqが続くこと）、他はcandidate_historyからHistoryを作り、既存validate_historyで完全に検査し、4つの候補値が一致すること。違えば`publication_invalid`／candidate_digest、recordsの形の誤りは／records。

戻り値は候補History。C-3はこれをhistory_bytesで書く。check_publicationは**計画を確認し直さない**。公開値が作り手の作ったものであること（形とhash）と、今が期待どおりであることだけを確かめる。確認は作り手だけが行う（§3.1）。

### 5.3 照合 `reconcile_publication(current, publication)`

replaceの呼出しの開始以後に失敗したとき（成否不明）に、読み直したバイト列で判断する。公開値の形の誤りだけは`publication_invalid`で拒否し、中身の問題はすべて値で返す（例外にしない）。

| 結果 | 条件 |
|---|---|
| PUBLISHED | currentを厳格に読めて、正規化digest・先頭が候補と同じ |
| PUBLISHED_THEN_EXTENDED | currentの先頭から候補の記録数だけの物理prefixのdigestが候補と同じで、その後に記録が続く |
| NOT_PUBLISHED | CREATEでcurrentがNone。REPLACEで生バイトの識別値がexpectedと同じ。APPENDで正規化digest・先頭がexpectedと同じ |
| CONFLICT | それ以外。CREATE以外でcurrentがNone、読めない・無効なcurrentを含む |

- PUBLISHED_THEN_EXTENDEDの「物理prefix」は、今の先頭candidate_head_seq＋1件だけで作った履歴のdigestが、公開値のcandidate_digestと同じことで判断する。有効な今では記録のhashが鎖になっている（各event_hashはseqと直前の記録のhashを含む）ので、正直な公開値ではこれと「位置candidate_head_seqの記録のhashがcandidate_head_hashと同じ」は同じ結果になる。両者の違いは、candidate_head_hashとcandidate_digestが食い違う（hashを付け直した）公開値でだけ現れ、物理prefixの判定ではCONFLICTになる（第2版、レビューR-02）。

- 判断の順序はREPLACEの「まだ元のまま」を最初に見る（元のバイトは壊れていて読めないため）。
- NOT_PUBLISHEDは「同じ公開値でもう一度試してよい」を意味するが、C-3はもう一度ロックの下でcheck_publicationを通してから書く。照合だけで書かない。
- 誰が書いたかは示さない。PUBLISHEDでも、通知の権利や「この処理が書いた」ことの証明にはしない。S1の「同じ親hash」条件は使わない（S3-B第2版§9.4）。
- 戻り値`Reconciliation`はoutcomeとpublication_hashだけを持つ不変の値。

### 5.4 日足の運用での使われ方（C-3以降の想定。C-2では実装しない）

早朝の定時処理：ロック→読み→`read_history_bytes`→`publish_day`→`check_publication`→書く→replace。replaceが成否不明なら`reconcile_publication`。PUBLISHEDならその日の通知へ進んでよいかはC-3／S4で決める（照合は通知の権利を与えない）。CONFLICTなら保存できなかったこととして通知し、前日値で埋めない。保守（再開始・復元・採用・移行）は日中に人が行い、同じ型をpublish_restart等で使う。

## 6. 範囲試験（D-7）

### 6.1 前の段階の固定

tests/v2_history_consume/test_c1_09_scope.pyの`END = None`を、受領した最終コミットの完全SHAに替える。

    END = "de6549acb4ecea759cc771300fd0bef59dd5456a"   # accepted (review b473db4); frozen when C-2 began

### 6.2 試行で見つかったこと：ENDの1行だけでは足りない

ENDだけを固定すると、test_c1_09のChain.test_the_range_values_of_this_file_are_those_read_from_the_textが失敗する。この試験は自分のファイルを`C.show(REV, …)`で読み、そこに書かれたENDが実行中のENDと同じことを確かめる。固定後はREV＝END＝de6549aになり、de6549aの版のファイルには`END = None`と書かれているので、(True, None) ≠ (True, de6549a…)となる。

C-1のレビュー（b473db4）は、範囲の鎖の試験をSTARTを戻した使い捨てのコミットで確かめたが、「次の段階がENDを固定した後」の模擬は行っていなかった。範囲試験の固定（08072cc）の規則は「次の段階はENDを1行で固定する」なので、この試験はその規則に合っていない。

補正：同じ試験の読み直しを`C.show("HEAD", …)`にする1行（試行で確認）。HEADのファイルには固定したENDが書かれているので、実行中の値と一致する。ほかの試験はREV（＝de6549a）を読んだまま変えない。test_c1_09の差分は計2行（ENDの1行と、この1行）。

    tree = ast.parse(C.show("HEAD", NEW_DIR + "test_c1_09_scope.py"))   # HEAD: the frozen END is read as written

### 6.3 C-2の範囲試験

- 新しいディレクトリ`tests/v2_history_publish/`に`test_c2_*.py`と`c2_helpers.py`を置く。`__init__.py`は作らない。
- 範囲試験は`START = "de6549acb4ecea759cc771300fd0bef59dd5456a"`、`END = None`、`REV = END or "HEAD"`。git差分・中身・blob・一覧をREVから読み、作業ツリーを読まない。前の段階の差分を固定文字列で書き写さない。test_c1_09の2行の補正は、C-2自身の差分のハンクとして固定する。
- **自分のファイルの読み直しはHEADから行う**（§6.2の教訓）。範囲の値（START・END）を読む試験は、HEADのテキストと実行中の値を比べる。
- **次の段階の模擬**（第2版、レビューR-01）：受入の一部として、使い捨てのコミットで、(1) C-2の範囲試験のENDだけを自分の試験対象のSHAに替え（1行）、(2) 次の段階の**仮の開いた範囲試験**1本（START＝(1)で固定したSHA、END=None、`class FilesChanged`を持つ最小のもの。置き場所は使い捨ての`tests/v2_next_stage/`）を足し、test_sc_\*・test_c1_\*・test_c2_\*が通ることを確かめる（C2-19）。実際の次の段階も、ENDの固定と自分の開いた範囲試験を同じコミットで足すので、これが正しい模擬になる。(2)を足さずに開いた範囲が0本になると、範囲の鎖の試験（test_sc_02のChainJudgeの2件。開いた範囲がもう1本あることを前提に「open range」の問題を期待する）が「2 chain beginnings」で失敗する。これは次の段階では起きない形なので、test_sc_02を直さない。模擬は結果文書のコミットの前に試験対象のSHAで行い（範囲試験は結果文書を必須にしないので通る）、保存最終のSHAでの再現はレビューで行う。
- 範囲の鎖（test_sc_02）は新しい範囲試験を自動で見つける。鎖は`adfdf765→…→b626c98→bfbde7a→de6549a→（C-2、END=None）`になる。試行で、仮の範囲試験1本で鎖が通ることを確かめた。
- C-1レビューの提案P-03（r4_09のファイル一覧の固定を戻す）は、C-2でr4_09を触らないので扱わない（次にr4_09を触る機会のまま）。

## 7. 一時環境での試行（2026-11-03、Linux）

**位置づけ**：方式の確からしさを確かめるための使い捨ての試行。de6549aから作ったローカルの作業ツリーに、`v2_history_publish`（6ファイル、+471行）を試作し、test_c1_09の2行の補正と、仮の範囲試験1本（STARTがREVの祖先であることだけを見るもの）を加え、pushしないローカルコミットで試験した。正式な実装、受入試験、欠陥注入、レビューの代わりにしない。

環境：Linux、Python 3.12.3と3.13.18、`PYTHONDONTWRITEBYTECODE=1`、`-B -W error::ResourceWarning`。Windows、3.10・3.11、unshareによる通信遮断は実施していない。

| スイート | 試作後（3.12／3.13） |
|---|---|
| コア tests/v2_core | 197 OK |
| 保存 tests/v2_persistence | 170 OK |
| S2 tests/v2_persistence_local | 113 OK（skip 4、Windows専用） |
| S3-A tests/v2_recovery | 176 OK |
| B-1 tests/v2_history | 230 OK |
| B-2 tests/v2_history_ops | 173 OK |
| B-3 test_r3_\* | 109 OK |
| B-4 test_r4_\* | 165 OK |
| B-5a test_d5_\* | 131 OK |
| B-5b test_a5_\* | 170 OK |
| 範囲の鎖 test_sc_\* | 34 OK |
| C-1 test_c1_\* | 112 OK（test_c1_09を2行補正） |
| 合計 | **1780件合格**（仮の範囲試験1件は別） |

補正の前（ENDの1行だけを固定した時点）は、C-1の1件（§6.2）が失敗した。ほかは変更なしに合格した。

**プローブ（53項目、3.12・3.13ともすべて期待どおり）**：

- DAILY（20項目）：公開値の候補がB-2のbatchを受け入れた結果と同じ。recordsがbatchのrecordsと同じ文字。今が候補・無い・別の履歴のときのstale。照合の4結果（前、後、後に1日足した履歴、無い、壊れたバイト、別の履歴）。既に適用した日のnot_prepared。字下げ付きの有効なバイトを受け付ける。strのcurrent、BOMの拒否。hashの誤り、recordsを書き換えてhashを付け直した値（候補の検査で拒否）、dictの拒否、from_dictが無いこと。
- RESOLUTION・RESTART・RESTORE（12項目）：候補が確認結果と同じ。NO_CHANGEのpublication_refused。確認hashの誤りはhistory_plan_mismatchのまま。RESTOREはC-1のCONSUMEを含む例（DROP 4、CONSUME D3、REAPPLY 5）で、recordsが復元記録と作られた2件。台帳を変えると拒否。
- P-01（5項目）：§3.3の3経路すべて拒否。publish_\*の一覧が7つで、Historyを受け取る関数が無い。
- GENESIS（4項目）・MIGRATION（4項目）：CREATE、ある場合のpresent、照合のNOT_PUBLISHED／PUBLISHED、v1のバイトが無い・違うときのsource_v1、移行以外にv1を渡したときの拒否。
- ADOPTION（8項目）：REPLACE、expectedが受け取ったバイトから計算した値、NO_CHANGEのpublication_refused、別のバイトのraw、照合の前・後、bodyに`discarded`・`diagnosis`の名のキーが無いこと、候補が元バイトでの確認結果と同じこと。

**型の試し（2,660通り）**：3つの書き方の公開値について、bodyの各欄（APPENDは各記録の各欄も）をNone・数・真偽・空文字・list・dict等に替え、hashを付け直して、check_publication・reconcile_publication・summary・reprを呼んだ。最初の試作は、sourceがlist・dictのときに`body["source"] not in MODE_OF`でTypeError（unhashable）を出した（36件）。sourceの型を先に確かめる1行で直し、0件になった（型の試しに限る。整数の値の境界はレビューで別に見つかった。§10のR-03）。直した後に、プローブ53項目と全スイートを両方の版でもう一度通した。

試作の差分（8ファイル、+492／−2行、仮の範囲試験を含む）は、同じ資料コミットのdocs/specs/V2_HISTORY_PUBLISH_C2_TRIAL_20261103.diffに参考として保存する（未適用。SHA-256は§9）。実装者はこれを写すのではなく、本書と依頼書の規則に従って作り、違いがあれば結果文書で説明する。試作は受入試験・欠陥注入・正式な範囲試験・名前の整理を含まない。

## 8. 採否

| ID | 判断 | 推奨（未採用） |
|---|---|---|
| D-1 | C-2の範囲：公開値・CAS検査・照合・バイトの形だけを純粋関数で作る。新しいパッケージv2_history_publish、既存パッケージは不変（§2） | 採用を推奨。C-3のファイル操作と切り離して試験できる |
| D-2 | 作り方：publish_\*が確認を自分で実行し、PREPARED／CONFIRMED_IN_MEMORYからだけ作る。History・確認結果・dictを受け取る関数とfrom_dictを作らない。NO_CHANGE等はpublication_refused（§3） | 採用を推奨（P-01）。(i)確認結果の値を受け取る案は、結果のクラスを誰でも作れるので推奨しない |
| D-3 | 公開値の形：3つの書き方×7つの元、body 14キー、operation "/1"、APPENDはrecordsだけ、CREATE・REPLACEは候補全体。GENESISを元に加える（§4） | 採用を推奨 |
| D-4 | バイトの形と読み方：正規化UTF-8で書き、厳格に読み、正規化されていない有効なテキストは受け付ける。今の照合はAPPEND＝正規化digestと先頭、REPLACE＝生バイトの識別値、CREATE＝無いこと（MIGRATIONはv1の識別値も）（§5.1、§5.2） | 採用を推奨。正規化されたテキストだけを受け付ける案は、手で整形した有効なファイルがC-3でも採用でも扱えなくなるので推奨しない |
| D-5 | 照合：4つの結果、読めない今はCONFLICT、NOT_PUBLISHEDでも書く前にCASをやり直す、誰が書いたかと通知の権利を示さない（§5.3） | 採用を推奨 |
| D-6 | P-02の規則1〜4とP-01：NO_CHANGEから作らない、採用は元バイトのCONFIRMED_IN_MEMORYだけ、識別値は受け取ったバイトから計算、本文にdiscarded・diagnosis_digestを持たない。規則4の退避の部分はC-4へ（§3.3、§4、§5.1） | 採用を推奨 |
| D-7 | 範囲試験：test_c1_09のEND＝de6549aと自己読直しのHEAD化（計2行）、C-2の範囲試験はSTART＝de6549a・END=None、自己読直しはHEAD、次の段階の模擬（ENDの1行固定＋仮の開いた範囲試験1本、第2版）を受入に含める。P-03は扱わない（§6） | 採用を推奨。2行目は1行固定の規則の例外で、理由は§6.2 |
| D-8 | C-2の実装単位と担当：対になる依頼書の範囲（新しいパッケージ、新しい試験ディレクトリ、test_c1_09の2行、結果文書）。担当はSonnet 5.5・high | 採用を推奨。規則と試行の差分が具体的で、既存の型（plan→confirm、_Frozen）に乗る。矛盾や規則の追加が必要なら止めて主担当へ返す |

D-1〜D-8を一組で判断する。今回の文書作成と一時環境の試行は採用ではない。C-1の受領を、C-2の実装承認にしない。C-3・C-4、全体稼働、本番の保存先・資格情報・通知は今回の採否に含まない。

範囲外として残すもの：C-1レビューの提案P-02（結果文書の記述ずれ。受領記録の注記で扱う）とP-03（r4_09）、B-4§7.1の既知の制限（案a）、B-5b再レビューのP-01（a5_09）、範囲試験の固定のレビューのP-02（git_show_at_endの本文）、U-03、U-07、a6340c3 §5.5の未決（C-4の依頼前に判断）。

既知の制限：Pythonでは、内部の`_make`や`object.__new__`を直接呼べば公開値の形をした値を作れる。C-2はこれを防がず、作り手以外が`_make`を呼ばないことを範囲試験の静的監査で確かめる。C-3は自分のプロセスで作った公開値だけを受け取る。**check_publicationは確認ではない**：`_make`で作った値は、検査器だけを通った履歴（§3.3）を候補にしていても、形とhashと今が合えば受け付けられる（レビューのプローブで確認）。第2版では、この性質を特性の試験として1件固定し（C2-10）、C-3の依頼書に「C-3は同じプロセスでpublish_\*が返した値だけを受け取り、範囲試験でv2_history_publish/build.py以外が`_make`・`object.__new__(HistoryPublication)`を呼ばないことを監査する」を受入として引き継ぐ（レビューP-01）。

C-4への引継ぎ（第2版）：採用のREPLACEがreplaceの後で中断すると、元バイトはhistory.jsonから消えている。照合に要る公開値は、C-4がquarantineへ写した元バイトからpublish_adoptionで作り直す。今のバイトでの確認はNO_CHANGE（publication_refused／no_change）になり、これがa6340c3 §4の規則3の「すでに候補である」に当たる。a6340c3 §5.4の順序（退避先へ写してfsyncしてからreplace）がこれを可能にするので、C-4の依頼書でこの手順を受入にする。

## 9. 作業記録

- 担当モデル：Claude Opus 5.5、effort high（このスレッドのセッション設定）。
- 開始時（2026-11-03T13:40Z）に、C-1依頼書§7の70参照＋docs/v2-consume-s3c-20261103（a6340c3）＋feat/v2-history-consume-c1-20261103（de6549a）＋docs/v2-consume-c1-review-20261103（b473db4）の計73参照を、`git ls-remote`の完全SHAで照合し、73件とも一致した。終了時の照合は依頼書§7と結果の報告に記す。
- 本書、依頼書、試行の差分の3ファイルだけを、de6549aから作った新しい資料ブランチdocs/v2-history-publish-c2-20261103に追加した。製品コードの変更、PR、Actions、送信、新しい市場計算は0。一時環境の作業ツリーとローカルコミットはpushしていない。
- 試行の差分docs/specs/V2_HISTORY_PUBLISH_C2_TRIAL_20261103.diffのSHA-256は 7bfd3a80534c0e7fc3f2618db1894bd05883aed00c29449cc886cc219554b0ba（一時環境のde6549a→試作後の`git diff`の出力そのまま。対象はv2_history_publish、tests/v2_history_consume/test_c1_09_scope.py、tests/v2_history_publish）。
- モデル別の利用量は未計測。

## 10. 第2版の改訂（2026-11-03）

初版9dd64b8へのOpus 5.5・highのレビュー（a6e783e57c1de5dd92e6b43cfc416a1d79a672eb、docs/reviews/V2_HISTORY_PUBLISH_C2_DESIGN_REVIEW_20261103.md、重大0・通常3・提案3、「依頼書の限定改訂が先」）を、レビューの推奨どおり反映した。方式（D-1〜D-6）、パッケージ、変更境界、件数、試行の差分は変えていない（試行の差分は初版のまま参考として残す。下の2点は試行のコードに残っているので、写さない）。

| レビュー | 改訂した箇所 | 内容 |
|---|---|---|
| R-01（通常） | §6.3、§8 D-7、依頼書C2-19 | 次の段階の模擬に仮の開いた範囲試験1本を足す。模擬は試験対象のSHAで行う |
| R-02（通常） | §5.3、依頼書C2-12・欠陥注入15 | 物理prefix判定と記録のhashの判定は、正直な公開値では鎖のため同じ結果になる。区別はcandidate_head_hashとcandidate_digestが食い違う公開値で行う |
| R-03（通常） | §5.2手順1、依頼書§3・C2-14 | candidate_head_seq等の整数の範囲を形に含める。試行のreconcile_publicationは負のcandidate_head_seqでIndexErrorを漏らす |
| P-01（提案） | §8既知の制限、依頼書C2-10 | check_publicationが`_make`の値を受け付けることを特性の試験で固定し、C-3へ引き継ぐ |
| P-02（提案） | 依頼書§5の3・4・5 | 実物の確認の関数の下では等価。代役で検出するか、理由を書いて等価とする |
| P-03（提案） | §5.2手順1・2、依頼書§3 | 引数の誤用（current・source_v1）を今の比較より先に見る。試行は今の比較の後で見ている |

