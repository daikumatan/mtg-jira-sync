# SCRIPT_BACKLOG — 補助スクリプトの候補台帳

実行中に手で書いたコード・繰り返した操作を記録し、**2 回以上・手順が安定・入出力が定型** の 3 つが揃ったら scripts/ 化を提案する。
Status: candidate（観測中）/ proposed（提案済み）/ approved / done / rejected。

| # | 候補スクリプト | 置き換える手作業 | 手順 | 観測回数 | Status |
|---|---|---|---|---|---|
| 1 | `run_regression.py` | 旧版と新版の payload を手で diff | scripts/ 変更時 | 2 | **done（v1.1）** |
| 2 | `profile_lint.py` | プロファイルのキー漏れを目視 | §8 | 2 | **done（v1.1）** |
| 3 | `tracker_scan_excel.py` | 手順 2 で毎回 openpyxl のコードを書いて `.tracker_scan` JSON を作る（当日ブロック・TODO 印・自社の約束印・持ち越し） | 2 | 3 | candidate（次回実行時に提案） |
| 4 | `jira_dump_index.py` | 手順 1 でダンプから No.→チケット表と当日の手動コメントを jq で抜く | 1 | 2 | **done（v1.2・`jira_dump_summary.py` に吸収）** |
| 5 | `freshness_check.py` | 手順 6 直前に `updated` を再取得結果と手で比較 | 6 | 2 | **done（v1.2・`jira_api.py write` に内蔵）** |
| 6 | `apply_log.py` | 手順 7 で `written` を proposals に、実行ログをレポートに手で書き戻す | 7 | 2 | **done（v1.2・`jira_api.py write --report`。`written` の書き戻しは未対応）** |
| 7 | `jira_api.py` / `jira_dump_summary.py` | MCP 経由の取得・書き込み（応答が毎回コンテキストに入る） | 1, 6 | 3 | **done（v1.2）** |

## 記録の書き方
- 実行のたびに、レポート末尾「実行ログ」の **手作業だった箇所** から拾って上の表に追記する（新規は 1 行、既出は観測回数 +1）。
- 提案するときは「候補 #N を scripts/ 化しますか（入力→出力・置き換える手順）」の 1 行で。承認なしに作らない。
