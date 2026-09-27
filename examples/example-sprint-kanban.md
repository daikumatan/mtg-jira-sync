---
profile: example-sprint-kanban
project_name: Example 案件群（Kanban・1 週間スプリント）
status: draft
workspace: ~/work/example-mtg
meeting:
  name_en: Customer Sync
  weekday: wed
  sprint_end_weekday: tue
  tz_offset_hours: 9
  dir_glob: "YYYY-MM-DD_*"
  files:
    summary: "*_要約.md"
    transcript: "*_cleaned.txt"
    ledger: "*_レビュー注記.md"
    internal_sync: "internal_sync/*.md"   # 「Action Items」節が起票元
jira:
  cloud_id: 00000000-0000-0000-0000-000000000000
  site: https://example.atlassian.net
  project_key: KAN
  board: 200
  parent: KAN-5              # 既定エピック。案件ごとに new_tickets[].parent で上書き
  parents:
    site-a: KAN-5
    site-b: KAN-15
    misc: KAN-3
  issue_type: Task
  jql: "project = KAN AND parent in (KAN-5, KAN-15, KAN-3) ORDER BY key ASC"
  transitions: {}            # 初回に getTransitionsForJiraIssue で埋める
  resolved_transition_id: ""
  link_types: [Relates, "Work item split", Duplicate]
summary:
  ref_regex: null
  prefix_regex: null
  format: "動詞ベースで完了物が分かる表現。技術用語は英語"
labels:
  fixed: []
  ref_label: null
  conditional:
    site-a|site-b|misc: 案件（Epic と併用）
    network|hardware|logistics|pm-ops: 種別
    for-cust-mtg: 顧客定例で話す項目
  forbidden: [sprint-*]
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
  comment: [ja]
  description: ja
tracker:
  enabled: false
  name: トラッカー
  gate_token: SYNC           # 社内同期メモ由来の DoD を "— SYNC M/D" と書けば無条件採用
description:
  sections: {background: 目的, dod: Definition of Done, materials: 備考, nice_to_have: Nice to Have}
  title_line: false
priority_map: {}
model: Opus 5.5
python: ~/work/example-mtg/.venv/bin/python
glossary: ~/work/example-mtg/名寄せ辞書.md
downstream: []
ledgers: {skills: null, scripts: null}
---

# プロファイル: Example 案件群（架空・見本）

「管理表は無く、社内同期メモのアクション項目と顧客定例の文字起こしから起票する」型の見本。日本語のみ・課題 No. 体系なし。

## A. 出典の正
- **社内同期メモ**の Action Items ＝ スプリント内アクションの正（DoD 出典 `— SYNC M/D`）。
- **顧客定例の cleaned 文字起こし** ＝ 顧客との約束・回答待ちの正。

## B. 採用ゲート
- 社内同期メモに明記されたアクション → 採用。
- 顧客定例での約束 → 汎用ゲート。
- Nice to Have は任意項目。DoD（MUST）と混ぜない。無ければ省略。

## C. トラッカーのスキャン手順
無し。起票元は A 節の 2 つ。

## D. フィールド規則
| 項目 | 規則 |
|---|---|
| Parent | 案件 Epic を必ず設定（`new_tickets[].parent`） |
| Summary | 案件プレフィックス無し・動詞ベース・技術用語は英語 |
| Assignee | 正社員のみ。外部委託者はアサイン不可 → Assignee 空＋ `## 備考` に `担当: ◯◯（外部のためアサイン不可）` |
| Start / Due | Due は原則スプリント終了日（火曜）。明示期限があれば優先 |
| Status | 顧客回答待ちは Waiting 列で表現（ラベルにしない） |

## E. 記述テンプレ
```
## 目的
（背景・狙いを 1〜2 文）

## Definition of Done
- [ ] MUST HAVE の完了条件

## Nice to Have
- [ ] 任意・ストレッチ（無ければ省略）

## 備考
担当: ◯◯（外部のみ）／参考リンク
```
コメントは日本語のみ。見出し `## YYYY-MM-DD Customer Sync`。

## F. 完了後
- 遷移 ID を frontmatter に書き戻し、問題なければ `status: verified`。
