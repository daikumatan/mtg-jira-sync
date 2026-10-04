# Jira 同期ドライラン — 2026-09-25 Example 週次定例（顧客 X / フェーズ 1）（**未承認・Jira 未変更**）

- プロファイル: `example-weekly-sync.md`
- 管理表 URL: https://example.com/sheet/2026-09-25
- 対象エピック: PRJ-10 / 系統ラベル: -
- content: `content.json` / 提案設定: `proposals.json`

## 承認の受け方
「全件承認」／「PRJ-xx を除外」／「PRJ-xx の◯◯を修正」のいずれかで返答してください。承認された項目だけを書き込みます。

## PRJ-40 `[#12] Work schedule`
- 現状: status=In Progress / priority=Medium / due=None / assignee=None / labels=weekly-sync

### 1. 追記予定コメント
```
## 2026-09-25 Weekly Sync
**Minutes:** Minutes
**Decision / Background:** Decision
**ACME action:** Send the document — Owner: Owner A — Due: 2026-10-02
**Customer action:** Review — Owner: Customer — Due: TBC
**Source:** transcript l.1-2

---
**議事録:** 議事
**決定・経緯:** 決定
**ACME アクション:** 資料送付 — 担当: 担当A — 期限: 2026-10-02
**顧客 アクション:** 確認 — 担当: 顧客 — 期限: 未定
```

### 2. フィールド差分（提案）
- labels: +cust, no-12

### 3. Description: Description 空 → Background 新設（Title=トラッカー）＋ DoD 新設
```markdown
## Background

* Issue List: [9/25](https://example.com/sheet/2026-09-25)
* Title: Work schedule

## Definition of Done

- [ ] Send the document
```

#### DoD 出典（文字起こし抜粋・Jira には書かない）— 各項目の直下の発言が「〜します」型の約束か確認する
- Send the document — TRACKER 9/25

## 新規起票・分割・作り直し（起票後に返った key で placeholder を置換してからリンク・継続コメントを書く）

### NEW-1 `[#30] New deliverable` — new
- fields: parent=PRJ-10 / priority=None / due=2026-10-02 / labels=no-30,weekly-sync / assignee=None

#### Description
```markdown
## Background

* Issue List: [9/25](https://example.com/sheet/2026-09-25)
* Title: New

## Definition of Done

- [ ] Item
```

#### DoD 出典（文字起こし抜粋）
- Item — confirmed by user

## 実行ログ
（承認後に追記）
