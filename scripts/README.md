# scripts/ の契約

新しい補助スクリプトを足すときの共通ルール。場当たりな 1 回限りのコードを増やさず、同じ型で積み上げるためのもの。

## 追加の流れ（改善ループ）
1. 実行中に「scripts/ に無いのでその場でコードを書いた」「同じ確認を手で繰り返した」ことがあれば、レポートの実行ログに **手作業だった箇所** として残す。
2. 終了時に `../SCRIPT_BACKLOG.md` へ追記（既にあれば観測回数 +1）。**2 回以上・手順が安定・入出力が定型** の 3 つが揃ったらユーザーに scripts/ 化を提案する。
3. 承認後に作成 → `tests/fixtures/` に架空データのケースを追加 → `run_regression.py` が全ケース緑 → `../CHANGELOG.md` に 1 行 → バックログを done に。

スクリプト以外の穴（判断規則の不足＝プロファイル層、範囲外の定常業務＝スキル層 `../SKILL_BACKLOG.md`）も同じ 3 条件・承認制で扱う（SKILL.md 手順 8）。

## スクリプトの決まり
- **案件固有の値はハードコードしない**。必要なら `--profile` でプロファイル frontmatter から読む（`jira_sync_report.py` の `load_profile` / `pget` と同じ読み方）。
- 入力は JSON かファイルパス、出力は JSON と Markdown。**Jira には書かない**（書き込みは承認後に MCP で行う）。
- 終了コード: `0` 正常 / `1` 実行失敗・不一致 / `2` validate NG・入力不備。
- 冒頭 docstring に目的・usage・exit を書く。メッセージは日本語。
- 標準ライブラリ＋ PyYAML のみ。追加依存が要るときは README の「前提」に足す。
- **顧客名・人名・テナント ID を含めない**（コード・コメント・fixture とも）。コミット前に grep で確認する。

## 一覧
| スクリプト | 役割 | 手順 |
|---|---|---|
| `jira_sync_report.py` | content＋提案＋ダンプ → ドライラン md ＋ payload json、`--validate` | 5 |
| `check_desc.py` | 書き込み応答の Description を検査 | 6 |
| `profile_lint.py` | プロファイル frontmatter の検査（`--public` は見本用） | §8 |
| `run_regression.py` | fixtures を再実行し payload／report の一致を確認 | scripts/ 変更時 |
