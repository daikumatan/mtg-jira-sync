# tests/fixtures

`scripts/run_regression.py` が読む回帰ケース。ここに置くのは **`examples/` のプロファイルと架空データだけ**。
実案件の fixture（実データ・実プロファイル）はリポジトリの外（例: 作業ディレクトリの `jira_profiles/fixtures/`）に同じ構成で置き、`--fixtures-dir` で追加する。

ケース dir: `case.json` / `dump.json` / `content.json` / `proposals.json` / 任意 `tracker_scan.json` `transcript.txt` / 期待値 `expected_payload.json` `expected_report.md`（`--update` で生成）。
