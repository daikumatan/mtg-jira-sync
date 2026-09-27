# Jira 同期ドライラン — 2026-07-09 Example 案件群（Kanban・1 週間スプリント）（**未承認・Jira 未変更**）

- プロファイル: `example-sprint-kanban.md` / トラッカー URL: （未指定）
- content: `content.json` / 提案設定: `proposals.json`

## 承認の受け方
「全件承認」／「KAN-xx を除外」／「KAN-xx の◯◯を修正」のいずれかで返答してください。承認された項目だけを書き込みます。

## KAN-40 `Default Gateway の IP変更可否確認と進め方決定`
- 現状: status=In Progress / priority=Medium / due=2026-07-07 / assignee=Member A / labels=site-a,network

### 1. 追記予定コメント
```
## 2026-07-09 Customer Sync
**議事録:** Default Gateway 変更は Customer 側で実施する方向で合意。工数は ACME が算出済み。
**決定・経緯:** Customer が変更する。ACME は手順書を提供。
**ACME アクション:** 手順書ドラフトを Customer に送付 — 担当: 担当者A — 期限: 2026-07-14
**顧客 アクション:** 社内で変更作業の承認を取る — 担当: 担当者B — 期限: 2026-07-15
**参考:** Network Diagram v3
**出典:** 文字起こし l.12-20
```

### 2. フィールド差分（提案）
- status: In Progress → **WAITING FOR CUSTOMER**（遷移ID 31）— 根拠: Customer 承認待ち

### 3. Description: 本文は無変更＋ DoD 追記
```markdown
## 目的
疎通失敗要因の一つ。

## Definition of Done
- [ ] 社内で作業工数を確認する
- [ ] 顧客に変更可否を確認する

### 7/9 (added)

- [ ] 手順書ドラフトを Customer に送付
```

#### ⚠ 候補（トラッカー未記載・未承認 → 今回は DoD に書かない。採用するなら番号で指示）
- C1. KAN-41 の型番を反映 — l.30-31

#### DoD 出典（文字起こし抜粋・Jira には書かない）— 各項目の直下の発言が「〜します」型の約束か確認する
- 手順書ドラフトを Customer に送付 — SYNC 7/9
- KAN-41 の型番を反映 — l.30-31

## KAN-41 `Switch/Transceiver の型番開示を担当者Bへ再依頼`
- 現状: status=To Do / priority=Medium / due=None / assignee=None / labels=site-a

### 2. フィールド差分（提案）
- labels: +for-cust-mtg
- assignee: None → **Member A**

### 3. Description: Description 空 → 目的 新設＋ DoD 新設
```markdown
## 目的

## Definition of Done

- [ ] 担当者Bへ再依頼メールを送る
```

#### DoD 出典（文字起こし抜粋・Jira には書かない）— 各項目の直下の発言が「〜します」型の約束か確認する
- 担当者Bへ再依頼メールを送る — SYNC 7/9

## 新規起票・分割・作り直し（`createJiraIssue` → 返った key で placeholder を置換してからリンク・継続コメントを書く）

### NEW-1 `Survey Sheet の回答を Partner から回収` — new
- fields: parent=KAN-15 / priority=None / due=2026-07-14 / labels=network,site-b / assignee=None

#### Description
```markdown
## 目的

Site Bの Site Survey。担当者C担当。

## Definition of Done

- [ ] Survey Sheet 回収

## Nice to Have

- [ ] 回答の不足箇所を Network Diagram に反映

## 備考

* 担当: 担当者C（※[External]のためアサイン不可）
* Survey Sheet: [https://drive.example/x](https://drive.example/x)
```

#### DoD 出典（文字起こし抜粋）
- Survey Sheet 回収 — SYNC 7/9

## 変更しないチケット
- KAN-3: misc Epic

## トラッカーに無いアクション候補（要確認・一覧）
- KAN-40: KAN-41 の型番を反映

## 実行ログ
（承認後に追記）
