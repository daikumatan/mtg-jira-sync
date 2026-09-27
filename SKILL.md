---
name: mtg-jira-sync
description: 会議資料（要約・裏取り台帳・cleaned 文字起こし）と案件のトラッカー（管理表 Excel 等・任意）から、当日議論した課題ごとの議事録・決定・各社アクションを起こし、Jira チケットへ「会議日付きコメント」「Description（Background/DoD）」「フィールド・遷移・新規起票・リンク」として反映する汎用スキル。案件固有の定数と判断規則は `profiles/<案件>.md`（YAML frontmatter＋文章ルール）に分離し、本体は案件を問わず同じ手順で動く。ドライラン→承認→書き込み。「<案件名> の定例を Jira に反映して」「会議のアクションを Jira チケットに起こして（案件: ◯◯）」「新しい案件用に Jira 反映のプロファイルを作って」と頼まれたときに使う。
---

# mtg-jira-sync（汎用コア v1.1・2026-09-27）

**会議 → Jira** の反映手順を案件横断で共通化したもの。構成は「**汎用コア（本ファイル）＋ 案件プロファイル（`profiles/*.md`）**」。
ある案件専用に運用して安定した手順（ブラインド回帰テスト済み）を母体に、案件依存の値と判断規則をプロファイルへ抜き出した。母体案件のプロファイルで元の手順と同一の payload を出すことを実データで確認している。

## 0. 呼び出しとプロファイル解決

```
/mtg-jira-sync <profile> <会議dir> [tracker-url] [--internal]
```
- `<profile>`: プロファイルの id またはファイルパス。id は次の順で `<id>.md` を探す（**実案件のプロファイルはこのスキルのリポジトリの外に置く**。ファイル名に案件名が入るため）:
  1. 環境変数 `MTG_JIRA_SYNC_PROFILES` のディレクトリ
  2. 作業ディレクトリ直下の `jira_profiles/`
  3. `~/.config/mtg-jira-sync/profiles/`
  4. スキル同梱の `examples/`（架空値の見本。実行用ではない）
  会議 dir 直下に `.jira-sync-profile` があればその中身（id かパス）を既定にする。
- 見つからなければ上記 1〜3 の一覧を示して選ばせる。
- 開始時に `SCRIPT_BACKLOG.md`・`SKILL_BACKLOG.md`（プロファイル `ledgers.*` があればその台帳も）を読み、観測 2 以上で candidate の候補があれば「今回の終了時に提案する」と一言添える（作業は止めない）。新案件なら §8 の手順で `PROFILE_TEMPLATE.md` からプロファイルを作り、`status: draft` のまま **ドライランで止める**。
- プロファイル frontmatter の値（`jira.*` `parties` `language` `tracker` `description.sections` など）を本ファイルの `{…}` に読み替えて実行する。以下で `profiles/{id}.md` と書く箇所は、解決したプロファイルの実パスを指す。本文の A〜F 節は案件固有の判断規則で、**同じ論点では本ファイルよりプロファイルが優先**。

## 1. 原則（案件共通）

- **モデル**: プロファイル `model`（既定 Opus 5.5）。3 回連続で訂正なしに完走したら Sonnet 5 に下げる。`status: draft` のプロファイルは Opus 固定。
- **承認制**: ドライラン（差分レポート）→ ユーザーの承認 → 書き込み。承認前に Jira を変更しない。書き込み直前に対象チケットを再取得し、ダンプ以降に `updated` が動いていれば差分を示して続行可否を確認する。
- **出典は二軸**（プロファイル A 節で具体化）:
  - **トラッカー**（管理表・スプリントメモ等、`tracker`）が正: 課題の体系・統合方向・close 判断・優先度・確定アクション。無い案件（`tracker.enabled: false`）はこの軸を省く。
  - **cleaned 文字起こし**が正: 何が話され、誰が何を約束したか。個人メモ・手動 Jira コメント・自動要約より優先。矛盾は「訂正提案」として出す。
- **アクション/DoD の採用ゲート（非対称）**:
  - トラッカー由来（出典 `— {tracker.gate_token} M/D`）→ 無条件で採用。突合表が全件 ✓ になるまで書かない。
  - トラッカーに無い約束 → 文字起こしで**約束の発言**（「〜します」「I'll」＋具体的成果物）を引用できるものだけ「候補」としてレポートに出し、**ユーザーが承認したもの**（`confirmed by <name>`）だけ採用。要望・意見・例え話（「〜したい」「例えば」「かなと思う」）は `req` へ。迷ったら不採用。引用に無い固有名詞・数値を足さない。
- **上書き禁止の範囲**: 既存コメント（自分のもの以外）、人が書いた DoD 項目の文言とチェック状態、事実の記述。Description はテンプレに沿って**再構成してよい**が、これらは変えない。誤記の訂正は差分レポートに明示して承認を得る。
- 固有名詞はプロファイル `glossary`（名寄せ辞書）で正規化。文字起こしに無い語は書かない。トラッカー原本は読むだけ。Python はプロファイル `python`（venv）。説明はユーザー言語（日本語）、Jira 本文の言語は `language`。

## 2. プロファイルから読む定数（値は書かない・参照先だけ）

| 項目 | frontmatter キー | 使う場面 |
|---|---|---|
| Atlassian cloudId / サイト / プロジェクトキー | `jira.cloud_id` `jira.site` `jira.project_key` | 全 MCP 呼び出し・課題キーのリンク化 |
| 対象エピック・JQL・除外 | `jira.parent`(`jira.parents`) `jira.jql` `jira.exclude_parents` | ダンプ、新規起票の parent |
| 課題タイプ・遷移 ID・Resolved の ID | `jira.issue_type` `jira.transitions` `jira.resolved_transition_id` | 起票・遷移。空なら初回に `getTransitionsForJiraIssue` で埋めてプロファイルへ書き戻す |
| リンク種別 | `jira.link_types` | `createIssueLink`・validate |
| サマリ規約・課題 No. 抽出 | `summary.format` `summary.ref_regex` `summary.prefix_regex` | 改題・`no-NN` ラベル・validate |
| ラベル | `labels.fixed` `labels.ref_label` `labels.conditional` `labels.forbidden` | 起票・ラベル追加 |
| 当事者（自社/顧客/第三者） | `parties[]`（`code` `name_en/ja` `role` `assignable` `owner_default_*`） | content JSON のキー `e{code}/f{code}/g{code}`、コメントの「◯◯ action」行、突合表の組織列 |
| 言語 | `language.comment`（順序付きリスト）`language.description` | コメント構成・Description の validate |
| トラッカー | `tracker.*`（`enabled` `name` `kind` `sheet` `columns` `todo_marker` `link_label` `url_required` `gate_token`） | スキャン・突合表・Description 先頭のリンク行・採用ゲート |
| Description 節名 | `description.sections`（background/dod/materials/nice_to_have）`description.title_line` | 再構成・新規起票 |
| 期限・優先度・ステータス規則 | `meeting.weekday` `meeting.sprint_end_weekday` `priority_map` ＋ プロファイル D 節 | フィールド提案 |
| 下流 | `downstream` | content JSON のキー互換・完了後の記録先 |

## 3. 手順

0. **事前確認**: `atlassianUserInfo`。プロファイル解決（§0）。会議 dir に `meeting.files` の各ファイル（要約・cleaned 文字起こし・台帳）とトラッカー（`tracker.file_glob`）があるか。`tracker.url_required` ならトラッカー URL（引数）が無ければ「再指定 or リンク無し」を尋ねる。
1. **Jira ダンプ**: `jira.jql`、fields `summary,status,labels,assignee,duedate,priority,issuetype,updated,description,comment`、markdown、maxResults 100。`jq` で読み `.jira_dump_YYYYMMDD.json` として会議 dir に置く。`summary.ref_regex` があれば No.→チケット群の対応表を作る。当日の手動コメントを控える。
2. **トラッカースキャン**（`tracker.enabled` のとき。手順はプロファイル C 節）: 当日分の課題と確定アクション（`tracker.todo_marker`）を抽出し `.tracker_scan_YYYYMMDD.json`（形式: `{No: {title, title_en, pri, due, status, today, block, todos[{org, text, carryover}]}}`。案件の慣習があれば別名でもよい）に保存。要約 MD の章見出しとの和集合を当日分とする。
3. **content JSON** `tasklist_content_YYYYMMDD.json`。キー=課題 No.（無しは `other-N`、No. 体系の無い案件は短い slug）。各項目: `jira[]`, `d/d_en`（議事）, `l/l_en`（決定・経緯）, 当事者ごとに `e{code}/e{code}_en`（約束）`f{code}/f{code}_en`（担当）`g{code}`（期限）, `req/req_en`（未確定）, `ref`, `src`（行番号）, `quotes[]`（20〜40 字）, `tracker_todo[]`, `tracker{pri,due,status,title_en}`。`language.comment` に無い言語のキーは省いてよい。裏取りは台帳→無いものだけ grep→**最後のヒットまで**。同 No. の既存チケット（Resolved 含む）の DoD と重複する内容は DoD にせず Background で参照。
4. **提案設定** `.jira_sync_proposals_YYYYMMDD.json`: `manual_comment_day`、`tickets{key: summary / duedate / priority / assignee / labels_add / transition{id,to,why} / title_en / dod[] / desc_skip / background_en / desc_insert_after_link / notes / written}`、`new_tickets[]`（`placeholder NEW-n` / `kind` split|recreate|new / `origin` / `parent`（既定 `jira.parent`）/ `summary` / `content` / `background_en` / `dod` / `nice_to_have` / `materials` / `labels` / `priority` / `duedate` / `assignee` / `transition` / `links`）、`links[]`、`untouched{}`、`no_ticket{}`。DoD 各行の末尾に出典 `— l.NN-NN` か `— {gate_token} M/D` か `— confirmed by <name>` を必ず付ける。
5. **ドライラン**: 
   ```
   {python} scripts/jira_sync_report.py --profile profiles/{id}.md --content … --jira-dump … --proposals … --date YYYY-MM-DD \
       [--tracker-url URL] [--prev-links '{"旧URL":"M/D"}'] [--tracker-scan …] [--transcript …] --validate \
       --out-md jira_sync_YYYYMMDD.md --out-payload .jira_sync_payload_YYYYMMDD.json
   ```
   レポート（突合表・候補表・チケット別差分・DoD 出典抜粋・リンク案）を提示。**validate が NG なら payload を使わず修正**。承認の受け方: 「全件承認」「{PK}-xx を除外」「{PK}-xx の◯◯を修正」「候補 C1 を採用」。
6. **書き込み**（承認分のみ）: before を `.jira_rollback_YYYYMMDD.json` に保存 → 鮮度チェック → コメント → Description → フィールド → 遷移 → 新規起票（`new_tickets`。返った key で placeholder を `links`・継続コメント・`moved to` 行に置換）→ リンク。**応答の description を `scripts/check_desc.py --lang {language.description}` に通し**、`\[ \]`・`<custom`・`![](` が出たら即修正。エラーは止めて報告。
7. **検証・記録**: 実行ログをレポート末尾に追記（`written` を proposals に書き戻す）。新規チケットは「ボードへ移動が必要」としてユーザーに依頼（バックログ→ボードは MCP 不可）。プロファイル F 節の記録先へ 1 行。`status: draft` だった案件は結果を見て `verified` に上げるか判断を仰ぐ。
8. **改善ループ（3 層）**: 実行ログに次を列挙し、それぞれの台帳へ追記（新規は 1 行、既出は観測 +1）。**2 回以上・手順が安定・入出力が定型** の 3 つが揃った候補だけ、終了時に「候補 #N を◯◯化しますか（入力→出力・置き換える手順）」と 1 行で提案する。承認なしに作らない。
   - **スクリプト層** → `SCRIPT_BACKLOG.md`: scripts/ に無くその場で書いたコード、手で繰り返した確認、jq の定型パイプ。承認後は `scripts/README.md` の契約に沿って作成 → `tests/fixtures/` に架空ケース → `run_regression.py` 全緑 → `CHANGELOG.md`。
   - **プロファイル層** → 該当プロファイルの本文: 今回 SKILL.md にもプロファイルにも無くて判断に迷った規則（期限の慣例・ラベルの付け方・特定当事者の扱い）。承認後にプロファイル A〜F 節へ追記し、`profile_lint.py` を通す。新案件そのものは §8 でプロファイル新設を提案。
   - **スキル層** → `SKILL_BACKLOG.md`（顧客名を含まない汎用表現）＋ プロファイル `ledgers.skills` の台帳（案件固有の観測）: 本スキルの範囲外だが毎回同じ手順でやっている定常業務（上流の要約、アジェンダ、経営層向け議事録、トラッカーと Jira の整合点検、会議 dir の衛生点検など）。承認後は別スキルとして作るか、本リポへ汎用化する。

## 4. 記述規約（既定テンプレ。プロファイル D/E 節で差し替え可）

### 4.1 コメント（`language.comment` の順に `---` 区切り。1 チケット 1 本）
```
## YYYY-MM-DD {meeting.name_en}
**Minutes:** 事実のみ（Requests と重複させない）
**Decision / Background:** …
**Requests / proposals (not committed):** 誰が・何を（該当時のみ）
**{party.name_en} action:** … — Owner: … — Due: YYYY-MM-DD|TBC      ← parties ごと
**Refs:** 資料名 / URL
**Source:** transcript l.NN-NN

---
**議事録:** … / **決定・経緯:** … / **要望・提案（未確定）:** … / **{party.name_ja} アクション:** …
```
- 空の行は削る。EN 部に日本語を混ぜない（validate）。未確定は (TBC)／（未確定）。単言語案件は区切り無し・見出しは 1 つ。
- **手動コメントとの重複回避**: 会議日（`meeting.tz_offset_hours` の暦日。スクリプトが `created` を変換して抽出）に人が書いたコメントに既にある項目は繰り返さず、要点が同じ行は `cf. manual comment`。食い違えば訂正提案へ。
- **置き場所**: フル議事録は 1 か所。閉じて作り直した課題は新チケットへ書き、旧には「→ {PK}-yy で継続」1 行。分割はフル議事録を元に残し、新チケットには **Origin コメント**（`## Origin: YYYY-MM-DD {meeting.name_en}` ＋ 要点 2〜3 行 ＋ `Full minutes: {PK}-xx, comment dated …`）。

### 4.2 Description（`language.description`・構造化箇条書き・ネスト 4 スペース）
```
## {sections.background}
* {tracker.link_label}: [M/D](url), [M/D](url)      ← tracker.enabled のとき。日付リンクを追記していく
* Title: <トラッカーの英語タイトル>                    ← description.title_line のとき
* Origin: follow-up to [{PK}-xx](url) (resolved). <済んだ事実>:
    * …
* <顧客>'s request on M/D (発言者): …
* <自社>'s commitment (担当): …
* Target: <期限・目標>（誰の意向か）

## {sections.dod}
- [ ] <トラッカー由来の言い換え／承認済み候補>
- [x] <完了が裏取りできた項目 (done M/D: 根拠)>

## {sections.nice_to_have}            ← 定義された案件のみ
- [ ] …

## {sections.materials}
* <名前>: [URL](URL)
```
- 既存 Description は上の骨格へ**再構成してよい**（誤記の置換は承認）。既存 DoD 項目の文言・チェック状態は変えない。同じ成果物を既に表していれば追記しない。追記は `### M/D (added)`。
- `language.description: en` の案件は日本語本文を英訳して取り込む（原文は残さない）。旧形式 `[{link_label}](URL)` 1 本は新形式に置換し旧 URL を当該日付として保持（`--prev-links`）。
- 他チケット参照は `[{PK}-nn]({site}/browse/{PK}-nn)`。**チェックボックス行の中にはリンクを入れない**（`* Related:` / `* <名前>: [URL](URL)` 行へ）。
- DoD の出典（`— l.NNN` / `— {gate_token} M/D`）は proposals とレポートに持ち、**Jira 本文には書かない**（スクリプトが落とす）。

### 4.3 粒度・分割・統合・リンク（案件共通）
- **1 チケット＝1 成果物**（閉じる条件 1 つ）。同じ課題 No. でも成果物が別なら別チケット（No. ラベルを共有）。
- **閉じて作り直す**: 既存 DoD が全て `[x]` で新しい約束が別成果物 → 既存を Resolved、新規を起票し `Relates`、Background に Origin、旧側 DoD に「→ moved to {PK}-yy」。同じ成果物の続きなら追記。
- **チケットの Resolved とトラッカーの Status は独立**。トラッカー close は同 No. の全チケットを閉じる根拠。
- **リンク種別**: 成果物の切り出し＝`Work item split`。同 No. で並行する別成果物・作り直し＝`Relates`。統合＝吸収側を `Duplicate` で結び Resolved。同 No. は全ペア `Relates`（スクリプトが自動列挙）。統合の残す側はサマリ併記＋Merge note。

## 5. コネクタ制約（Atlassian MCP・2026-09-27 実証・案件共通）
- Description の読み書きは**常に markdown 往復**（ADF 指定は無視）。API 応答は送った文字列を返すので**描画崩れに気づけない**。新しい要素を含む書き込みはユーザーに画面確認を依頼する。
- 往復で壊れるもの: **画像** `![](blob:…)`（復元不可）、**スマートリンク** `<custom data-type="smartlink">`（文字列化）、**リンク入りチェックボックス行**（タスクリストが箇条書きに落ち `\[ \]` が残る）。
- 回避: 画像入り Description は**編集しない**（画像をコメントへ移すよう案内）。スマートリンクは `[URL](URL)` へ。チェック行のリンクは外へ。`jira_sync_report.py` が自動処理し `--validate` で検査。
- 新規起票はバックログに入る。ボード移動は MCP 未対応 → 手作業。コメントは削除不可（ロールバックは本文を "(rolled back)" に更新）。

## 6. 自己チェック（書き込み前）
- [ ] 突合表: トラッカー由来の当日アクションが全て `e{code}` と DoD に入っている（`tracker.enabled` の案件）。
- [ ] 候補表: トラッカーに無い DoD は `confirmed by` のものだけ。
- [ ] DoD 出典抜粋を 1 件ずつ見て、直下の発言が約束（「〜します」型）である。引用に無い固有名詞・数値を足していない。
- [ ] 同 No. の既存チケット（Resolved 含む）と DoD が重複していない。
- [ ] `--validate` が NG ゼロ。
- [ ] 手動コメント／個人メモとの矛盾は「訂正提案」に出した。
- [ ] Resolved 遷移には完了の発言かトラッカー close がある。
- [ ] `assignable: false` の当事者に Assignee を付けていない（ラベル／備考で代替）。
- [ ] 書き込み直前の鮮度チェックを行った。

## 7. 補助スクリプト（`scripts/`）
- `jira_sync_report.py --profile …` … content＋proposals＋ダンプ（＋トラッカースキャン＋文字起こし）→ レポート md・payload json（`tickets` / `new_tickets` / `links`）。コメント言語・Description 節名・ラベル・parent・課題キーのリンク化・DoD ゲートをプロファイルから読む。`--validate` で payload を検査。
- `check_desc.py --lang en|ja|any` … 書き込み応答の description（stdin）を検査。
- `profile_lint.py <profile.md> [--public]` … プロファイル frontmatter の必須キー・型・整合性を検査（見本は `--public`）。新案件のドライラン前と、プロファイルを編集したあとに通す。
- `run_regression.py [--fixtures-dir DIR] [--strict] [--update]` … `tests/fixtures/`（架空データ）と外部 fixture（実案件・リポジトリ外）を再実行し、payload（`--strict` で report md も）が期待値と一致するか確認。**scripts/ を変更したら必ず全ケース緑にしてから使う**。
- 追加の決まりは `scripts/README.md`。候補台帳はスクリプト `SCRIPT_BACKLOG.md`・スキル `SKILL_BACKLOG.md`。

## 8. 新しい案件を追加する（プロファイルの作り方）
1. `cp PROFILE_TEMPLATE.md <作業ディレクトリ>/jira_profiles/<id>.md`（リポジトリの外。§0 の探索先のいずれか）。frontmatter を埋める。分からない値（遷移 ID など）は空にして `status: draft`。
2. 本文 A〜F 節を書く: **A 出典の正** / **B 採用ゲート**（トラッカー由来をどう無条件採用するか）/ **C トラッカーのスキャン手順**（無ければ「無し」）/ **D フィールド規則**（優先度・期限・ステータス・Assignee）/ **E 記述テンプレの差分** / **F 完了後の記録先**。`examples/example-weekly-sync.md`（トラッカー有り・英日・課題 No. 体系有り）と `examples/example-sprint-kanban.md`（トラッカー無し・日本語のみ・No. 無し）が両端の見本。
3. `scripts/profile_lint.py <profile.md>` を通す（ERROR ゼロ）。過去の会議 1 回分で手順 0〜5 を回し、レポートをユーザーが確認。遷移 ID 等を書き戻し、問題なければ `status: verified`。その回の入力と payload を実案件 fixture（リポジトリ外）として保存し、以後の回帰に使う。
4. 案件の Jira 記載ガイドラインが別にあれば、プロファイルから参照し重複して書かない。

## 9. 改訂履歴
- 2026-09-27 v1.1: 改善ループ 3 層（手順 8・`SCRIPT_BACKLOG.md`・`SKILL_BACKLOG.md`・プロファイル `ledgers`・`scripts/README.md`）、`run_regression.py`・`profile_lint.py`、`tests/fixtures/` を追加。
- 2026-09-27 v1: 単一案件専用スキルから汎用化。プロファイル分離、スクリプトのプロファイル駆動化（母体案件の実データで payload 一致を確認）、サンプルプロファイル 2 種を追加。
