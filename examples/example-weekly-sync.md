---
profile: example-weekly-sync
project_name: Example 週次定例（顧客 X / フェーズ 1）
status: draft
workspace: ~/work/example-mtg
meeting:
  name_en: Weekly Sync
  weekday: fri
  time: "10:00 JST"
  tz_offset_hours: 9
  dir_glob: "YYYY-MM-DD_HHMM_*"
  files:
    summary: "*_要約.md"
    transcript: "*_文字起こし_cleaned.txt"
    ledger: "*_要約_レビュー注記.md"
jira:
  cloud_id: 00000000-0000-0000-0000-000000000000
  site: https://example.atlassian.net
  project_key: PRJ
  board: 100
  parent: PRJ-10             # 週次定例のエピック
  exclude_parents: [PRJ-11]  # 別トラックのエピックは対象外
  issue_type: Task
  jql: "project = PRJ AND parent = PRJ-10 ORDER BY key ASC"
  transitions:
    "To Do": "11"
    "In Progress": "21"
    "Waiting for Customer": "31"
    "Resolved": "41"
  resolved_transition_id: "41"
  link_types: [Relates, "Work item split", Duplicate]
summary:
  ref_regex: '\[#(\d+)\]'            # 顧客管理表の課題 No.
  prefix_regex: '^\[(#\d+\]|Other\])'
  no_ref_prefix: "[Other]"
  format: "[#NN] 英語サマリ（統合は [#12][#29] と併記）"
labels:
  fixed: [weekly-sync]
  ref_label: "no-{n:02d}"
  conditional:
    cust: 顧客側アクションを持つチケット（顧客は Jira アカウント無しのため Assignee の代替）
parties:
  - code: own
    name_en: ACME
    name_ja: ACME
    role: self
    owner_default_en: TBC
    owner_default_ja: 未定
  - code: cust
    name_en: Customer
    name_ja: 顧客
    role: customer
    assignable: false
    owner_default_en: Customer
    owner_default_ja: 顧客
language:
  comment: [en, ja]
  description: en
tracker:
  enabled: true
  name: 管理表
  kind: excel
  file_glob: "課題管理表_*.xlsx"
  sheet: Issue List
  columns:
    title: 課題タイトル
    title_en: Action Item(EN)
    priority: 優先度
    due: 完了期限
    status: ステータス
    answer: 回答・対応方針
  todo_marker: "＜TODO＞"
  link_label: Issue List
  url_required: true
  gate_token: TRACKER
description:
  sections: {background: Background, dod: Definition of Done, materials: Materials}
  title_line: true
priority_map: {High: High, Middle: Medium, Low: Low}
model: Opus 5.5
python: ~/work/example-mtg/.venv/bin/python
glossary: ~/work/example-mtg/名寄せ辞書.md
downstream: []
ledgers: {skills: null, scripts: null}
---

# プロファイル: Example 週次定例（架空・見本）

「顧客が管理表 Excel を毎週配布し、こちらが Jira で追跡する」型の見本。値はすべて架空。

## A. 出典の正（二軸）
- **顧客管理表が正**: 課題 No. の体系、統合方向、close 判断、優先度、`＜TODO＞` のアクション。読むだけ。
- **cleaned 文字起こしが正**: 何が話され、誰が何を約束したか。個人メモ・手動コメント・自動要約より優先。

## B. 採用ゲート
- 管理表の**当日ブロック**の `＜TODO＞` → 無条件採用（出典 `— TRACKER M/D`）。
- 前回ブロックの `＜TODO＞`（持ち越し）→ 当日再び触れられ未完了なら採用（`carryover: true`）。
- 管理表に無い約束 → 汎用ゲート（約束の発言のみ・引用＋行番号・承認）。

## C. トラッカーのスキャン手順
1. シート `Issue List` をヘッダー名で列特定（`tracker.columns`）。
2. 当日日付で始まる行を当日 No. とし、当日ブロックから `＜TODO＞` を抽出 → `.tracker_scan_YYYYMMDD.json`。
3. 要約 MD の章見出しとの和集合を当日 No. とする。管理表 URL は引数で受ける。

## D. フィールド規則
| 項目 | 規則 |
|---|---|
| 優先度 | 管理表 High/Middle/Low → High/Medium/Low。Jira が既定 Medium のときだけ写す |
| 期限 | Jira の期限が空か過去日のときだけ提案。「次回定例」= 翌週金曜。管理表の過去日は誤記扱い |
| ステータス | Resolved は完了の発言・管理表 close・DoD 全 `[x]` のいずれかがある場合のみ。顧客待ち = Waiting for Customer |
| Assignee | 自社担当が発言で明確なときのみ。顧客はアカウント無し → ラベル `cust` |

## E. 記述テンプレの差分
- Background 先頭行 `* Issue List: [M/D](url), …`（日付リンクを追記）。2 行目 `* Title: <管理表の EN タイトル>`。
- 日本語の既存本文は英訳して取り込む。

## F. 完了後
- 新規チケットのボード移動を依頼。レポート所在を案件の索引ファイルに 1 行。
