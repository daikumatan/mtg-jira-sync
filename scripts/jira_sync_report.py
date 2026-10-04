#!/usr/bin/env python3
"""
/mtg-jira-sync 補助（プロファイル駆動・汎用版）:
content JSON + 提案設定 + Jira ダンプ (+ トラッカースキャン + 文字起こし) → ドライラン差分レポート(md)・書き込みプレビュー(md)・payload(json)。
Jira への書き込みは行わない（payload は承認後に jira_api.py write --apply か MCP で書く）。案件固有の定数はすべて --profile の YAML frontmatter から読む。

usage:
  python jira_sync_report.py --profile <profiles/xxx.md> --content <content.json> --jira-dump <dump.json> \
      --proposals <proposals.json> --date 2026-09-25 [--meeting-type weekly|internal|customer] [--meeting-name "..."] \
      [--parent <alias|KEY-nn>] [--track-label <label>] [--tracker-url <URL>] [--prev-links '{"url":"9/18"}'] \
      [--tracker-scan <scan.json>] [--transcript <cleaned.txt>] [--validate] [--out-preview <preview.md>] \
      --out-md <report.md> --out-payload <payload.json>
exit: 0 正常 / 2 validate NG（--validate 時）
"""
import argparse, json, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True, help="案件プロファイル md（YAML frontmatter を読む）")
ap.add_argument("--content", required=True)
ap.add_argument("--jira-dump", required=True, help="Jira ダンプ JSON（jira_api.py fetch または MCP 検索結果）")
ap.add_argument("--proposals", required=True)
ap.add_argument("--date", required=True)          # YYYY-MM-DD
ap.add_argument("--meeting-type", choices=["weekly", "internal", "customer"], default="weekly",
                help="weekly=定例（トラッカーあり） / internal=社内会議（トラッカーなし・全アクション候補） / customer=顧客臨時会議（トラッカーなし・顧客同席の約束は確定扱い）")
ap.add_argument("--meeting-name", default="", help="internal / customer のときの会議名（コメント見出しに使う）")
ap.add_argument("--parent", "--epic", dest="parent", default="", help="新規起票の parent エピック（jira.parents の別名か課題キー。既定 jira.parent）")
ap.add_argument("--track-label", default=None, help="全件に付ける系統ラベル（既定 labels.track[parent]）")
ap.add_argument("--tracker-url", "--excel-url", dest="tracker_url", default="", help="トラッカー（管理表等）の URL。Description の日付リンク行に使う")
ap.add_argument("--prev-links", default="{}", help='旧リンクの日付ラベル JSON 例 {"https://...":"9/18"}')
ap.add_argument("--tracker-scan", "--excel-scan", dest="tracker_scan", default="", help="トラッカースキャン json（todos 付き）→ 冒頭に TODO 突合表")
ap.add_argument("--transcript", default="", help="cleaned 文字起こし。DoD 出典行を自動抜粋して照合欄に出す")
ap.add_argument("--validate", action="store_true", help="payload を検査し NG があれば exit 2")
ap.add_argument("--out-preview", default="", help="書き込み内容だけを並べたプレビュー md（差分・出典抜粋なし。手元チェックと Phase B の書き込み手順書に使う）")
ap.add_argument("--out-md", required=True)
ap.add_argument("--out-payload", required=True)
a = ap.parse_args()

# ---------------- profile ----------------
def load_profile(path):
    txt = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m: sys.exit(f"profile に YAML frontmatter が無い: {path}")
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML が無い。プロファイルの python（venv）で実行するか pip install pyyaml")
    return yaml.safe_load(m.group(1)) or {}

P = load_profile(a.profile)
def pget(path, default=None):
    cur = P
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur

PROJECT_NAME = pget("project_name", pget("profile", "project"))
MEETING_EN   = pget("meeting.name_en", "Weekly Sync")
SITE         = (pget("jira.site") or "").rstrip("/")
BROWSE       = SITE + "/browse/"
PK           = pget("jira.project_key")
PARENTS      = pget("jira.parents", {}) or {}            # 別名 → エピックキー
def resolve_parent(x):
    x = (x or "").strip()
    return PARENTS.get(x, x) if x else pget("jira.parent")
PARENT       = resolve_parent(a.parent)
ISSUE_TYPE   = pget("jira.issue_type", "Task")
RESOLVED_ID  = str(pget("jira.resolved_transition_id", ""))
LINK_TYPES   = pget("jira.link_types", ["Relates", "Work item split", "Duplicate"])
REF_RE       = pget("summary.ref_regex")            # 例 '\[#(\d+)\]'。None なら課題 No. 体系無し
PREFIX_RE    = pget("summary.prefix_regex")         # 例 '^\[(#\d+\]|Other\])'。None なら検査しない
FIXED_LABELS = pget("labels.fixed", []) or []
REF_LABEL    = pget("labels.ref_label")             # 例 'no-{n:02d}'。None なら付けない
TRACK_MAP    = pget("labels.track", {}) or {}       # エピックキー → 系統ラベル
MT_LABELS    = pget("labels.meeting_type", {}) or {}   # weekly/internal/customer → ラベル
PARTIES      = pget("parties", []) or []
LANG_COMMENT = pget("language.comment", ["en", "ja"]) or ["en"]
LANG_DESC    = pget("language.description", "any")
TRK_ON       = bool(pget("tracker.enabled", False))
TRK_NAME     = pget("tracker.name", "トラッカー")
TRK_LABEL    = pget("tracker.link_label", "Tracker")
TRK_URL_REQ  = bool(pget("tracker.url_required", False))
GATE_TOKEN   = pget("tracker.gate_token", "TRACKER")
SEC          = {"purpose": None, "background": "Background", "dod": "Definition of Done", "deliverable_contents": None, "nice_to_have": None, "materials": "Materials"} | (pget("description.sections", {}) or {})
SEC_ORDER    = [SEC[k] for k in ("purpose", "background", "dod", "deliverable_contents", "nice_to_have", "materials") if SEC.get(k)]
RULES        = pget("description.rules", {}) or {}  # sections_strict / background_std / background_max / background_line_chars / dod_std / dod_max / done_evidence
TITLE_LINE   = bool(pget("description.title_line", True))
TZ_HOURS     = float(pget("meeting.tz_offset_hours", 9))   # 会議日の暦日を決める TZ（既定 JST）
if not (PK and SITE): sys.exit("profile の jira.project_key / jira.site は必須")

MT = a.meeting_type
_NM = a.meeting_name.strip()
if MT == "weekly":
    SYNC = MEETING_EN
    MTG_JA = PROJECT_NAME
elif MT == "customer":
    SYNC = f"{pget('meeting.customer_name_en', 'Customer Meeting')} ({_NM})" if _NM else pget("meeting.customer_name_en", "Customer Meeting")
    MTG_JA = f"{pget('meeting.customer_name_ja', '顧客会議')} {_NM}".rstrip()
else:
    SYNC = f"{pget('meeting.internal_name_en', 'Internal Sync')} ({_NM})" if _NM else pget("meeting.internal_name_en", "Internal Sync")
    MTG_JA = f"{pget('meeting.internal_name_ja', '社内会議')} {_NM}".rstrip()
MTG_LABEL = MT_LABELS.get(MT)
TRACK = a.track_label if a.track_label is not None else TRACK_MAP.get(PARENT)

KEY_RE = re.compile(r"(https?://[^\s)]+)|(?<![\[/\w-])(" + re.escape(PK) + r"-\d+)\b(?!\]\()")
def _linkify_line(text):
    """素の課題キーをリンク化。URL の内部（…selectedIssue=KEY-112 等）は触らない"""
    return KEY_RE.sub(lambda m: m.group(1) if m.group(1) else f"[{m.group(2)}]({BROWSE}{m.group(2)})", text)
def linkify(text, skip_checkbox=True):
    """素の課題キーをリンク化（チェック行は除外）"""
    return "\n".join(l if (skip_checkbox and re.match(r"\s*- \[[ x]\]", l)) else _linkify_line(l) for l in text.split("\n"))
def bare_keys(text):
    """リンク化漏れの素キー（URL 内は除外）"""
    return [m.group(2) for m in KEY_RE.finditer(text) if m.group(2)]
GATE = re.compile(rf"{re.escape(GATE_TOKEN)}|confirmed by|^\[x\]")
STRIP_SRC = re.compile(rf"\s+—\s+(l\.|{re.escape(GATE_TOKEN)}|confirmed by).*$")
no_of = (lambda summ: [int(x) for x in re.findall(REF_RE, summ or "")]) if REF_RE else (lambda summ: [])
def ref_labels(summ):
    return [REF_LABEL.format(n=n) for n in no_of(summ)] if REF_LABEL else []
REF_LABEL_RE = re.compile("^" + re.escape(REF_LABEL.split("{")[0]) + r"\d+$") if REF_LABEL else None
def party_of(org):
    for p in PARTIES:
        if org and org.lower() in {str(p.get("code", "")).lower(), str(p.get("name_en", "")).lower(), str(p.get("name_ja", "")).lower()}: return p
    return None
def multilang(parts):
    """{'en': [...], 'ja': [...]} → language.comment の順に結合。複数言語は --- 区切り"""
    segs = ["\n".join(parts[l]) for l in LANG_COMMENT if parts.get(l)]
    return "\n\n---\n".join(segs) + "\n"
JA_RE = re.compile(r"[぀-ヿ一-鿿]")

# ---------------- inputs ----------------
content = json.load(open(a.content, encoding="utf-8"))
dump = json.load(open(a.jira_dump, encoding="utf-8"))
props = json.load(open(a.proposals, encoding="utf-8"))
prev_links = json.loads(a.prev_links)
issues = {n["key"]: n["fields"] | {"key": n["key"]} for n in dump["issues"]["nodes"]}
Y, M, D = a.date.split("-")
mlabel = f"{int(M)}/{int(D)}"
tracker_url = a.tracker_url.strip()

def nz(s): return (s or "").strip()
def local_date(iso):
    """Jira の created (例 2026-09-24T18:46:23.165-0700) → 会議 TZ の暦日 'YYYY-MM-DD'。API はアカウント TZ で返すため必ず変換する"""
    from datetime import datetime, timezone, timedelta
    try:
        dt = datetime.strptime(re.sub(r"(\.\d+)?([+-]\d{2}):?(\d{2})$", r"\2\3", iso), "%Y-%m-%dT%H:%M:%S%z")
        return dt.astimezone(timezone(timedelta(hours=TZ_HOURS))).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]
TR = Path(a.transcript).read_text(encoding="utf-8").splitlines() if a.transcript else []
def excerpt(ref, maxlines=6, width=110):
    """'l.25-31' / 'l.39-42, 76-80' → 文字起こし該当行を抜粋"""
    out = []
    for m in re.finditer(r"(\d+)(?:-(\d+))?", ref or ""):
        s_, e_ = int(m.group(1)), int(m.group(2) or m.group(1))
        for i in range(s_, min(e_, s_ + maxlines - 1) + 1):
            if 1 <= i <= len(TR): out.append(f"    l.{i}: {TR[i-1][:width]}")
        if e_ - s_ + 1 > maxlines: out.append(f"    … (l.{s_+maxlines}-{e_} 省略)")
    return out

def comment_body(c, part=None):
    """content エントリ → 多言語コメント本文。part: {"d_key":..} 等の上書き。"""
    c = dict(c); c.update(part or {})
    en, ja = [f"## {a.date} {SYNC}"], [f"## {a.date} {SYNC}"] if "en" not in LANG_COMMENT else []
    if nz(c.get("d_en")): en.append(f"**Minutes:** {c['d_en'].strip()}")
    if nz(c.get("l_en")): en.append(f"**Decision / Background:** {c['l_en'].strip()}")
    if nz(c.get("req_en")): en.append(f"**Requests / proposals (not committed):** {c['req_en'].strip()}")
    for p in PARTIES:
        k = p["code"]
        if nz(c.get(f"e{k}_en")):
            en.append(f"**{p.get('name_en', k.upper())} action:** {c[f'e{k}_en'].strip()} — Owner: {nz(c.get(f'f{k}_en')) or p.get('owner_default_en', 'TBC')} — Due: {nz(c.get(f'g{k}')) or 'TBC'}")
    refs = [x for x in [nz(c.get("ref")), nz(c.get("url"))] if x]
    if refs: en.append(f"**Refs:** {' / '.join(refs)}")
    if nz(c.get("src")): en.append(f"**Source:** transcript {c['src'].strip()}")
    if nz(c.get("d")): ja.append(f"**議事録:** {c['d'].strip()}")
    if nz(c.get("l")): ja.append(f"**決定・経緯:** {c['l'].strip()}")
    if nz(c.get("req")): ja.append(f"**要望・提案（未確定）:** {c['req'].strip()}")
    for p in PARTIES:
        k = p["code"]
        if nz(c.get(f"e{k}")):
            ja.append(f"**{p.get('name_ja', k.upper())} アクション:** {c[f'e{k}'].strip()} — 担当: {nz(c.get(f'f{k}')) or p.get('owner_default_ja', '未定')} — 期限: {nz(c.get(f'g{k}')) or '未定'}")
    if "en" not in LANG_COMMENT:
        if refs: ja.append(f"**参考:** {' / '.join(refs)}")
        if nz(c.get("src")): ja.append(f"**出典:** 文字起こし {c['src'].strip()}")
    return linkify(multilang({"en": en, "ja": ja}), skip_checkbox=False)

LINK_RE = re.compile(r"^\s*\*\s.*\[" + re.escape(TRK_LABEL) + r"\]\((https?://[^)\s]+)\).*$", re.M)   # 旧形式 1 本リンク
TRK_LINE_RE = re.compile(r"^\* " + re.escape(TRK_LABEL) + r":.*$", re.M)                               # 新形式（日付リンク列挙）
H_BG, H_DOD, H_MAT = f"## {SEC['background']}", f"## {SEC['dod']}", f"## {SEC['materials']}"
_after = [re.escape(SEC[k]) for k in ("deliverable_contents", "nice_to_have", "materials") if SEC.get(k)]
AFTER_DOD_RE = re.compile(r"^## (" + "|".join(_after) + r").*$", re.M) if _after else None
CB_RE = re.compile(r"\s*- \[[ x]\]")

def sibling_tracker_line(key, summary=None):
    """同じ課題 No. を持つ他チケットの `* {TRK_LABEL}:` 行（日付リンクが最も多いもの）を返す。無ければ None"""
    nos = set(no_of(summary or issues.get(key, {}).get("summary", "")))
    if not nos: return None
    best = None
    for k2, f2 in issues.items():
        if k2 == key or not (nos & set(no_of(f2.get("summary", "")))): continue
        m2 = TRK_LINE_RE.search(f2.get("description") or "")
        if m2 and (best is None or m2.group(0).count("](") > best.count("](")): best = m2.group(0)
    return best

def dod_lines(dod):
    return "\n".join(f"- [{'x' if d.startswith('[x]') else ' '}] {STRIP_SRC.sub('', d[3:].strip() if d.startswith(('[x]','[ ]')) else d)}" for d in dod)

def as_bullets(bg):
    """background_en（文字列 or 配列）→ トップレベル箇条書きの行リスト（`* ` が無い行には付ける）"""
    bg = bg if isinstance(bg, list) else ([bg] if nz(bg) else [])
    return [b.rstrip() if re.match(r"^\s*([*-]|\d+\.) ", b) or not b.strip() else "* " + b.strip() for b in bg]

def new_desc(key, title_en, skip_reason=None, dod=None, background_en=None, title_replace=None, desc_drop=None, desc_replace=None):
    """Description のトラッカーリンク行を新形式にし、必要なら Background/DoD を作る。戻り値 (new_text or None, note)"""
    cur = issues[key].get("description") or ""
    raw = cur
    if skip_reason: return None, skip_reason
    if desc_replace:   # 既存本文を丸ごと差し替える（手書きメモを正式版にするとき。原文はコメントに残す前提）
        cur = desc_replace if isinstance(desc_replace, str) else "\n".join(desc_replace)
        note0 = "Description を全面差し替え（旧本文は Jira コメントに保存済みであること）"
    else:
        note0 = ""
    for d_ in (desc_drop or []):   # 仮置きの 1 行を削除
        cur = "\n".join(l for l in cur.split("\n") if l.strip() != d_.strip())
    n_sl = len(re.findall(r'<custom data-type="smartlink"[^>]*>', cur))
    cur = re.sub(r'<custom data-type="smartlink"[^>]*>\s*(https?://[^<\s]+)\s*</custom>', r"[\1](\1)", cur)  # 書き戻すと文字列化するため通常リンクへ
    if "![](" in cur: return None, "画像を含むため編集スキップ（画像をコメントへ移せば自動更新可）"
    if TRK_ON and TRK_URL_REQ and MT == "weekly" and not tracker_url: return None, "tracker-url 未指定（リンク再指定 or リンク無し を確認）"
    bg = as_bullets(background_en)
    links, line, m = [], "", LINK_RE.search(cur)
    if TRK_ON and not tracker_url and TRK_LABEL not in cur:   # トラッカーなしの会議でも、同じ No. の兄弟が持つ最新のリンク行を引き継ぐ
        line = sibling_tracker_line(key) or ""
    if TRK_ON and tracker_url:
        if m:
            old = m.group(1); links.append((prev_links.get(old, "prev"), old))
        links.append((mlabel, tracker_url))
        line = f"* {TRK_LABEL}: " + ", ".join(f"[{d}]({u})" for d, u in links)
    ins = "\n".join(x for x in [line] + bg if x)   # 挿入ブロック（リンク行＋Background 箇条書き）
    ttl = f"* Title: {title_en}" if TITLE_LINE and nz(title_en) else ""
    if m and line:
        new = LINK_RE.sub(line, cur, count=1); note = "旧形式リンク行を新形式へ置換（旧URLは前回日付として保持）" + (f"＋スマートリンク {n_sl} 本を通常リンク化" if n_sl else "")
        if bg: new = new.replace(line, line + "\n" + "\n".join(bg), 1); note += "＋ Background 箇条書きを追記"
    elif H_BG in cur:
        m_new = TRK_LINE_RE.search(cur)   # 新形式のリンク行
        if m_new and line:   # 新形式の既存行に当日リンクを追記（重複行を作らない）
            nl = m_new.group(0) if tracker_url in m_new.group(0) else m_new.group(0).rstrip() + f", [{mlabel}]({tracker_url})"
            new = cur[:m_new.start()] + nl + cur[m_new.end():]; note = f"{TRK_LABEL} 行に当日リンクを追記"
            if bg: new = new.replace(nl, nl + "\n" + "\n".join(bg), 1); note += "＋ Background 箇条書きを追記"
        elif (m or m_new) and bg and not line:   # 既存のリンク行の直後に Background 箇条書き
            e = (m_new or m).end(); new = cur[:e] + "\n" + "\n".join(bg) + cur[e:]; note = f"既存 {TRK_LABEL} 行の直後に Background 箇条書きを挿入"
        elif ins: new = (cur.replace(H_BG + "\n\n", H_BG + "\n\n" + ins + "\n", 1) if H_BG + "\n\n" in cur else cur.replace(H_BG, H_BG + "\n\n" + ins, 1)); note = f"{H_BG} 直下に" + ("リンク行" if line else "") + ("＋" if line and bg else "") + ("Background 箇条書き" if bg else "") + "を挿入"
        else: new = cur; note = "Background 既存・挿入なし"
    elif not cur.strip():
        new = f"{H_BG}\n\n" + "\n".join(x for x in [line, ttl] + bg if x) + "\n"; note = f"Description 空 → {SEC['background']} 新設" + ("（Title=トラッカー）" if MT == "weekly" and ttl else "")
    elif re.search(r"^## ", cur, re.M):
        if not (ins or ttl): new = cur; note = "既存本文のみ・追記内容なし"
        else: new = f"{H_BG}\n\n" + "\n".join(x for x in [line, ttl] + bg if x) + f"\n\n{cur}"; note = f"既存本文の前に {SEC['background']} を追加（本文は無変更）"
    else:
        body = "\n".join(bg) if bg else f"* Background: {cur.strip()}"
        new = f"{H_BG}\n\n" + "\n".join(x for x in [line, ttl, body] if x) + "\n"; note = f"既存の短文を {SEC['background']} 箇条書きに取り込み"
    # チェックボックス行内のリンクは外へ（コネクタがタスクリストを箇条書きに落とすため）
    out_lines, moved = [], []
    for l in new.split("\n"):
        if CB_RE.match(l) and "](" in l:
            lks = re.findall(r"\[([^\]]*)\]\((https?://[^)]+)\)", l)
            l = re.sub(r"\s*\(?\[([^\]]*)\]\((https?://[^)]+)\)\)?", lambda m: f" ({m.group(1)})" if m.group(1) else "", l)
            moved += [f"* {t or 'Link'}: [{u}]({u})" for t, u in lks]
        out_lines.append(l)
    if moved:
        new = "\n".join(out_lines).rstrip("\n") + f"\n\n{H_MAT} (links moved from checklist)\n\n" + "\n".join(moved) + "\n"; note += f"＋チェックボックス内リンクを {SEC['materials']} へ移動"
    else:
        new = "\n".join(out_lines)
    new = linkify(new)
    if note0:
        note = note0 + ("＋" + note if note and note != "Background 既存・挿入なし" else "")
    if title_replace:
        new = re.sub(r"^\* Title:.*$", title_replace, new, count=1, flags=re.M); note += "＋ Title 行を置換"
    if dod:
        dod = [d for d in dod if GATE.search(d)]   # トラッカー由来・承認済み・完了のみ DoD へ
    if dod:
        items = dod_lines(dod)
        if SEC["dod"] in new or "## DoD" in new:
            block = f"\n\n### {mlabel} (added)\n\n{items}\n"
            mm = AFTER_DOD_RE.search(new) if AFTER_DOD_RE else None   # DoD 節の後ろの補足節（Deliverable contents / Materials 等）の手前に入れる
            if mm and mm.start() > new.find(SEC["dod"] if SEC["dod"] in new else "## DoD"):
                new = new[:mm.start()].rstrip("\n") + block + "\n" + new[mm.start():]
            else:
                new = new.rstrip("\n") + block
            note += "＋ DoD 追記"
        else:
            new = new.rstrip("\n") + f"\n\n{H_DOD}\n\n{items}\n"; note += "＋ DoD 新設"
    if new.strip() == raw.strip(): return None, "変更なし（追記内容なし・書き込みスキップ）"
    return new, note

md, payload, CANDS = [], {"date": a.date, "profile": pget("profile"), "meeting_type": MT, "parent": PARENT, "tracker_url": tracker_url, "tickets": {}}, []
md.append(f"# Jira 同期ドライラン — {a.date} {MTG_JA}（**未承認・Jira 未変更**）\n")
_HDR = {"weekly": f"- {TRK_NAME} URL: {tracker_url or '（未指定）'}" if TRK_ON else "- 会議種別: weekly",
        "customer": "- 会議種別: customer（顧客臨時会議・トラッカーなし。顧客同席のため会議中の約束は確定扱い。DoD は承認分のみ）",
        "internal": "- 会議種別: internal（トラッカーなし。DoD は承認分のみ。顧客合意ではない社内決定は Background に internal と明記）"}[MT]
md.append(f"- プロファイル: `{Path(a.profile).name}`\n" + _HDR + f"\n- 対象エピック: {PARENT} / 系統ラベル: {TRACK or '-'}" + f"\n- content: `{Path(a.content).name}` / 提案設定: `{Path(a.proposals).name}`\n")
if a.tracker_scan and TRK_ON:
    xs = json.load(open(a.tracker_scan, encoding="utf-8"))
    md.append(f"## {TRK_NAME} TODO 突合表（{TRK_NAME}が正・全件 ✓ が書き込み条件）")
    md.append(f"| No. | 組織 | {TRK_NAME} TODO | content 側 | 判定 |\n|---|---|---|---|---|")
    ng = 0
    for n, o in xs.items():
        for t in o.get("todos", []):
            c = content.get(n, {}); p = party_of(t.get("org")); side = f"e{p['code']}" if p else "e?"
            have = nz(c.get(side))
            ok = bool(have); ng += (not ok)
            md.append(f"| #{n} | {t['org']} | {t['text']}{'（前回TODO継続）' if t.get('carryover') else ''} | {have[:60] if have else '（空）'} | {'✓' if ok else '✗ 未反映'} |")
    md.append(f"\n未反映: **{ng} 件**\n")
md.append(f"## 承認の受け方\n「全件承認」／「{PK}-xx を除外」／「{PK}-xx の◯◯を修正」のいずれかで返答してください。承認された項目だけを書き込みます。\n")

for key, p in props["tickets"].items():
    f = issues.get(key)
    if p.get("written"):
        md.append(f"## {key} — **書き込み済み**（{p['written']}）\n"); continue
    if not f: md.append(f"## {key} — **チケットが見つかりません**\n"); continue
    md.append(f"## {key} `{f['summary']}`")
    md.append(f"- 現状: status={f['status']['name']} / priority={(f.get('priority') or {}).get('name')} / due={f.get('duedate')} / assignee={(f.get('assignee') or {}).get('displayName')} / labels={','.join(f.get('labels') or [])}")
    t = {"comment": None, "fields": {}, "transition": None, "description": None, "notes": list(p.get("notes", []))}
    if p.get("content"):
        c = content[p["content"]]; body = comment_body(c, p.get("part"))
        t["comment"] = body
        manual = [x for x in (f.get("comment") or {}).get("comments", []) if local_date(x["created"]) in {props.get("manual_comment_day"), a.date}]  # 会議日（会議 TZ の暦日）の手動コメント
        md.append(f"\n### 1. 追記予定コメント" + (f"（当日の手動コメント {len(manual)} 件あり → 重複部分は既知として省略済み）" if manual else ""))
        md.append("```\n" + body + "```")
    fl = {}
    if p.get("summary"): fl["summary"] = p["summary"]
    if p.get("duedate"): fl["duedate"] = p["duedate"]
    if p.get("priority"): fl["priority"] = {"name": p["priority"]}
    # 課題 No. ラベル: 提案後サマリ（改題があればそれ）の参照から機械的に付与
    auto = ref_labels(p.get("summary") or f["summary"])
    if REF_LABEL_RE:
        stray = [l for l in (f.get("labels") or []) if REF_LABEL_RE.match(l) and l not in auto]
        if stray: t["notes"].append(f"⚠ サマリに無い No. ラベル: {stray}（サマリと不一致）")
    add = [x for x in p.get("labels_add", []) + auto if x not in (f.get("labels") or [])]
    if add: fl["labels"] = sorted(set((f.get("labels") or []) + add))
    if p.get("assignee"): fl["assignee"] = p["assignee"]
    if fl or p.get("transition"):
        md.append("\n### 2. フィールド差分（提案）")
        if "summary" in fl: md.append(f"- summary: `{f['summary']}` → `{fl['summary']}`")
        if "duedate" in fl: md.append(f"- duedate: {f.get('duedate')} → **{fl['duedate']}**")
        if "priority" in fl: md.append(f"- priority: {(f.get('priority') or {}).get('name')} → **{p['priority']}**（{TRK_NAME} 優先度）")
        if "labels" in fl: md.append(f"- labels: +{', '.join(add)}")
        if "assignee" in fl: md.append(f"- assignee: {(f.get('assignee') or {}).get('displayName')} → **{fl['assignee']}**")
        if p.get("transition"):
            tr = p["transition"]; md.append(f"- status: {f['status']['name']} → **{tr['to']}**（遷移ID {tr['id']}）— 根拠: {tr.get('why','')}")
            t["transition"] = tr
    t["fields"] = fl
    nd, note = new_desc(key, p.get("title_en", p.get("title_jp","")), p.get("desc_skip"), p.get("dod"), p.get("background_en"), p.get("title_replace"), p.get("desc_drop"), p.get("desc_replace"))
    if p.get("desc_insert_after_link") and nd is not None:
        m2 = TRK_LINE_RE.search(nd) or re.search(r"^" + re.escape(H_BG) + r".*$", nd, re.M)
        nd = nd[:m2.end()] + "\n" + "\n".join(p["desc_insert_after_link"]) + nd[m2.end():]; note += "＋ 統合説明を挿入"
    md.append(f"\n### 3. Description: {note}")
    if nd is not None:
        t["description"] = nd
        md.append("```markdown\n" + nd.rstrip("\n") + "\n```")
    cands = [d for d in p.get("dod", []) if not GATE.search(d)]
    if cands:
        md.append("\n#### ⚠ 候補（未承認 → 今回は DoD に書かない。採用するなら番号で指示）" + {"internal": "（社内会議は全件候補）", "customer": "（顧客会議は全件候補。顧客同席の約束は確定扱いで承認を推奨）"}.get(MT, f"（{TRK_NAME}未記載）"))
        for i, d in enumerate(cands, 1):
            md.append(f"- C{i}. {d}")
            m4 = re.search(r"—\s*(l\.[\d,\-\s]+)", d)
            if m4 and TR: md += excerpt(m4.group(1), maxlines=8)
        CANDS.append((key, cands))
    if p.get("dod"):
        md.append("\n#### DoD 出典（文字起こし抜粋・Jira には書かない）— 各項目の直下の発言が「〜します」型の約束か確認する")
        for d in p["dod"]:
            md.append(f"- {d}")
            m3 = re.search(r"—\s*(l\.[\d,\-\s]+)", d)
            if m3 and TR: md += excerpt(m3.group(1))
            elif TR: md.append("    ⚠ 出典行なし → 採用不可（要望/提案なら req へ）")
    if t["notes"]:
        md.append("\n### 4. 訂正提案・要確認")
        md += [f"- {n}" for n in t["notes"]]
    md.append("")
    payload["tickets"][key] = t

# ---- 新規起票・分割・作り直し・リンク（proposals["new_tickets"] / proposals["links"]） ----
def lk(k): return k if k.startswith("NEW-") else f"[{k}]({BROWSE}{k})"

def new_ticket_desc(nt):
    """新規チケットの Description（プロファイルのセクション名で構成・言語は language.description）"""
    lines = []
    if SEC.get("purpose") and nz(nt.get("purpose")): lines += [f"## {SEC['purpose']}", "", nt["purpose"].strip(), ""]
    lines += [H_BG, ""]
    if TRK_ON and tracker_url and (no_of(nt["summary"]) or not REF_RE): lines.append(f"* {TRK_LABEL}: [{mlabel}]({tracker_url})")
    elif TRK_ON and no_of(nt["summary"]) and sibling_tracker_line(nt["placeholder"], nt["summary"]): lines.append(sibling_tracker_line(nt["placeholder"], nt["summary"]))
    if TITLE_LINE and nz(nt.get("title_en")): lines.append(f"* Title: {nt['title_en'].strip()}")
    o = nt.get("origin")
    if o:
        verb = {"split": "split from", "recreate": "follow-up to"}.get(nt.get("kind"), "related to")
        st = (issues.get(o, {}).get("status") or {}).get("name", "")
        tail = " (resolved)" if nt.get("kind") == "recreate" or st == "Resolved" else ""
        lines.append(f"* Origin: {verb} {lk(o)}{tail}" + (f". {nt['origin_summary_en'].strip()}" if nz(nt.get("origin_summary_en")) else ""))
    lines += as_bullets(nt.get("background_en") or nt.get("background") or [])
    dod = [d for d in nt.get("dod", []) if GATE.search(d)]
    if dod: lines += ["", H_DOD, "", dod_lines(dod)]
    dc = nt.get("deliverable_contents") or []
    if dc and SEC.get("deliverable_contents"): lines += ["", f"## {SEC['deliverable_contents']}", ""] + as_bullets(dc)
    nth = nt.get("nice_to_have") or []
    if nth and SEC.get("nice_to_have"): lines += ["", f"## {SEC['nice_to_have']}", "", dod_lines(nth)]
    mats = nt.get("materials") or []
    if mats: lines += ["", H_MAT, ""] + [f"* {m}" for m in mats]
    text = "\n".join(lines).rstrip("\n") + "\n"
    return linkify(text)

def origin_comment(nt):
    o = nt["origin"]
    en = [f"## Origin: {a.date} {SYNC}", nz(nt.get("origin_note_en")) or "(see full minutes)", f"Full minutes: {lk(o)}, comment dated {a.date}"]
    ja = ([f"## Origin: {a.date} {SYNC}"] if "en" not in LANG_COMMENT else []) + [nz(nt.get("origin_note_ja")) or "（詳細は元チケットの議事録）", f"議事録全文: {lk(o)} の {a.date} コメント"]
    return multilang({"en": en, "ja": ja})

def continuation_comment(ph, nt):
    en = [f"## {a.date} {SYNC}", f"All DoD items are complete. Follow-up deliverable continues in {ph} (`{nt['summary']}`)."]
    ja = ([f"## {a.date} {SYNC}"] if "en" not in LANG_COMMENT else []) + [f"DoD は全て完了。後続の成果物は {ph}（`{nt['summary']}`）で継続。"]
    return multilang({"en": en, "ja": ja})

existing_nos = {k: no_of(props["tickets"].get(k, {}).get("summary") or f["summary"]) for k, f in issues.items()}
pairs, links_out, skipped_links = set(), [], []
EXIST, EXIST_PAIRS = set(), {}   # ダンプに issuelinks があれば既存リンクを収集（無ければ空＝従来どおり）
for n in dump["issues"]["nodes"]:
    for il in (n["fields"].get("issuelinks") or []):
        other = (il.get("outwardIssue") or il.get("inwardIssue") or {}).get("key")
        if other:
            tn = (il.get("type") or {}).get("name", ""); pr = tuple(sorted([n["key"], other]))
            EXIST.add(pr + (tn,)); EXIST_PAIRS.setdefault(pr, set()).add(tn)
def add_link(frm, typ, to, why, auto=False):
    key = tuple(sorted([frm, to])) + (typ,)
    if frm == to or key in pairs: return
    if key in EXIST: pairs.add(key); skipped_links.append(f"{frm} —{typ}— {to}"); return
    if auto and key[:2] in EXIST_PAIRS:   # 自動候補は種別が違っても既にリンク済みなら足さない
        pairs.add(key); skipped_links.append(f"{frm} —{typ}— {to}（既存: {', '.join(sorted(EXIST_PAIRS[key[:2]]))}）"); return
    pairs.add(key); links_out.append({"from": frm, "type": typ, "to": to, "why": why, "auto": auto})

new_out = []
NEWS = props.get("new_tickets") or []
if NEWS:
    md.append("## 新規起票・分割・作り直し（起票後に返った key で placeholder を置換してからリンク・継続コメントを書く）\n")
for nt in NEWS:
    ph = nt.get("placeholder") or f"NEW-{len(new_out)+1}"; kind = nt.get("kind", "new"); o = nt.get("origin")
    if kind == "split" and o: add_link(o, "Work item split", ph, f"{o} の成果物を切り出し（split to {ph}）")
    elif o: add_link(o, "Relates", ph, {"recreate": "閉じて作り直し", "new": "同 No. 関連"}.get(kind, "関連"))
    for l in nt.get("links", []): add_link(ph, l.get("type", "Relates"), l["to"], l.get("why", "提案"))
    for n in no_of(nt["summary"]):  # 同 No. は全ペア Relates（Resolved 含む）
        for k, nos in existing_nos.items():
            if n in nos: add_link(ph, "Relates", k, f"同 #{n}", auto=True)
        for other in NEWS:
            oph = other.get("placeholder")
            if oph and oph != ph and n in no_of(other["summary"]): add_link(ph, "Relates", oph, f"同 #{n}", auto=True)
    desc = new_ticket_desc(nt)
    if kind == "split" and o: comment = origin_comment(nt)
    elif nz(nt.get("content")): comment = comment_body(content[nt["content"]], nt.get("part"))
    else: comment = None
    nt_parent = resolve_parent(nt.get("parent")) if nt.get("parent") else PARENT
    nt_track = TRACK if not nt.get("parent") else (TRACK_MAP.get(nt_parent) or TRACK)
    labels = (nt.get("labels") or []) + FIXED_LABELS + [x for x in (nt_track, MTG_LABEL) if x] + ref_labels(nt["summary"])
    fields = {"summary": nt["summary"], "description": desc, "labels": sorted(set(labels))}
    if nt.get("priority"): fields["priority"] = {"name": nt["priority"]}
    if nt.get("duedate"): fields["duedate"] = nt["duedate"]
    if nt.get("assignee"): fields["assignee"] = nt["assignee"]
    entry = {"placeholder": ph, "kind": kind, "origin": o, "issueTypeName": nt.get("issue_type") or ISSUE_TYPE, "parent": nt_parent, "fields": fields,
             "transition": nt.get("transition"), "comment": comment, "notes": list(nt.get("notes", []))}
    if kind == "recreate" and o:
        entry["origin_updates"] = {"comment": continuation_comment(ph, nt), "description_append": f"* → moved to {ph}",
                                   "transition_expected": f"{RESOLVED_ID} (Resolved)"}
        tr_o = (props["tickets"].get(o) or {}).get("transition") or {}
        if str(tr_o.get("id")) != RESOLVED_ID: entry["notes"] = entry["notes"] + [f"⚠ 作り直し元 {o} に Resolved({RESOLVED_ID}) 遷移の提案が無い"]
        if o in payload["tickets"] and payload["tickets"][o].get("description"):
            payload["tickets"][o]["description"] = payload["tickets"][o]["description"].rstrip("\n") + f"\n\n* → moved to {ph}\n"
        elif o in payload["tickets"]:
            payload["tickets"][o]["notes"] = payload["tickets"][o].get("notes", []) + [f"Description 編集スキップのため「→ moved to {ph}」行は手動追記"]
        if o in payload["tickets"]: payload["tickets"][o]["comment2"] = entry["origin_updates"]["comment"]
    new_out.append(entry)
    md.append(f"### {ph} `{nt['summary']}` — {kind}" + (f"（origin {o}）" if o else ""))
    md.append(f"- fields: parent={entry['parent']} / priority={nt.get('priority')} / due={nt.get('duedate')} / labels={','.join(fields['labels'])} / assignee={nt.get('assignee')}" + (f" / 初期遷移 {nt['transition'].get('to')}（ID {nt['transition'].get('id')}）" if nt.get("transition") else ""))
    if comment: md.append("\n#### コメント（" + ("Origin コメント" if kind == "split" else "フル議事録") + "）\n```\n" + comment + "```")
    md.append("\n#### Description\n```markdown\n" + desc.rstrip("\n") + "\n```")
    cands = [d for d in nt.get("dod", []) if not GATE.search(d)]
    if cands:
        md.append(f"\n#### ⚠ 候補（{TRK_NAME}未記載・未承認 → DoD に書かない）")
        for i, d in enumerate(cands, 1):
            md.append(f"- C{i}. {d}"); m4 = re.search(r"—\s*(l\.[\d,\-\s]+)", d)
            if m4 and TR: md += excerpt(m4.group(1), maxlines=8)
        CANDS.append((ph, cands))
    if nt.get("dod"):
        md.append("\n#### DoD 出典（文字起こし抜粋）")
        for d in nt["dod"]:
            md.append(f"- {d}"); m3 = re.search(r"—\s*(l\.[\d,\-\s]+)", d)
            if m3 and TR: md += excerpt(m3.group(1))
    if kind == "recreate" and o: md.append(f"\n#### 元チケット {o} への書き込み\n- 継続コメント 1 行（payload `tickets.{o}.comment2`）／DoD 末尾に `* → moved to {ph}`／Resolved({RESOLVED_ID}) 遷移")
    if entry["notes"]: md += ["\n#### 要確認"] + [f"- {n}" for n in entry["notes"]]
    md.append("")
for l in props.get("links") or []: add_link(l["from"], l.get("type", "Relates"), l["to"], l.get("why", "提案"))
# 既存チケット同士の同 No. Relates（改題で No. が付いたもの含む）— 自動候補
for k1, n1 in existing_nos.items():
    for k2, n2 in existing_nos.items():
        if k1 < k2 and set(n1) & set(n2): add_link(k1, "Relates", k2, f"同 #{sorted(set(n1)&set(n2))[0]}（既存同士・重複なら Jira 側で無視）", auto=True)
payload["new_tickets"], payload["links"] = new_out, links_out
if skipped_links: md.append("## 既存リンク（ダンプの issuelinks に既にあるため書き込まない）\n" + "\n".join(f"- {x}" for x in skipped_links) + "\n")
if links_out:
    md.append("## リンク案（issueLink" + ("。既存リンクは除外済み）" if EXIST else "。ダンプに issuelinks が無いため重複は書き込み時に確認）"))
    md.append("| from | type | to | 根拠 | 自動 |\n|---|---|---|---|---|")
    md += [f"| {l['from']} | {l['type']} | {l['to']} | {l['why']} | {'✓' if l['auto'] else ''} |" for l in links_out]
    md.append("")

if props.get("untouched"):
    md.append("## 変更しないチケット\n" + "\n".join(f"- {k}: {v}" for k, v in props["untouched"].items()) + "\n")
if props.get("no_ticket"):
    md.append("## チケットが無い No.（起票不要と判断）\n" + "\n".join(f"- {k}: {v}" for k, v in props["no_ticket"].items()) + "\n")
if CANDS:
    md.append(f"## {TRK_NAME}に無いアクション候補（要確認・一覧）\n" + "\n".join(f"- {k}: " + " / ".join(re.sub(r"\s+—.*$","",c) for c in cs) for k, cs in CANDS) + "\n")
md.append("## 実行ログ\n（承認後に追記）\n")

# ---------------- --validate: payload 検査 ----------------
viol = []
BG_STD, BG_MAX, BG_LINE = RULES.get("background_std"), RULES.get("background_max"), RULES.get("background_line_chars")
DOD_STD, DOD_MAX, DONE_EV = RULES.get("dod_std"), RULES.get("dod_max"), bool(RULES.get("done_evidence"))
SEC_STRICT = bool(RULES.get("sections_strict"))
vis = lambda l: re.sub(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", r"\1", l)   # 見た目の長さ（リンク URL を除く）
def section_check(d):
    """節名はプロファイル定義のみ・順序固定・Deliverable contents は箇条書きのみ。違反の説明文リストを返す"""
    out = []
    secs = [s_.strip() for s_ in re.findall(r"^## (.+)$", d, re.M)]
    names = [re.sub(r"\s*\(.*\)$", "", s_) for s_ in secs]
    bad = [s_ for s_ in names if s_ not in SEC_ORDER]
    if bad: out.append(f"独自節 {bad}（許可: {'/'.join(SEC_ORDER)}）")
    idx = [SEC_ORDER.index(s_) for s_ in names if s_ in SEC_ORDER]
    if idx != sorted(idx): out.append(f"節順 {names}（正: {'→'.join(SEC_ORDER)}）")
    if SEC["background"] in names and SEC["dod"] in names and names.index(SEC["dod"]) != names.index(SEC["background"]) + 1:
        out.append(f"{SEC['dod']} が {SEC['background']} の直後にない")
    if SEC.get("deliverable_contents"):
        m_dc = re.search(r"^## " + re.escape(SEC["deliverable_contents"]) + r"\n(.*?)(?=^## |\Z)", d, re.S | re.M)
        if m_dc and any(l.strip() and not re.match(r"^\s*([*-]|\d+\.) ", l) for l in m_dc.group(1).split("\n")): out.append(f"{SEC['deliverable_contents']} に箇条書き以外の行")
    return out
def bg_bullets(d):
    m = re.search(re.escape(H_BG) + r"\n(.*?)(?=\n## |\Z)", d, re.S)
    if not m: return []
    return [l for l in m.group(1).split("\n") if re.match(r"\* ", l) and not TRK_LINE_RE.match(l)]   # トップレベル箇条書きのみ数える（トラッカー行は上限に含めない）
def check_desc(k, d):
    for l in d.split("\n"):
        if CB_RE.match(l) and "](" in l: viol.append(f"{k}: チェック行内にリンク: {l.strip()[:60]}")
    if "<custom" in d: viol.append(f"{k}: <custom スマートリンク記法が残存")
    if "![](" in d: viol.append(f"{k}: 画像参照が残存（編集禁止対象）")
    if LANG_DESC == "en" and JA_RE.search(re.sub(r"\[[^\]]*\]\([^)]*\)", "", d)): viol.append(f"{k}: Description に日本語")
    if bare_keys("\n".join(l for l in d.split("\n") if not CB_RE.match(l))): viol.append(f"{k}: 素の課題キー（リンク化漏れ）")
def check_comment(k, c):
    if "en" in LANG_COMMENT and len(LANG_COMMENT) > 1:
        en = c.split("\n---\n")[LANG_COMMENT.index("en")] if c else ""
        if JA_RE.search(re.sub(r"\*\*Refs:\*\*.*", "", en)): viol.append(f"{k}: コメント EN 部に日本語（Refs 以外）")
def check_limits(k, d, strict, new_dod_lines, bg_over_reason, notes, touched_bg):
    """Background 行数・DoD 件数・[x] 証跡。strict=新規本文（desc_replace・新規起票）は NG、既存本文は注記"""
    bl = bg_bullets(d)
    if BG_MAX and strict:
        if len(bl) > BG_MAX: viol.append(f"{k}: Background が {len(bl)} 行（上限 {BG_MAX}。詳細はコメントへ）")
        elif BG_STD and len(bl) > BG_STD and not bg_over_reason: viol.append(f"{k}: Background が {len(bl)} 行（基本 {BG_STD} 行。超える理由を bg_over_reason に書く）")
        elif BG_STD and len(bl) > BG_STD: notes.append(f"Background {len(bl)} 行（基本 {BG_STD} 行超えの理由: {bg_over_reason}）")
        if BG_LINE:
            for l in bl:
                if len(vis(l)) > BG_LINE: viol.append(f"{k}: Background の 1 行が {len(vis(l))} 字（上限 {BG_LINE}・URL 除く）: {l[:50]}…")
    elif BG_MAX and touched_bg and len(bl) > BG_MAX:
        notes.append(f"⚠ Background 合計 {len(bl)} 行（上限 {BG_MAX}）。既存本文のため NG にしない。次回の整理対象")
    n_dod = len(re.findall(r"^\s*- \[[ x]\]", d, re.M))
    if DOD_MAX:
        if strict and n_dod > DOD_MAX: viol.append(f"{k}: DoD が {n_dod} 件（基本 {DOD_STD or DOD_MAX}・最大 {DOD_MAX}。分割を検討）")
        elif n_dod > DOD_MAX: notes.append(f"⚠ DoD 合計 {n_dod} 件（基本 {DOD_STD or DOD_MAX}・最大 {DOD_MAX}）。既存分を含むため NG にしない")
        elif DOD_STD and n_dod > DOD_STD and (new_dod_lines or strict): notes.append(f"DoD {n_dod} 件（基本 {DOD_STD} 件超。分割の余地）")
    if DONE_EV:
        for x in new_dod_lines:
            if re.search(r"^\s*(- )?\[x\]", x) and not re.search(r"\(done\b", x): viol.append(f"{k}: 完了行に証跡が無い `(done M/D: 根拠)`: {x.strip()[:60]}")
for k, t in payload["tickets"].items():
    d = t.get("description") or ""; pr = props["tickets"].get(k, {})
    check_desc(k, d); check_comment(k, t.get("comment") or "")
    if d:
        strict = bool(pr.get("desc_replace"))
        if SEC_STRICT:
            probs = section_check(d)
            if probs and strict: viol += [f"{k}: {x}" for x in probs]
            elif probs: t["notes"].append("⚠ 形式: " + " / ".join(probs) + "（既存本文のため NG にしない。次回整理）")
        new_lines = [x for x in (pr.get("dod") or [])] + ([l for l in d.split("\n") if CB_RE.match(l)] if strict else [])
        check_limits(k, d, strict, new_lines, pr.get("bg_over_reason"), t["notes"], bool(pr.get("background_en")))
known = set(issues) | {n["placeholder"] for n in payload.get("new_tickets", [])}
for n in payload.get("new_tickets", []):
    k, d = n["placeholder"], n["fields"]["description"]
    check_desc(k, d)
    if PREFIX_RE and not re.match(PREFIX_RE, n["fields"]["summary"]): viol.append(f"{k}: サマリ接頭辞が規約（{PREFIX_RE}）に合わない")
    if n["fields"].get("duedate") and n["fields"]["duedate"] <= a.date: viol.append(f"{k}: 期限 {n['fields']['duedate']} が会議日以前（次回定例日にする）")
    if n["kind"] == "recreate" and not n.get("origin"): viol.append(f"{k}: recreate に origin が無い")
    if not n.get("parent"): viol.append(f"{k}: parent（エピック）未指定")
    if SEC_STRICT: viol += [f"{k}: {x}" for x in section_check(d)]
    src = next((x for x in NEWS if x.get("placeholder") == k), {})
    check_limits(k, d, True, re.findall(r"^\s*- \[x\].*$", d, re.M), src.get("bg_over_reason"), n["notes"], True)
    check_comment(k, n.get("comment") or "")
for l in payload.get("links", []):
    for side in ("from", "to"):
        if l[side] not in known: viol.append(f"link {l['from']}→{l['to']}: 不明なキー {l[side]}")
    if l["type"] not in LINK_TYPES: viol.append(f"link {l['from']}→{l['to']}: 未知のリンク種別 {l['type']}")
if viol:
    md.append("## ⚠ validate NG\n" + "\n".join(f"- {v}" for v in viol) + "\n")
Path(a.out_md).write_text("\n".join(md), encoding="utf-8")
if a.out_preview:
    pv = [f"# 書き込みプレビュー — {a.date} {MTG_JA}", "", "これが Jira に書かれる最終文字列。承認後、Phase B（書き込み）はこのファイルと payload だけを見て書く（jira_api.py write --apply / MCP）。", ""]
    for k, t in payload["tickets"].items():
        if props["tickets"].get(k, {}).get("written"): continue
        f = issues.get(k, {}); pv.append(f"## {k} `{f.get('summary','')}`")
        fl = t.get("fields") or {}
        if fl: pv.append("**fields:** " + ", ".join(f"{kk}={json.dumps(v, ensure_ascii=False)}" for kk, v in fl.items()))
        if t.get("transition"): pv.append(f"**transition:** id={t['transition']['id']} → {t['transition']['to']}")
        if t.get("comment"): pv.append("\n**comment (markdown):**\n```\n" + t["comment"].rstrip() + "\n```")
        if t.get("description"): pv.append("\n**description (markdown):**\n```\n" + t["description"].rstrip() + "\n```")
        if t.get("notes"): pv.append("\n**notes:** " + " / ".join(t["notes"]))
        pv.append("")
    for n in payload.get("new_tickets", []):
        pv.append(f"## {n['placeholder']} 新規起票 `{n['fields']['summary']}`（parent {n['parent']}）"); pv.append("```\n" + json.dumps(n["fields"], ensure_ascii=False, indent=1) + "\n```")
        if n.get("comment"): pv.append("**Origin comment:**\n```\n" + n["comment"].rstrip() + "\n```")
        pv.append("")
    if payload.get("links"):
        pv.append("## links (issueLink)"); pv += [f"- {l['from']} —{l['type']}→ {l['to']}" + ("（自動: 同 No.）" if l.get("auto") else "") for l in payload["links"]]
    if viol: pv.insert(3, "**⚠ validate NG あり — この payload は書かない**\n")
    Path(a.out_preview).write_text("\n".join(pv) + "\n", encoding="utf-8")
Path(a.out_payload).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"tickets={len(payload['tickets'])} new={len(payload['new_tickets'])} links={len(payload['links'])} md={a.out_md} payload={a.out_payload}" + (f"  validate: NG {len(viol)}" if viol else "  validate: OK"))
if a.validate and viol: sys.exit(2)
