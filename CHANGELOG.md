# Changelog

## v1.2 — 2026-10-04
母体案件の専用スキル v2.2〜v2.5b（2026-09-29〜10-03）で入った改修を汎用側へ取り込み、案件側のスクリプトを本リポへ一本化した（案件側は `--profile` を自動付与するラッパーのみ）。

- `scripts/jira_api.py`（新規）: Jira Cloud REST v3。`fetch`（ダンプ＋要約ビュー）／`write`（既定ドライラン・`--apply`・鮮度チェック・書き込み後の Description 差分検証・`--report` で実行ログ追記・作り直し元の継続コメント `comment2` を実キー置換後に書く）／`transitions --key`（遷移 ID 一覧）／`adf --back`。サイト・プロジェクト・既定 JQL・課題タイプ・TZ はプロファイルから、認証は環境変数か `~/.config/jira.env`。
- `scripts/jira_dump_summary.py`（新規）: ダンプ → 要約ビュー。`--audit` で形式監査（節・Background 行数・DoD 件数・`[x]` 証跡）とエピック配置監査（プロファイル `jira.placement`）。Background 行数は本文行と監査で同じ数え方（トラッカー行を除く）に統一。
- `scripts/jira_sync_report.py`: `--meeting-type weekly|internal|customer`・`--meeting-name`、`--parent`（`jira.parents` の別名可）・`--track-label`、`--out-preview`、`desc_replace`・`desc_drop`・`bg_over_reason`・`purpose`・`deliverable_contents`、ダンプ `issuelinks` による既存リンクの自動除外、同 No. 兄弟チケットからのトラッカー行引き継ぎ、新形式トラッカー行への当日リンク追記（重複行を作らない）、DoD 追記は補足節（Deliverable contents / Materials）の手前、DoD 本文から `confirmed by` を除去、`background_en` の各行に `* ` を補う、validate に節固定・順序・Background 行数／1 行字数・DoD 件数・`[x]` 証跡（`description.rules`）、`labels.track`・`labels.meeting_type` でラベル付与。
- `scripts/profile_lint.py`: `jira.parents`・`jira.placement`・`labels.track`・`labels.meeting_type`・`description.sections`（purpose/deliverable_contents）・`description.rules` を検査。
- `scripts/run_regression.py`: `case.json` の `meeting_type`・`meeting_name`・`parent`・`track_label` を渡し、プレビューも生成。
- `SKILL.md` v1.2: REST 版 3 段モデル、会議種別、複数エピック、Description 5 節と規則、DoD 判定基準 A1〜A6/C1/C2/B1〜B5、結論からの逆引き判定、手動変更を戻さない規則、`tracker.promise_marker`。
- `PROFILE_TEMPLATE.md`・`README.md`・`scripts/README.md`: 新キーと REST 前提、ラッパー方針、fixture の作り方。
- `tests/fixtures/`: 期待値を更新（payload に `meeting_type`・`parent`、DoD 本文の `confirmed by` 除去、Background 行の `* ` 補完）。
- `SCRIPT_BACKLOG.md`: #4 `jira_dump_index`・#5 `freshness_check`・#6 `apply_log` は上記スクリプトに吸収して done。

## v1.1 — 2026-09-27
- 改善ループ（3 層）を追加: SKILL 手順 8。スクリプト層 `SCRIPT_BACKLOG.md`、プロファイル層（判断規則の追記）、スキル層 `SKILL_BACKLOG.md`。案件固有の台帳はプロファイル `ledgers`。`scripts/README.md`（契約）。
- `scripts/run_regression.py`: fixtures 再実行と payload／report 比較（`--fixtures-dir` で外部 fixture を追加、`--update` で期待値生成）。
- `scripts/profile_lint.py`: プロファイル frontmatter の検査（`--public` で見本用チェック）。
- `tests/fixtures/`: 架空データの回帰ケース 2 件。

## v1.0 — 2026-09-27
- 単一案件専用スキルから汎用化。汎用コア `SKILL.md` ＋ 案件プロファイル（リポジトリ外）。
- `scripts/jira_sync_report.py` をプロファイル駆動化。母体案件の実データで payload 一致を確認。
- `examples/` に見本プロファイル 2 種。MIT ライセンス。
