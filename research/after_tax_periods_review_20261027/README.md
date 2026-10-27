# 税引後・別期間研究の主担当再現（2026-10-27）

資料開始7a564c583dcd018847d10db62881aaaabc44c348。
研究：research/after-tax-periods-20261027、
052ee96c898ecdef49204d61c46b7e66b77e4615。
[受領判断](../../docs/reviews/AFTER_TAX_PERIODS_RECEIPT_20261027.md)。

固定した研究ファイルと参照先を、一時コピーで同じ相対配置に置いて実行：

```powershell
Set-Location research/after_tax_periods_20261027
node run.mjs
python -X utf8 make_tables.py
```

主担当の環境はNode v24.22.1、Python 3.12.10、Windows。入力は保存済みの37a14c0のengine/入力3件/分配台帳、052ee96のspecification/reference、既存77bb44f summaryを使用。ネットワークは研究ソースの読取と公開資料の確認だけで、市場データを新規取得していない。スクリプトは出力を再生成するので元チェックアウトへ上書きせず一時コピーで行う。

[reproduction.json](reproduction.json)に全検証、13ファイルのGit blob比較、旧Open結果の税/清算/分配等を保存。

954件・失敗0、旧26重複一致を再現。13ファイル中10件完全一致。tables.mdは改行正規化で一致、environmentはNode、verificationはruntime_msだけ異なる。数値再現と、現金分配/課税/整数株の運用モデルとしての妥当性は別。

主担当は旧77bb44fの2024-10/2025-01開始×遅延0/1について、同じ税/分配/Openモデルの保存結果も別途抽出。税引後清算額では遅延0でP20 R25がNO_SELL I25を上回るが、遅延1では逆。主評価の問いに合わせ、時価と同日清算後を区別して説明する。

AT-01〜06のため、過去区間の順位やOpen/Close差を実売買の採用根拠にはしない。次の48セルは依頼作成までで、未実行。本番変更・起動・送信なし。
