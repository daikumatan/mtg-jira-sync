# SKILL_BACKLOG — 隣接スキル・新規スキルの候補台帳

`/mtg-jira-sync` の実行中に見つかる「このスキルの範囲外だが、毎回同じ手順で人が/モデルがやっている定常業務」を記録し、**2 回以上・手順が安定・入出力が定型** の 3 つが揃ったらスキル化（または本リポへの汎用化）を提案する。
案件固有の候補は各作業ディレクトリの台帳（プロファイル `ledgers.skills`）へ。ここには**顧客名を含まない汎用の候補**だけ書く。
Status: candidate / proposed / approved / done / rejected。

| # | 候補スキル | 置き換える定常業務 | 入力 → 出力 | 観測 | Status |
|---|---|---|---|---|---|
| 1 | `mtg-jira-sync`（本リポ） | 会議→Jira 反映を案件ごとに別スキルで運用 | 会議 dir＋プロファイル → Jira コメント/Description/起票 | 案件専用版を 3 回以上運用 → 汎用化 | **done（v1.0）** |
| 2 | `mtg-summarize`（汎用化） | 文字起こし txt の整理・名寄せ・日英要約・命名 | 文字起こし txt＋名寄せ辞書 → 会議 dir（要約 JA/EN・cleaned・裏取り台帳） | 案件専用版を長期運用。本スキルの上流入力を作る | candidate |
| 3 | `mtg-agenda-from-jira` | 次回定例のアジェンダを前回の Jira コメント／DoD から起こす | Jira ダンプ（前回コメント・未完 DoD）＋社内同期要約 → 日英アジェンダ md | 案件専用版は Excel 依存。Jira 直読みへの改修要望あり | candidate |
| 4 | `mtg-hq-minutes`（汎用化） | 経営層向け 1 枚議事録（日英・Human Eval 付き） | 会議 dir＋content JSON → A4 議事録 JA/EN＋cleaned 文字起こし | 案件専用版あり。本スキルの content JSON を入力にできる | candidate |
| 5 | `tracker-jira-consistency` | トラッカー（管理表）と Jira の Status/期限/優先度の食い違いを定期点検 | tracker_scan JSON＋Jira ダンプ → 差分レポート md | 「後で検討」として複数回言及 | candidate |
| 6 | `mtg-hygiene` | 会議 dir 群の衛生点検（重複 dir・上流更新後に下流が stale・命名不整合・孤児ファイル） | 作業ディレクトリ → 点検レポート | 実害 2 回（並行セッション衝突・上流修正の手追随） | candidate |

## 記録の書き方
- 実行のたびに、レポート末尾「実行ログ」の **範囲外だった定常作業** から拾って追記する（新規は 1 行、既出は観測 +1）。
- 提案は「候補 #N をスキル化しますか（入力→出力・置き換える業務）」の 1 行で。承認なしに作らない。
- 案件固有の観測（顧客名・人名・No. が入るもの）は `ledgers.skills` の台帳に書き、ここには汎用化した表現で写す。
