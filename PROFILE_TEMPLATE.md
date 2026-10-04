---
profile: <id>                # ファイル名と同じ（例 acme-phase2）
project_name: <会議名（レポート見出し）>
status: draft                # draft → 実データでドライランを確認後 verified
workspace: <作業ディレクトリ>
meeting:
  name_en: Weekly Sync       # weekly のコメント見出し "## YYYY-MM-DD <name_en>"
  internal_name_en: Internal Sync      # --meeting-type internal の見出し "<internal_name_en> (会議名)"
  customer_name_en: Customer Meeting   # --meeting-type customer の見出し
  internal_name_ja: 社内会議            # レポート見出し（日本語）
  customer_name_ja: 顧客会議
  weekday: fri               # 「次回定例」の解釈に使う曜日
  tz_offset_hours: 9         # 会議日の暦日を決める TZ（JST=9）。Jira API の時刻はアカウント TZ で返る
  dir_glob: "YYYY-MM-DD_HHMM_*"
  files:
    summary: "*_summary.md"
    transcript: "*_transcript_cleaned.txt"
    ledger: "*_summary_review.md"     # 裏取り台帳（無ければ削除）。「アクション再分類」表の「結論との関係」列を再利用する
jira:
  cloud_id: <Atlassian cloudId>       # MCP フォールバック時のみ使う
  site: https://<tenant>.atlassian.net
  email: null                # REST の認証メール。通常は ~/.config/jira.env の JIRA_EMAIL に書き、ここは null
  project_key: <KEY>
  board: <番号>
  parent: <KEY-nn>           # 既定エピック。案件内に複数あるなら parents に別名で列挙し --parent <別名> / new_tickets[].parent で指定
  parents: {}                # 例 {hw: KEY-10, sw: KEY-11}
  exclude_parents: []
  issue_type: Task
  jql: "project = <KEY> AND parent = <KEY-nn> ORDER BY key ASC"
  transitions: {}            # {"To Do": "11", ...}。空なら初回に jira_api.py transitions --key で埋める
  resolved_transition_id: ""
  link_types: [Relates, "Work item split", Duplicate]
  placement: []              # jira_dump_summary.py --audit のエピック配置規則（任意）。3 種:
                             #   - {summary: '^\[#\d+\]', parent: KEY-10, msg: "..."}                 サマリが一致するなら parent 配下であること
                             #   - {under: KEY-12, forbid_summary: '^\[#\d+\]', msg: "..."}            parent 配下にこのサマリは置かない
                             #   - {under: KEY-12, labels_any: [weekly-mtg], require_link_under: KEY-11, except: [KEY-99], msg: "..."}
summary:
  ref_regex: null            # 課題 No. を持つ案件のみ 例 '\[#(\d+)\]'
  prefix_regex: null         # 新規起票サマリの検査 例 '^\[(#\d+|Other|[A-Za-z][\w /&-]*)\]'
  no_ref_prefix: "[Other]"   # No. の無い話題を起票するときの接頭辞
  format: "<サマリの書き方>"
labels:
  fixed: []                  # 全件に付けるラベル
  track: {}                  # エピック → 系統ラベル 例 {KEY-10: hw, KEY-11: sw}（新規起票に付ける。--track-label で上書き可）
  meeting_type: {}           # 会議種別 → ラベル 例 {weekly: weekly-mtg, internal: internal-mtg, customer: customer-mtg}
  ref_label: null            # 課題 No. から機械付与 例 "no-{n:02d}"
  conditional: {}            # ラベル: 付ける条件（LLM 向け説明）
  forbidden: []
parties:                     # 当事者。code は content JSON のキー e{code}/f{code}/g{code} になる
  - code: own
    name_en: <自社略称>
    name_ja: <自社略称>
    role: self
    owner_default_en: TBC
    owner_default_ja: 未定
  - code: cust
    name_en: <顧客略称>
    name_ja: <顧客略称>
    role: customer
    assignable: false        # Jira アカウント無し等
    owner_default_en: <顧客略称>
    owner_default_ja: <顧客略称>
language:
  comment: [en, ja]          # コメントの言語と順序。単言語なら [ja]
  description: en            # en | ja | any（en は日本語混入を validate）
tracker:                     # 管理表・スプリントメモ等「確定アクションの正」。無ければ enabled: false
  enabled: false
  name: 管理表
  kind: excel                # excel | md | none
  file_glob: ""
  sheet: ""
  columns: {}                # ヘッダー名で列特定 {title:, title_en:, priority:, due:, status:, answer:}
  todo_marker: ""            # 確定アクションの印 例 "＜TODO＞"
  promise_marker: ""         # TODO 印が無くても採用する自社の約束の書き方 例 "⇒〜する（自社）"（無ければ空）
  link_label: Tracker        # Description 先頭の日付リンク行ラベル
  url_required: false
  gate_token: TRACKER        # DoD 出典 "— <gate_token> M/D" を無条件採用にする語
description:
  sections: {purpose: Purpose, background: Background, dod: Definition of Done, deliverable_contents: Deliverable contents, materials: Materials}   # nice_to_have を足せる。使わない節は削る
  title_line: true
  rules:                     # validate と --audit の規則。使わないキーは削る（検査しない）
    sections_strict: true    # 独自節・節順違いを検査（新規・desc_replace は NG、既存本文は注記）
    background_std: 3        # Background 基本行数（超えるときは proposals の bg_over_reason）
    background_max: 5
    background_line_chars: 220
    dod_std: 3
    dod_max: 5
    done_evidence: true      # [x] 行に (done M/D: 根拠) を必須にする
priority_map: {}             # トラッカー表記 → Jira 優先度
model: Opus 5.5              # Phase A（内容確定）のモデル。Phase 0/B はモデル不要
python: <venv の python パス>
glossary: <名寄せ辞書のパス>
downstream: []               # content JSON を読む下流スキル・記録先
ledgers:                     # 案件固有の候補台帳（任意）。無ければ null。汎用の候補はリポの SCRIPT_BACKLOG.md / SKILL_BACKLOG.md へ
  skills: null               # 例 <作業ディレクトリ>/docs/Skill化候補.md
  scripts: null
---

# プロファイル: <案件名>

<1〜2 行: この案件の Jira 反映の目的・母体となるガイドライン>

## A. 出典の正
- <トラッカー>が正: …
- cleaned 文字起こしが正: …
- 下流で確定した文言（Slack 周知等）があれば DoD もそれに揃える: …

## B. 採用ゲート
- トラッカー由来（`— <gate_token> M/D`）→ 無条件採用。
- それ以外 → 汎用ゲート（約束の発言・引用＋行番号・承認）。
- 会議種別（weekly / internal / customer）ごとの違いがあれば表で。
- 複数エピックがあれば「エピックの使い分け」表（接頭辞・期限の決め方・起票可否）。

## C. トラッカーのスキャン手順
（無い案件は「無し。起票元は ◯◯」と書く）

## D. フィールド規則
| 項目 | 規則 |
|---|---|
| 優先度 | |
| 期限 | |
| ステータス | |
| Assignee | |

## E. 記述テンプレの差分
（汎用 §4 との違いだけ）

## F. 完了後
（記録先・手作業の依頼事項・下流スキル）
