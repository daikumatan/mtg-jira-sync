# Changelog

## v1.1 — 2026-09-27
- 改善ループ（3 層）を追加: SKILL 手順 8。スクリプト層 `SCRIPT_BACKLOG.md`、プロファイル層（判断規則の追記）、スキル層 `SKILL_BACKLOG.md`。案件固有の台帳はプロファイル `ledgers`。`scripts/README.md`（契約）。
- `scripts/run_regression.py`: fixtures 再実行と payload／report 比較（`--fixtures-dir` で外部 fixture を追加、`--update` で期待値生成）。
- `scripts/profile_lint.py`: プロファイル frontmatter の検査（`--public` で見本用チェック）。
- `tests/fixtures/`: 架空データの回帰ケース 2 件。

## v1.0 — 2026-09-27
- 単一案件専用スキルから汎用化。汎用コア `SKILL.md` ＋ 案件プロファイル（リポジトリ外）。
- `scripts/jira_sync_report.py` をプロファイル駆動化。母体案件の実データで payload 一致を確認。
- `examples/` に見本プロファイル 2 種。MIT ライセンス。
