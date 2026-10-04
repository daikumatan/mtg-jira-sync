---
name: mtg-jira-sync
description: 会議資料（要約・裏取り台帳・cleaned 文字起こし）と案件のトラッカー（管理表 Excel 等・任意）から、当日議論した課題ごとの議事録・決定・各社アクションを起こし、Jira チケットへ「会議日付きコメント」「Description（Purpose/Background/DoD）」「フィールド・遷移・新規起票・リンク」として反映する汎用スキル。案件固有の定数と判断規則は `profiles/<案件>.md`（YAML frontmatter＋文章ルール）に分離し、本体は案件を問わず同じ手順で動く。Jira の取得・書き込みは REST スクリプト（`jira_api.py`）でモデルを介さず行い、ドライラン→承認→書き込み。「<案件名> の定例を Jira に反映して」「会議のアクションを Jira チケットに起こして（案件: ◯◯）」「新しい案件用に Jira 反映のプロファイルを作って」と頼まれたときに使う。
---

# mtg-jira-sync（汎用コア v1.2・2026-10-04）

**会議 → Jira** の反映手順を案件横断で共通化したもの。構成は「**汎用コア（本ファイル）＋ 案件プロファイル（`profiles/*.md`）＋ スクリプト（`scripts/`）**」。
ある案件専用に運用して安定した手順を母体に、案件依存の値と判断規則をプロファイルへ抜き出した。母体案件のプロファイルで元の手順と同一の payload を出すことを実データ 2 回分（回帰 fixture）で確認している。

## 0. 呼び出しとプロファイル解決

```
/mtg-jira-sync <profile> <会議dir> [tracker-url] [--meeting-type weekly|internal|customer] [--meeting-name "…"] [--parent <alias>]
```
- `<profile>`: プロファイルの id またはファイルパス。id は次の順で `<id>.md` を探す（**実案件のプロファイルはこのスキルのリポジトリの外に置く**。ファイル名に案件名が入るため）:
  1. 環境変数 `MTG_JIRA_SYNC_PROFILES` のディレクトリ
  2. 作業ディレクトリ直下の `jira_profiles/`
  3. `~/.config/mtg-jira-sync/profiles/`
  4. スキル同梱の `examples/`（架空値の見本。実行用ではない）
  会議 dir 直下に `.jira-sync-profile` があればその中身（id かパス）を既定にする。
- 見つからなければ上記 1〜3 の一覧を示して選ばせる。
- 開始時に `SCRIPT_BACKLOG.md`・`SKILL_BACKLOG.md`（プロファイル `ledgers.*` があればその台帳も）を読み、観測 2 以上で candidate の候補があれば「今回の終了時に提案する」と一言添える（作業は止めない）。新案件なら §8 の手順で `PROFILE_TEMPLATE.md` からプロファイルを作り、`status: draft` のまま **ドライランで止める**。
- プロファイル frontmatter の値（`jira.*` `parties` `language` `tracker` `description.*` `labels.*` など）を本ファイルの `{…}` に読み替えて実行する。以下で `profiles/{id}.md` と書く箇所は、解決したプロファイルの実パスを指す。本文の A〜F 節は案件固有の判断規則で、**同じ論点では本ファイルよりプロファイルが優先**。

## 1. 原則（案件共通）

- **モデルは 3 段に分ける**: **Phase 0（取得）**＝手順 0〜1。`scripts/jira_api.py fetch` を Bash で呼ぶだけ（モデル不要）。成果物は `.jira_dump_*.json` と `jira_dump_summary_*.md`。**Phase A（内容確定）**＝手順 2〜5。文字起こしの読解・DoD の判断・Background の圧縮など判断が多いので **プロファイル `model`（既定 Opus 5.5）以上**（検収・契約・数値が絡む回は上位モデル）。**Phase A は Jira API/MCP を呼ばない**（ダンプ JSON と要約ビューを `jq`/`sed` で読む。足りないチケットがあれば Phase 0 に戻って取り直す）。成果物は `.jira_sync_payload_*.json` と `jira_preview_*.md`。**Phase B（書き込み）**＝手順 6〜7。`scripts/jira_api.py write --apply` を Bash で呼ぶだけ（モデル不要。本文は payload の文字列そのまま）。結果、**1 セッション・1 モデルで完結**し、Jira の応答はコンテキストに入らない。REST が使えないとき（トークン失効等）だけ MCP にフォールバックし、軽いモデルが payload の文字列を一字も変えずに渡す。`status: draft` のプロファイルは Opus 固定。
- **承認制**: ドライラン（差分レポート＋プレビュー）→ ユーザーの承認 → 書き込み。承認前に Jira を変更しない。書き込み直前に対象チケットを再取得し、ダンプ以降に `updated` が動いていれば skip（`--force` で続行）。**dump と status・担当・期限が違っても「戻さない」**: 人の手動変更として報告だけする。
- **出典は二軸**（プロファイル A 節で具体化）:
  - **トラッカー**（管理表・スプリントメモ等、`tracker`）が正: 課題の体系・統合方向・close 判断・優先度・確定アクション。無い案件（`tracker.enabled: false`）はこの軸を省く。
  - **cleaned 文字起こし**が正: 何が話され、誰が何を約束したか。個人メモ・手動 Jira コメント・自動要約より優先。矛盾は「訂正提案」として出す。
- **アクション/DoD の採用ゲート（非対称）**:
  - トラッカー由来（出典 `— {tracker.gate_token} M/D`）→ 無条件で採用。突合表が全件 ✓ になるまで書かない。トラッカーに `tracker.promise_marker` の形で自社の約束が書かれていれば、TODO 印が無くても採用（顧客の依頼だけなら候補のまま）。持ち越し TODO は当日再び触れられ未完了なら採用（`carryover: true`）。
  - トラッカーに無い約束 → 文字起こしで**約束の発言**（「〜します」「I'll」＋具体的成果物）を引用できるものだけ「候補」としてレポートに出し、**ユーザーが承認したもの**（`confirmed by <name>`）だけ採用。要望・意見・例え話（「〜したい」「例えば」「かなと思う」）は `req` へ。迷ったら不採用。引用に無い固有名詞・数値を足さない。要約の `[Watch]`／`[Open]` は `l`（決定・経緯）か `req` に入れ、DoD にしない。`[FYI]` は Jira に書かない（資料 URL があれば Materials のみ）。
  - 下流スキル（Slack 周知等）でユーザーが確定した文言があれば、同じアクションの DoD・コメントの action 行はその文言に揃える（プロファイル A 節）。
- **結論からの逆引き判定**: 「最後の発言が勝つ」は期限・数値・担当の上書きに使う規則。これとは別に、**会議途中に出たアクション候補は、その議題の最終結論から逆引きして有効性を判定する**。
  1. 議題ごとの**結論ブロック**を特定する（司会の「次に行きます」「クローズしましょう」、当事者の "that's our final answer" など締めの発言と、その前 20〜30 行）。
  2. 途中に出たアクション候補を 1 件ずつ結論と照合し、**有効**（結論の実行に必要・結論で担当や期限が再確認された → 採用）／**吸収**（結論側のアクションと目的・相手が同じ → 結論側の行に統合し出典を併記）／**失効**（結論で前提が変わった・否定された・保留 → `[Watch]`/`[Open]` に理由付きで記録）／**独立**（別議題の約束 → 通常のゲート）に分類する。
  3. 「I'll try」「〜してみる」型の弱い約束は、結論に再登場しなければ失効。結論で担当名が無い場合は、結論を述べた人（と引き取った人）を担当にする。
  4. 上流の裏取り台帳（`meeting.files.ledger`）に「結論との関係」列があればそれを再利用する。DoD に起こすのは「有効」「独立（約束あり）」だけ。
- **DoD の判定基準**（DoD＝「このチケットの成果物が受け手に使える状態で渡ったと言える条件」。PMBOK 7 の "ready for customer use"、Scrum 用語では受け入れ基準）。1 行ごとに次を満たす:
  - A1 **独立性**: 他の DoD 行の成果物に内包される内容は書かない（「一覧を作る」があるなら「一覧に X を明記」は別行にせず `{sections.deliverable_contents}` へ）。
  - A2 **成果物の授受**: 完了は「誰に何を渡したか」で判定。口頭伝達・社内決定だけで `[x]` にしない。
  - A3 **受け手基準**: 「共有する」「検討する」単体は不可。受け手が何をできるようになるかを書く。決定型（Decide …）は「何を・誰に・いつまでに決めた結果を伝えるか」、社内確認型（Check with …）は「回答を記録し、次の一手を決める」まで書けば可。
  - A4 **一回性**: 毎週・随時続くものは DoD にしない（決定事項・運用節へ）。
  - A5 **約束の裏取り**: 「〜します」型の発言に行番号を付けられるものだけ。要望・懸念・「話すべき」は `req`。
  - A6 **起票者の意図**: 人が手動起票したチケットは、サマリに無い目的が無いかを確認してから DoD を起こす（`{sections.purpose}` があればそれに従う。無ければドライランで「意図確認」を出す）。
  - C1 報告先が明確な**確認作業は DoD**（例: X に確認し顧客へ報告）。社内で聞いて終わるものは Background。
  - C2 **顧客側のアクション**は「自社が必要な情報を得るまで」が成果物。自社視点で `Obtain X from <顧客>` と書き、待ちの間は顧客待ちステータス。
  - 運用: B1 DoD は **基本 `rules.dod_std` 件・最大 `rules.dod_max` 件**（超えるなら分割）。B2 `[x]` には `(done M/D: 根拠)` を必須（`rules.done_evidence`）。B3 ドライランの DoD 候補に採用根拠（A1〜A6/C1/C2）を 1 語で付け、A1・A6 の疑いは明示してユーザーに聞く。B4 人が書いた既存 DoD の文言・チェックは変えず、反する行は訂正提案のみ。B5 手動起票は `{sections.purpose}` を推奨（必須ではない）。`--validate` が B1・B2 を機械検査する。
- **上書き禁止の範囲**: 既存コメント（自分のもの以外）、人が書いた DoD 項目の文言とチェック状態、事実の記述。Description はテンプレに沿って**再構成してよい**が、これらは変えない。誤記の訂正は差分レポートに明示して承認を得る。
- 固有名詞はプロファイル `glossary`（名寄せ辞書）で正規化。文字起こしに無い語は書かない。トラッカー原本は読むだけ。Python はプロファイル `python`（venv）。説明はユーザー言語（日本語）、Jira 本文の言語は `language`。

### 1.5 会議種別（最初に決める。`--meeting-type`）

| 項目 | weekly（定例） | internal（社内会議） | customer（顧客臨時会議） |
|---|---|---|---|
| 出典 | トラッカー ＋ cleaned 文字起こし | cleaned 文字起こしのみ（要約が無ければ自動要約＋台帳でよい） | cleaned 文字起こしのみ |
| アクション採用 | トラッカー由来は無条件、それ以外は候補 | **全件候補**。ユーザー承認分だけ DoD へ | 全件候補。顧客同席の約束は確定扱いで承認を推奨 |
| 課題 No. の対応付け | トラッカーの当日 No. | 発言中の No. とサマリの参照（`summary.ref_regex`）・題名で照合。No. が無い話題は既存チケットへのコメント追記を優先し、新規起票は候補として出して承認時のみ `summary.no_ref_prefix` で起票 | 同左 |
| 優先度・close・No. 統合 | トラッカーに従う | **触らない**（顧客が決める） | 触らない |
| ステータス遷移 | 完了発言 or トラッカー close | 社内決定は顧客合意ではない。Resolved は「顧客へ提出済み／回答済み」の発言があるときだけ。自社方針の決定は Background・コメントに `internal decision, not yet communicated to <顧客>` と明記 | 完了発言のみ |
| 期限 | 発言の期限 ＞ 次回定例日（`meeting.weekday`） | 同じ | 同じ |
| コメント見出し | `## YYYY-MM-DD {meeting.name_en}` | `## YYYY-MM-DD {meeting.internal_name_en} (会議名)` | `## YYYY-MM-DD {meeting.customer_name_en} (会議名)` |
| ラベル | `labels.track[parent]` ＋ `labels.meeting_type.weekly` | 同 ＋ `labels.meeting_type.internal` | 同 ＋ `labels.meeting_type.customer` |
| Description | トラッカー日付リンク行を追記 | その行は追記しない（同 No. の兄弟チケットから引き継ぐ）。`background_en` で経緯を補う | 同左 |
| Jira に書かない | 対外非開示の内部情報は台帳で切り分け | 同じ＋台帳の「顧客可視性」節の項目（収益・原価・経営判断・個人の反発）は Jira にも書かない | 同左 |

複数エピックを持つ案件は `jira.parents`（別名 → キー）に列挙し、`--parent <別名>` で起票先を選ぶ。エピックごとの接頭辞・期限の決め方・起票可否はプロファイル B 節に表で書く。

## 2. プロファイルから読む定数（値は書かない・参照先だけ）

| 項目 | frontmatter キー | 使う場面 |
|---|---|---|
| サイト / プロジェクトキー / メール | `jira.site` `jira.project_key` (`jira.email`) | REST 呼び出し・課題キーのリンク化。認証トークンは `~/.config/jira.env` |
| 対象エピック・別名・JQL | `jira.parent` `jira.parents` `jira.jql` `jira.exclude_parents` | ダンプ、新規起票の parent（`--parent`） |
| 課題タイプ・遷移 ID・Resolved の ID | `jira.issue_type` `jira.transitions` `jira.resolved_transition_id` | 起票・遷移。空なら初回に `jira_api.py transitions --key` で埋めてプロファイルへ書き戻す |
| リンク種別 | `jira.link_types` | リンク作成・validate |
| エピック配置の規則 | `jira.placement[]` | `jira_dump_summary.py --audit`（接頭辞と親エピックの整合） |
| サマリ規約・課題 No. 抽出 | `summary.format` `summary.ref_regex` `summary.prefix_regex` `summary.no_ref_prefix` | 改題・No. ラベル・validate |
| ラベル | `labels.fixed` `labels.track{エピック: ラベル}` `labels.meeting_type{weekly/internal/customer: ラベル}` `labels.ref_label` `labels.conditional` `labels.forbidden` | 起票・ラベル追加 |
| 当事者（自社/顧客/第三者） | `parties[]`（`code` `name_en/ja` `role` `assignable` `owner_default_*`） | content JSON のキー `e{code}/f{code}/g{code}`、コメントの「◯◯ action」行、突合表の組織列 |
| 言語 | `language.comment`（順序付きリスト）`language.description` | コメント構成・Description の validate |
| トラッカー | `tracker.*`（`enabled` `name` `kind` `sheet` `columns` `todo_marker` `promise_marker` `link_label` `url_required` `gate_token`） | スキャン・突合表・Description 先頭のリンク行・採用ゲート |
| Description 節名・規則 | `description.sections`（purpose/background/dod/deliverable_contents/nice_to_have/materials）`description.title_line` `description.rules`（`sections_strict` `background_std/max/line_chars` `dod_std/max` `done_evidence`） | 再構成・新規起票・validate・監査 |
| 会議 | `meeting.name_en` `meeting.internal_name_en` `meeting.customer_name_en` `meeting.weekday` `meeting.tz_offset_hours` `meeting.files` | コメント見出し・期限・手動コメント抽出・入力ファイル |
| 期限・優先度・ステータス規則 | `priority_map` ＋ プロファイル D 節 | フィールド提案 |
| 下流 | `downstream` | content JSON のキー互換・完了後の記録先 |

## 3. 手順

0. **事前確認**: プロファイル解決（§0）。会議種別（§1.5）と起票先エピック（`--parent`）を決める。会議 dir に `meeting.files` の各ファイル（要約・cleaned 文字起こし・台帳）とトラッカー（`tracker.file_glob`）があるか。`tracker.url_required` ならトラッカー URL（引数）が無ければ「再指定 or リンク無し」を尋ねる。
1. **Jira ダンプ（Phase 0）**: `{python} scripts/jira_api.py --profile profiles/{id}.md fetch --out .jira_dump_YYYYMMDD.json --summary jira_dump_summary_YYYYMMDD.md --full <追記対象キー> [--keys エピック外キー]`（JQL は `jira.jql`。description/comment は markdown 化済み・`issuelinks`/`parent` 付き）。要約の章見出し・発言中の No. から追記対象になりそうなキーを挙げ、`--full` で全文を同梱する。**Phase A へ渡すのはこの 2 ファイル**。`summary.ref_regex` で No.→チケット群の対応表を作る。当日の手動コメントを控える。MCP フォールバック時は fields を**必ず全部**（`summary,status,labels,assignee,duedate,priority,issuetype,updated,description,comment,issuelinks,parent`）取り、`jira_dump_summary.py` で要約ビューを作る。
2. **トラッカースキャン**（`tracker.enabled` かつ weekly のとき。手順はプロファイル C 節）: 当日分の課題と確定アクション（`tracker.todo_marker`・`tracker.promise_marker`）を抽出し `.tracker_scan_YYYYMMDD.json`（形式: `{No: {title, title_en, pri, due, status, today, block, todos[{org, text, carryover}]}}`。案件の慣習があれば別名でもよい）に保存。要約 MD の章見出しとの和集合を当日分とする。internal/customer はスキップし、当日の話題は要約の章見出しと発言中の No. から起こす。
3. **content JSON** `tasklist_content_YYYYMMDD.json`。キー=課題 No.（無しは `other-N`、No. 体系の無い案件は短い slug）。各項目: `jira[]`, `d/d_en`（議事）, `l/l_en`（決定・経緯）, 当事者ごとに `e{code}/e{code}_en`（約束）`f{code}/f{code}_en`（担当）`g{code}`（期限）, `req/req_en`（未確定）, `ref`, `src`（行番号）, `quotes[]`（20〜40 字）, `tracker_todo[]`, `tracker{pri,due,status,title_en}`。`language.comment` に無い言語のキーは省いてよい。裏取りは台帳→無いものだけ grep→**最後のヒットまで**。同 No. の既存チケット（Resolved 含む）の DoD と重複する内容は DoD にせず Background で参照。
4. **提案設定** `.jira_sync_proposals_YYYYMMDD.json`: `manual_comment_day`、`tickets{key: summary / duedate / priority / assignee / labels_add / transition{id,to,why} / title_en / title_replace / dod[] / desc_skip / desc_replace / desc_drop[] / background_en[] / bg_over_reason / desc_insert_after_link / notes / written}`、`new_tickets[]`（`placeholder NEW-n` / `kind` split|recreate|new / `origin` / `parent`（別名可。既定 `--parent`）/ `summary` / `content` / `purpose` / `background_en` / `bg_over_reason` / `dod` / `deliverable_contents` / `nice_to_have` / `materials` / `labels` / `priority` / `duedate` / `assignee` / `transition` / `links`）、`links[]`、`untouched{}`、`no_ticket{}`。DoD 各行の末尾に出典 `— l.NN-NN` か `— {gate_token} M/D` か `— confirmed by <name>` を必ず付ける（スクリプトが本文から落とす）。
5. **ドライラン（Phase A の出口）**:
   ```
   {python} scripts/jira_sync_report.py --profile profiles/{id}.md --content … --jira-dump … --proposals … --date YYYY-MM-DD \
       [--meeting-type internal --meeting-name "会議名"] [--parent sw] [--tracker-url URL] [--prev-links '{"旧URL":"M/D"}'] \
       [--tracker-scan …] [--transcript …] --validate --out-preview jira_preview_YYYYMMDD.md \
       --out-md jira_sync_YYYYMMDD.md --out-payload .jira_sync_payload_YYYYMMDD.json
   ```
   `jira_sync_*.md`（突合表・候補表・チケット別差分・DoD 出典抜粋・リンク案＝分析用）、**`jira_preview_*.md`（Jira に書かれる最終文字列だけ＝承認用）**、payload を生成。**validate が NG なら payload を使わず修正**。承認の受け方: 「全件承認」「{PK}-xx を除外」「{PK}-xx の◯◯を修正」「候補 C1 を採用」。
6. **書き込み（Phase B・承認分のみ）**: `{python} scripts/jira_api.py --profile profiles/{id}.md write --payload … --dump … --log jira_write_YYYYMMDD.md` でドライラン → 問題なければ `--apply --report jira_sync_YYYYMMDD.md`（鮮度チェック→コメント→fields+description→遷移→新規起票（parent 付き・placeholder を実キーに置換）→作り直し元の継続コメント→リンク。Description は書いた直後に再取得して payload と差分検証し、実行ログをレポート末尾へ追記）。除外は `--only`。MCP フォールバック時は before を `.jira_rollback_YYYYMMDD.json` に保存し、同じ順で書き、**応答の description を `scripts/check_desc.py --lang {language.description}` に通し**、`\[ \]`・`<custom`・`![](` が出たら即修正。エラーは止めて報告。
7. **検証・記録**: 新規チケットは「ボードへ移動が必要」としてユーザーに依頼（バックログ→ボードは REST Agile API・MCP とも未対応）。`written` を proposals に書き戻す。プロファイル F 節の記録先へ 1 行。`status: draft` だった案件は結果を見て `verified` に上げるか判断を仰ぐ。
8. **改善ループ（3 層）**: 実行ログに次を列挙し、それぞれの台帳へ追記（新規は 1 行、既出は観測 +1）。**2 回以上・手順が安定・入出力が定型** の 3 つが揃った候補だけ、終了時に「候補 #N を◯◯化しますか（入力→出力・置き換える手順）」と 1 行で提案する。承認なしに作らない。
   - **スクリプト層** → `SCRIPT_BACKLOG.md`: scripts/ に無くその場で書いたコード、手で繰り返した確認、jq の定型パイプ。承認後は `scripts/README.md` の契約に沿って作成 → `tests/fixtures/` に架空ケース → `run_regression.py` 全緑 → `CHANGELOG.md`。
   - **プロファイル層** → 該当プロファイルの本文: 今回 SKILL.md にもプロファイルにも無くて判断に迷った規則（期限の慣例・ラベルの付け方・特定当事者の扱い）。承認後にプロファイル A〜F 節へ追記し、`profile_lint.py` を通す。新案件そのものは §8 でプロファイル新設を提案。
   - **スキル層** → `SKILL_BACKLOG.md`（顧客名を含まない汎用表現）＋ プロファイル `ledgers.skills` の台帳（案件固有の観測）: 本スキルの範囲外だが毎回同じ手順でやっている定常業務。承認後は別スキルとして作るか、本リポへ汎用化する。

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
- **置き場所**: フル議事録は 1 か所。閉じて作り直した課題は新チケットへ書き、旧には「→ {PK}-yy で継続」1 行（スクリプトが `comment2` として生成）。分割はフル議事録を元に残し、新チケットには **Origin コメント**（`## Origin: YYYY-MM-DD {meeting.name_en}` ＋ 要点 2〜3 行 ＋ `Full minutes: {PK}-xx, comment dated …`）。

### 4.2 Description（`language.description`・構造化箇条書き・ネスト 4 スペース）
- **節はプロファイル `description.sections` で定義したものだけ・この順**: `{purpose}`（任意・1 文）→ `{background}` → `{dod}`（Background の直後に必ず）→ `{deliverable_contents}`（任意。成果物の中身。DoD にも Background にも入れない）→ `{nice_to_have}`（任意）→ `{materials}`（任意・URL のみ）。自由な節名は作らない（`rules.sections_strict`）。経緯・引用・議論の往復は会議日付きコメントへ。
- `{purpose}` は次のどれかに当たるときだけ: ① タイトルの成果物を出すだけでは閉じない隠れた目的がある ② 期限・依存から来る「なぜ今」がある ③ 分割・作り直しで親の目的を知らないと DoD が読めない。**タイトルと DoD で目的が読めるなら書かない**。
- **Background は基本 `rules.background_std` 行・最大 `rules.background_max` 行**（トップレベルの箇条書き。1 行 `rules.background_line_chars` 字以内。トラッカーのリンク行は数えない）。超えるときは proposals の `bg_over_reason` に理由を書く（無ければ validate NG）。基本の 3 行: ① Origin＋Related ② 顧客の要求 or 決定 ③ 自社の約束・方針＋Target。
```
## {sections.background}
* {tracker.link_label}: [M/D](url), [M/D](url)      ← tracker.enabled のとき。日付リンクを追記していく
* Title: <トラッカーの英語タイトル>                    ← description.title_line のとき
* Origin: follow-up to [{PK}-xx](url) (resolved). <済んだ事実>
* <顧客>'s request on M/D (発言者): …
* <自社>'s commitment (担当): … Target: <期限・目標>（誰の意向か）

## {sections.dod}
- [ ] <トラッカー由来の言い換え／承認済み候補>
- [x] <完了が裏取りできた項目 (done M/D: 根拠)>

## {sections.deliverable_contents}   ← 定義された案件のみ
* …

## {sections.materials}
* <名前>: [URL](URL)
```
- **DoD 行末の担当名**は、Assignee を設定できないとき（`assignable: false` の当事者・外部者）だけ付ける。
- 既存 Description は上の骨格へ**再構成してよい**（誤記の置換は承認）。既存 DoD 項目の文言・チェック状態は変えない。同じ成果物を既に表していれば追記しない。追記は `### M/D (added)`（補足節の手前に入る）。手書きメモを正式版にするときは `desc_replace`（原文はコメントに保存してから）、仮置き 1 行の削除は `desc_drop`。
- `language.description: en` の案件は日本語本文を英訳して取り込む（原文は残さない）。旧形式 `[{link_label}](URL)` 1 本は新形式に置換し旧 URL を当該日付として保持（`--prev-links`）。トラッカー無しの会議でも同 No. の兄弟チケットが持つ最新のリンク行を引き継ぐ。
- 他チケット参照は `[{PK}-nn]({site}/browse/{PK}-nn)`。**チェックボックス行の中にはリンクを入れない**（`* Related:` / `* <名前>: [URL](URL)` 行へ）。画像は Description に置かない（コメントへ）。スマートリンクは `[URL](URL)` に変換。
- DoD の出典（`— l.NNN` / `— {gate_token} M/D` / `— confirmed by`）は proposals とレポートに持ち、**Jira 本文には書かない**（スクリプトが落とす）。
- 既存チケットは一括書き換えしない。次にそのチケットへ追記するときにこの形へ寄せる（`jira_dump_summary.py --audit` の形式監査が対象一覧）。

### 4.3 粒度・分割・統合・リンク（案件共通）
- **1 チケット＝1 成果物**（閉じる条件 1 つ）。同じ課題 No. でも成果物が別なら別チケット（No. ラベルを共有）。顧客側アクションが主体のチケットには自社アクションの DoD を足さず、自社の約束は新規起票する。
- **閉じて作り直す**: 既存 DoD が全て `[x]` で新しい約束が別成果物 → 既存を Resolved、新規を起票し `Relates`、Background に Origin、旧側 DoD に「→ moved to {PK}-yy」。同じ成果物の続きなら追記。
- **チケットの Resolved とトラッカーの Status は独立**。トラッカー close は同 No. の全チケットを閉じる根拠。
- **リンク種別**: 成果物の切り出し＝`Work item split`。同 No. で並行する別成果物・作り直し＝`Relates`。統合＝吸収側を `Duplicate` で結び Resolved。同 No. は全ペア `Relates`（スクリプトが自動列挙。ダンプの `issuelinks` にある既存リンクは除外）。統合の残す側はサマリ併記＋Merge note。

## 5. コネクタ制約（Atlassian MCP・案件共通。REST 版 `jira_api.py` では該当しないものに ※）
- MCP の Description 読み書きは**常に markdown 往復**（ADF 指定は無視）。API 応答は送った文字列を返すので**描画崩れに気づけない**。※REST 版は ADF を直接書き、書いた直後に再取得して差分検証する。
- 往復で壊れるもの: **画像** `![](blob:…)`（復元不可）、**スマートリンク** `<custom data-type="smartlink">`（文字列化）、**リンク入りチェックボックス行**（タスクリストが箇条書きに落ち `\[ \]` が残る）。
- 回避: 画像入り Description は**編集しない**（画像をコメントへ移すよう案内）。スマートリンクは `[URL](URL)` へ。チェック行のリンクは外へ。`jira_sync_report.py` が自動処理し `--validate` で検査。
- **サブエージェントからは MCP を呼べない**（コネクタの OAuth はメインセッション限定）。Phase 0／B をサブエージェントに委譲する構成は不可。REST 版なら Bash から呼ぶだけなので不要。
- 新規起票はバックログに入る。ボード移動は REST Agile API・MCP とも未対応 → 手作業。コメントは削除不可（ロールバックは本文を "(rolled back)" に更新）。

## 6. 自己チェック（書き込み前）
- [ ] 突合表: トラッカー由来の当日アクションが全て `e{code}` と DoD に入っている（`tracker.enabled` の案件）。
- [ ] 候補表: トラッカーに無い DoD は `confirmed by` のものだけ。
- [ ] DoD 出典抜粋を 1 件ずつ見て、直下の発言が約束（「〜します」型）である。引用に無い固有名詞・数値を足していない。結論からの逆引きで「失効」「吸収」にした候補を DoD にしていない。
- [ ] DoD 各行が A1〜A6・C1・C2 を満たす（内包・口頭伝達の `[x]`・「共有する」単体・継続的な取り決めが無い）。
- [ ] 同 No. の既存チケット（Resolved 含む）と DoD が重複していない。
- [ ] `--validate` が NG ゼロ（節・Background 行数・DoD 件数・証跡・画像・smartlink・チェック行内リンク・言語・素の課題キー・リンク先の存在）。
- [ ] 手動コメント／個人メモとの矛盾は「訂正提案」に出した。
- [ ] Resolved 遷移には完了の発言かトラッカー close がある。dump と違う status・担当・期限を戻していない。
- [ ] `assignable: false` の当事者に Assignee を付けていない（ラベル／備考で代替）。
- [ ] 書き込み直前の鮮度チェックを行った。

## 7. 補助スクリプト（`scripts/`。すべて `--profile` でプロファイルを読む）
- `jira_api.py --profile … {myself|fetch|write|transitions|adf}` … **Jira Cloud REST v3 直叩き**（MCP 代替）。認証は環境変数 `JIRA_EMAIL`/`JIRA_API_TOKEN` か `~/.config/jira.env`。`fetch`（Phase 0。ダンプ JSON＋要約ビュー）／`write`（Phase B。既定ドライラン、`--apply` で書く。鮮度チェック→コメント→fields+description→遷移→新規→継続コメント→リンク。Description は再取得して差分検証。`--report` で実行ログをレポート末尾へ）／`transitions --key`（遷移 ID 一覧。プロファイルを埋めるとき）／`adf --md --back`（往復確認）。
- `jira_dump_summary.py --profile … --dump … --out … [--full KEYS] [--audit]` … ダンプ → 要約ビュー md（1 件 10 行前後）。`--audit` で形式監査（節・Background 行数・DoD 件数・`[x]` 証跡・`jira.placement` によるエピック配置）。Phase A の入力。
- `jira_sync_report.py --profile …` … content＋proposals＋ダンプ（＋トラッカースキャン＋文字起こし）→ レポート md・プレビュー md・payload json（`tickets` / `new_tickets` / `links`）。会議種別・エピック・ラベル・節名・言語・DoD ゲート・規則をプロファイルから読む。`--validate` で payload を検査。
- `check_desc.py --lang en|ja|any` … MCP 書き込み応答の description（stdin）を検査。
- `profile_lint.py <profile.md> [--public]` … プロファイル frontmatter の必須キー・型・整合性を検査（見本は `--public`）。新案件のドライラン前と、プロファイルを編集したあとに通す。
- `run_regression.py [--fixtures-dir DIR] [--strict] [--update]` … `tests/fixtures/`（架空データ）と外部 fixture（実案件・リポジトリ外）を再実行し、payload（`--strict` で report md も）が期待値と一致するか確認。**scripts/ を変更したら必ず全ケース緑にしてから使う**。
- 追加の決まりは `scripts/README.md`。候補台帳はスクリプト `SCRIPT_BACKLOG.md`・スキル `SKILL_BACKLOG.md`。

## 8. 新しい案件を追加する（プロファイルの作り方）
1. `cp PROFILE_TEMPLATE.md <作業ディレクトリ>/jira_profiles/<id>.md`（リポジトリの外。§0 の探索先のいずれか）。frontmatter を埋める。分からない値（遷移 ID など）は空にして `status: draft`。
2. 本文 A〜F 節を書く: **A 出典の正** / **B 採用ゲート**（トラッカー由来をどう無条件採用するか・会議種別・エピックの使い分け）/ **C トラッカーのスキャン手順**（無ければ「無し」）/ **D フィールド規則**（優先度・期限・ステータス・Assignee）/ **E 記述テンプレの差分** / **F 完了後**。`examples/example-weekly-sync.md`（トラッカー有り・英日・課題 No. 体系有り）と `examples/example-sprint-kanban.md`（トラッカー無し・日本語のみ・No. 無し）が両端の見本。
3. `scripts/profile_lint.py <profile.md>` を通す（ERROR ゼロ）。`jira_api.py --profile … myself` で認証を確認し、`transitions --key` で遷移 ID を埋める。過去の会議 1 回分で手順 0〜5 を回し、レポートをユーザーが確認。問題なければ `status: verified`。その回の入力と payload を実案件 fixture（リポジトリ外）として保存し、以後の回帰に使う。
4. 案件の Jira 記載ガイドラインが別にあれば、プロファイルから参照し重複して書かない。
5. 案件専用の呼び出し口が必要なら、`scripts/` の各スクリプトに `--profile` を自動付与する薄いラッパーを案件側に置く（スクリプト本体は複製しない）。

## 9. 改訂履歴
- 2026-10-04 v1.2: 母体案件の v2.2〜v2.5b（2026-09-29〜10-03）を取り込み。**REST 版 3 段モデル**（`jira_api.py` fetch/write/transitions、`jira_dump_summary.py --audit`）、会議種別 weekly/internal/customer、複数エピック（`jira.parents`・`labels.track`・`--parent`）、Description 5 節（Purpose／Deliverable contents）と `description.rules`（節固定・Background 3〜5 行・DoD 3〜5 件・`[x]` 証跡）、DoD 判定基準 A1〜A6/C1/C2/B1〜B5、結論からの逆引き判定、`desc_replace`/`desc_drop`/`bg_over_reason`/`--out-preview`、既存リンクの自動除外、兄弟チケットからのトラッカー行引き継ぎ、手動変更を戻さない規則、`tracker.promise_marker`。実案件 fixture を 2 件（9/25・10/2）にし、案件側スクリプトを本リポへ一本化（案件側はラッパー）。
- 2026-09-27 v1.1: 改善ループ 3 層（手順 8・`SCRIPT_BACKLOG.md`・`SKILL_BACKLOG.md`・プロファイル `ledgers`・`scripts/README.md`）、`run_regression.py`・`profile_lint.py`、`tests/fixtures/` を追加。
- 2026-09-27 v1: 単一案件専用スキルから汎用化。プロファイル分離、スクリプトのプロファイル駆動化（母体案件の実データで payload 一致を確認）、サンプルプロファイル 2 種を追加。
