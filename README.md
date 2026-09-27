# mtg-jira-sync

会議資料（要約・裏取り台帳・cleaned 文字起こし）と案件のトラッカー（管理表 Excel 等・任意）から、当日議論した課題ごとの議事録・決定・各社アクションを起こし、Jira チケットへ **会議日付きコメント / Description（Background・DoD）/ フィールド・遷移・新規起票・リンク** として反映する [Claude Code](https://claude.com/claude-code) スキル。

**汎用コア（`SKILL.md`）＋ 案件プロファイル（`<id>.md`・リポジトリの外に置く）** の 2 層構成。案件固有の値（Jira プロジェクト・エピック・ラベル・言語・トラッカーの列名…）と判断規則はプロファイルに閉じ込め、本体は案件を問わず同じ手順で動く。**ドライラン → 承認 → 書き込み**。

## 構成

```
SKILL.md               汎用コア（原則・手順・記述規約・コネクタ制約・自己チェック）
PROFILE_TEMPLATE.md    新案件用テンプレ（YAML frontmatter＝定数、本文 A〜F 節＝判断規則）
examples/
  example-weekly-sync.md     見本 1: 顧客管理表あり・英日併記・課題 No. 体系あり
  example-sprint-kanban.md   見本 2: トラッカーなし・日本語のみ・Kanban／スプリント
scripts/
  jira_sync_report.py  content＋提案＋Jira ダンプ → ドライランレポート md＋書き込み payload json（--validate 付き）
  check_desc.py        書き込み応答の Description を検査（チェックリスト崩れ・スマートリンク・画像・言語）
  profile_lint.py      プロファイル frontmatter の検査
  run_regression.py    fixtures を再実行して payload／report の一致を確認
  README.md            スクリプト追加の契約
tests/fixtures/        架空データの回帰ケース（実案件の fixture はリポジトリ外）
SCRIPT_BACKLOG.md      補助スクリプトの候補台帳（改善ループ・スクリプト層）
SKILL_BACKLOG.md       隣接・新規スキルの候補台帳（改善ループ・スキル層）
CHANGELOG.md
```

## 前提

- Claude Code ＋ Atlassian MCP コネクタ（Jira の検索・取得・編集・コメント・遷移・リンク作成）。
- Python 3.10 以上と `PyYAML`（プロファイルの frontmatter を読む）。
- 会議 dir に要約・cleaned 文字起こし・（あれば）裏取り台帳。上流の要約スキルは別途。

## インストール

```bash
git clone <this repo> ~/Documents/mtg-jira-sync
ln -s ~/Documents/mtg-jira-sync ~/.claude/skills/mtg-jira-sync
```

コピーでもよい。

実案件のプロファイルは **このリポジトリの外**に置く（ファイル名に案件名が入るため、リポジトリ内には置かない）。探索順:

1. 環境変数 `MTG_JIRA_SYNC_PROFILES` のディレクトリ
2. 作業ディレクトリ直下の `jira_profiles/`
3. `~/.config/mtg-jira-sync/profiles/`

```bash
mkdir -p ~/work/<案件ワークスペース>/jira_profiles
cp ~/Documents/mtg-jira-sync/PROFILE_TEMPLATE.md ~/work/<案件ワークスペース>/jira_profiles/<id>.md
```

## 使い方

```
/mtg-jira-sync <profile-id> <会議dir> [tracker-url]
```

1. プロファイル解決 → Jira ダンプ → （あれば）トラッカースキャン → content JSON → 提案設定。
2. `scripts/jira_sync_report.py --profile <解決したプロファイルのパス> … --validate` でドライランレポートと payload を生成。
3. レポートを確認し「全件承認」「PRJ-xx を除外」「候補 C1 を採用」などで指示。
4. 承認分のみ書き込み。前後スナップショット・鮮度チェック・応答検査つき。

## 改善ループ（足りないものを増やす仕組み・3 層）

1. 実行のたびに、モデルが手で書いたコードや繰り返した確認（**スクリプト層** → `SCRIPT_BACKLOG.md`）、判断に迷った案件規則（**プロファイル層** → 該当プロファイル）、範囲外だが毎回やっている定常業務（**スキル層** → `SKILL_BACKLOG.md`）を実行ログに記録し、台帳へ追記する。
2. 2 回以上・手順が安定・入出力が定型の候補は、終了時にユーザーへ提案する（承認制）。
3. スクリプトを作成したら `tests/fixtures/` に架空データのケースを足し、`scripts/run_regression.py` が全ケース緑であることを確認してから使う。実案件の fixture はリポジトリの外に置き `--fixtures-dir` で追加する。

```bash
python scripts/run_regression.py --strict                      # 同梱の架空ケース
python scripts/run_regression.py --fixtures-dir <外部fixture>   # 実案件ケースも
python scripts/profile_lint.py <profile.md>                    # プロファイル検査
```

## 開発を再開するとき

1. `git status` と `CHANGELOG.md`・`SCRIPT_BACKLOG.md` を読む。
2. `python scripts/run_regression.py --strict`（外部 fixture があれば `--fixtures-dir` も）を全ケース緑にする。
3. `SKILL.md` §9 改訂履歴の最終行が現状。設計判断は §0（プロファイル優先）・§1・`scripts/README.md`（契約）。
4. 変更したら回帰 → `CHANGELOG.md` → 顧客名スキャン → コミット。

## 新しい案件を追加する

`SKILL.md` §8 のとおり。`PROFILE_TEMPLATE.md` をコピーし、frontmatter と A〜F 節を埋め、過去の会議 1 回分でドライランまで回してから `status: verified` に上げる。

## セキュリティ上の注意

- 実案件のプロファイルは顧客名・Atlassian テナント ID・担当者名を含み、**ファイル名自体が案件名になる**ため、リポジトリの外に置く。`.gitignore` の `profiles/` `jira_profiles/` は万一の安全網。公開してよい見本は `examples/` に架空値で置く。
- スクリプトは Jira に書き込まない。書き込みは MCP 経由で、承認後にのみ行う。
- 認証情報はスキルもスクリプトも扱わない（MCP コネクタ側）。

## ライセンス

[MIT](LICENSE)
