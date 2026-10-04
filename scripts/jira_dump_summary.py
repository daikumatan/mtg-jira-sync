#!/usr/bin/env python3
"""Jira ダンプ（jira_api.py fetch / MCP 検索結果）→ Phase A（分析）が読むための要約ビュー md（プロファイル駆動）。
ボイラープレートを捨て、1 チケット 10 行前後に圧縮する。節名・トラッカー行・TZ・配置規則はプロファイルから読む。

usage: jira_dump_summary.py --profile <profile.md> --dump .jira_dump_YYYYMMDD.json --out jira_dump_summary_YYYYMMDD.md [--full KEY-1,KEY-2] [--audit]
  --full   挙げたキーは Description とコメント本文も全文で出す（Phase A が追記対象を精読する用）
  --audit  先頭に形式監査（Background 行数超過・節順違い・独自節・空・DoD 件数・[x] 証跡なし・エピック配置）の一覧を付ける
exit: 0
"""
import argparse, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True)
ap.add_argument("--dump", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--full", default="", help="Description・コメント全文を出すキー（カンマ区切り）")
ap.add_argument("--audit", action="store_true")
a = ap.parse_args()

def load_profile(path):
    txt = Path(path).expanduser().read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m: sys.exit(f"profile に YAML frontmatter が無い: {path}")
    import yaml
    return yaml.safe_load(m.group(1)) or {}
P = load_profile(a.profile)
def pget(path, default=None):
    cur = P
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur
SEC = {"purpose": None, "background": "Background", "dod": "Definition of Done", "deliverable_contents": None, "nice_to_have": None, "materials": "Materials"} | (pget("description.sections", {}) or {})
SEC_ORDER = [SEC[k] for k in ("purpose", "background", "dod", "deliverable_contents", "nice_to_have", "materials") if SEC.get(k)]
RULES = pget("description.rules", {}) or {}
BG_STD, BG_MAX, DOD_MAX = RULES.get("background_std"), RULES.get("background_max"), RULES.get("dod_max")
TRK_PREFIX = "* " + pget("tracker.link_label", "Tracker")
TZ = timezone(timedelta(hours=float(pget("meeting.tz_offset_hours", 9))))
TZN = pget("meeting.time", "").split()[-1] if pget("meeting.time") else ""
PLACEMENT = pget("jira.placement", []) or []
EPICS = {v for v in (pget("jira.parents", {}) or {}).values() if v} | ({pget("jira.parent")} if pget("jira.parent") else set())
H_BG, H_DOD = SEC["background"], SEC["dod"]

def local(iso):
    try:
        dt = datetime.strptime(re.sub(r"(\.\d+)?([+-]\d{2}):?(\d{2})$", r"\2\3", iso), "%Y-%m-%dT%H:%M:%S%z")
        return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M") + (f" {TZN}" if TZN else "")
    except Exception:
        return iso

dump = json.load(open(a.dump, encoding="utf-8"))
nodes = dump["issues"]["nodes"]
full = {k.strip() for k in a.full.split(",") if k.strip()}
def bg_count(d):
    bg = re.search(r"## " + re.escape(H_BG) + r"\n(.*?)(?=\n## |\Z)", d, re.S)
    return len([l for l in (bg.group(1) if bg else "").split("\n") if re.match(r"\* ", l) and not l.startswith(TRK_PREFIX)])
def fmt_check(d):
    """形式の逸脱を短く返す（無ければ空）"""
    if not d.strip(): return ["空"]
    secs = [re.sub(r"\s*\(.*\)$", "", s_.strip()) for s_ in re.findall(r"^## (.+)$", d, re.M)]
    bad = [s_ for s_ in secs if s_ not in SEC_ORDER]
    idx = [SEC_ORDER.index(s_) for s_ in secs if s_ in SEC_ORDER]
    out = []
    nbg = bg_count(d)
    ndod = len(re.findall(r"^\s*- \[[ x]\]", d, re.M)); nx_noev = len([x for x in re.findall(r"^\s*- \[x\].*$", d, re.M) if "(done" not in x])
    if DOD_MAX and ndod > DOD_MAX: out.append(f"DoD {ndod}件")
    if RULES.get("done_evidence") and nx_noev: out.append(f"[x]証跡なし{nx_noev}")
    if H_BG not in secs: out.append(f"{H_BG}無し")
    elif BG_MAX and nbg > BG_MAX: out.append(f"BG {nbg}行(NG)")
    elif BG_STD and nbg > BG_STD: out.append(f"BG {nbg}行")
    if RULES.get("sections_strict"):
        if bad: out.append("独自節:" + "/".join(bad))
        if idx != sorted(idx): out.append("節順")
        if H_BG in secs and H_DOD in secs and secs.index(H_DOD) != secs.index(H_BG) + 1: out.append("DoDがBG直後でない")
    return out
PARENT_OF = {n["key"]: (n["fields"].get("parent") or {}).get("key") for n in nodes}
def place_check(f):
    """エピック配置の規則（プロファイル jira.placement）。summary→parent / under+forbid_summary / under+labels_any+require_link_under"""
    out = []; par = (f.get("parent") or {}).get("key"); sm = f.get("summary", ""); labels = set(f.get("labels") or []); key = f.get("key")
    if (f.get("issuetype") or {}).get("name") == "Epic": return out
    if EPICS and par not in EPICS: out.append(f"親が対象エピック外({par})")
    for r in PLACEMENT:
        if key in (r.get("except") or []): continue
        if r.get("summary") and r.get("parent"):
            if re.match(r["summary"], sm) and par != r["parent"]: out.append(r.get("msg") or f"{r['summary']} なのに {r['parent']} 配下でない")
        elif r.get("under") and r.get("forbid_summary"):
            if par == r["under"] and re.match(r["forbid_summary"], sm): out.append(r.get("msg") or f"{r['under']} 配下に {r['forbid_summary']}")
        elif r.get("under") and r.get("require_link_under"):
            if par == r["under"] and (not r.get("labels_any") or labels & set(r["labels_any"])):
                linked = {(l.get("outwardIssue") or l.get("inwardIssue") or {}).get("key") for l in f.get("issuelinks") or []}
                if not any(PARENT_OF.get(k_) == r["require_link_under"] for k_ in linked if k_): out.append(r.get("msg") or f"{r['under']} 配下に {r['require_link_under']} 側リンク無し")
    return out
out = [f"# Jira ダンプ要約ビュー — {Path(a.dump).name}（{len(nodes)} 件）", "",
       "Phase A はこのファイルとダンプ JSON だけを読む（Jira API/MCP は呼ばない）。全文が要るキーは `--full` で出し直す。", ""]
if a.audit:
    rows = [(n["key"], (n["fields"].get("status") or {}).get("name"), fmt_check(n["fields"].get("description") or "") + place_check(n["fields"] | {"key": n["key"]})) for n in nodes if (n["fields"].get("issuetype") or {}).get("name") != "Epic"]
    rows = [r for r in rows if r[2]]
    out += ["## 形式監査（次にそのチケットへ追記するときに寄せる）", "", "| key | status | 逸脱 |", "|---|---|---|"] + [f"| {k} | {st} | {'; '.join(x)} |" for k, st, x in sorted(rows, key=lambda r: (r[1] == "Resolved", r[0]))] + [""]
for n in sorted(nodes, key=lambda x: int(x["key"].split("-")[1])):
    f = n["fields"]; k = n["key"]
    st = (f.get("status") or {}).get("name"); pri = (f.get("priority") or {}).get("name")
    asg = (f.get("assignee") or {}).get("displayName") or "-"
    out.append(f"## {k} `{f.get('summary','')}`")
    out.append(f"- status={st} / priority={pri} / due={f.get('duedate') or '-'} / assignee={asg} / updated={local(f.get('updated',''))}")
    out.append(f"- labels: {', '.join(f.get('labels') or []) or '-'}")
    links = []
    for l in f.get("issuelinks") or []:
        t = l["type"]["name"]
        if "outwardIssue" in l: links.append(f"{t}→{l['outwardIssue']['key']}")
        if "inwardIssue" in l: links.append(f"{t}←{l['inwardIssue']['key']}")
    out.append(f"- links: {', '.join(links) or '-'}")
    d = f.get("description") or ""
    dod = [l.strip() for l in d.split("\n") if re.match(r"\s*- \[[ x]\]", l)]
    fc = fmt_check(d) + place_check(f | {"key": k})
    out.append(f"- parent: {(f.get('parent') or {}).get('key') or '-'}")
    out.append(f"- description: {len(d)} chars / {H_BG} {bg_count(d)} 行 / DoD {len(dod)} 件（[x] {sum(1 for x in dod if '[x]' in x)}）" + (" / 画像あり⚠" if "![](" in d else "") + (" / smartlink⚠" if "<custom" in d else "") + (f" / 形式⚠ {'; '.join(fc)}" if fc else ""))
    for x in dod[:12]: out.append(f"    {x[:140]}")
    cs = (f.get("comment") or {}).get("comments") or []
    if cs:
        out.append(f"- comments: {len(cs)} 件 — " + "; ".join(f"{local(c['created'])[:10]} {(c['author'].get('displayName') or '?').split()[0]} \"{(c.get('body') or '').split(chr(10))[0][:50]}\"" for c in cs[-3:]))
    if k in full:
        out.append("\n<details><summary>Description 全文</summary>\n\n```markdown\n" + d.rstrip() + "\n```\n</details>")
        for c in cs:
            out.append(f"\n<details><summary>Comment {c['id']} — {local(c['created'])} {c['author'].get('displayName')}</summary>\n\n```markdown\n" + (c.get("body") or "").rstrip() + "\n```\n</details>")
    out.append("")
Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{len(nodes)} tickets → {a.out} ({sum(len(x) for x in out)} chars; full={','.join(sorted(full)) or '-'})")
