#!/usr/bin/env python3
"""Jira Cloud REST (v3) 直叩き（プロファイル駆動）。MCP コネクタの代替。
Phase 0（取得）と Phase B（書き込み）をモデルを介さず Bash から実行し、Jira の応答をモデルのコンテキストに入れないためのもの。

認証: 環境変数 JIRA_EMAIL / JIRA_API_TOKEN、無ければ ~/.config/jira.env（`JIRA_EMAIL=…` `JIRA_API_TOKEN=…` の行。生トークン 1 行も可）。
      メールはプロファイル `jira.email` でも指定できる（優先順: 環境変数 > jira.env > プロファイル）。
サイト・プロジェクト・既定 JQL・課題タイプ・TZ はプロファイル frontmatter（jira.site / jira.project_key / jira.jql / jira.issue_type / meeting.tz_offset_hours）。

usage:
  jira_api.py --profile <profile.md> myself
  jira_api.py --profile <profile.md> fetch  [--jql JQL] [--keys K1,K2] --out dump.json [--summary sum.md --full K1,K2]
  jira_api.py --profile <profile.md> write  --payload payload.json --dump dump.json [--only K1,K2] [--apply] [--force] --log log.md [--report report.md]
  jira_api.py --profile <profile.md> transitions --key KEY-nn          遷移 ID 一覧（プロファイル jira.transitions を埋めるとき）
  jira_api.py --profile <profile.md> adf --md file.md [--back]         markdown→ADF（--back で ADF→markdown の往復確認）
exit: 0 正常 / 1 HTTP エラー・入力不備
"""
import argparse, json, os, re, sys, uuid, difflib
from pathlib import Path
from datetime import datetime, timezone, timedelta
import requests, urllib3
urllib3.disable_warnings()

ap = argparse.ArgumentParser()
ap.add_argument("--profile", required=True, help="案件プロファイル md（YAML frontmatter を読む）")
sp = ap.add_subparsers(dest="cmd", required=True)
sp.add_parser("myself")
p = sp.add_parser("fetch"); p.add_argument("--jql", default="", help="既定はプロファイル jira.jql"); p.add_argument("--keys", default=""); p.add_argument("--out", required=True); p.add_argument("--summary", default=""); p.add_argument("--full", default="")
p = sp.add_parser("write"); p.add_argument("--payload", required=True); p.add_argument("--dump", required=True); p.add_argument("--only", default=""); p.add_argument("--apply", action="store_true"); p.add_argument("--force", action="store_true"); p.add_argument("--log", required=True); p.add_argument("--report", default="", help="--apply 時、この md（jira_sync_YYYYMMDD.md）の末尾に実行ログを追記")
p = sp.add_parser("transitions"); p.add_argument("--key", required=True)
p = sp.add_parser("adf"); p.add_argument("--md", required=True); p.add_argument("--back", action="store_true")
a = ap.parse_args()

# ---------------- profile ----------------
def load_profile(path):
    txt = Path(path).expanduser().read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m: sys.exit(f"profile に YAML frontmatter が無い: {path}")
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML が無い（pip install pyyaml）")
    return yaml.safe_load(m.group(1)) or {}
P = load_profile(a.profile)
def pget(path, default=None):
    cur = P
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur
SITE = (pget("jira.site") or "").rstrip("/")
PK = pget("jira.project_key")
ISSUE_TYPE = pget("jira.issue_type", "Task")
DEFAULT_JQL = pget("jira.jql", "")
TZ = timezone(timedelta(hours=float(pget("meeting.tz_offset_hours", 9))))
if not (SITE and PK): sys.exit("profile の jira.site / jira.project_key は必須")
API = f"{SITE}/rest/api/3"
FIELDS = ["summary","status","labels","assignee","duedate","priority","issuetype","updated","description","comment","issuelinks","parent"]

def auth():
    tok, mail = os.environ.get("JIRA_API_TOKEN"), os.environ.get("JIRA_EMAIL")
    p = Path.home()/".config"/"jira.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line and line.split("=",1)[0].strip().isupper():
                k, v = line.split("=",1); k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "JIRA_API_TOKEN" and not tok: tok = v
                if k == "JIRA_EMAIL" and not mail: mail = v
            elif not tok:
                tok = line   # 生トークン 1 行
    mail = mail or pget("jira.email")
    if not tok: sys.exit("JIRA_API_TOKEN が見つからない（環境変数か ~/.config/jira.env）")
    if not mail: sys.exit("JIRA_EMAIL が見つからない（環境変数・~/.config/jira.env・プロファイル jira.email のいずれか）")
    return (mail, tok)

S = requests.Session(); S.auth = auth(); S.headers.update({"Accept":"application/json","Content-Type":"application/json"})
def req(method, path, **kw):
    r = S.request(method, path if path.startswith("http") else API + path, timeout=60, **kw)
    if r.status_code >= 400:
        sys.exit(f"HTTP {r.status_code} {method} {path}: {r.text[:500]}")
    return r.json() if r.text.strip() else {}

# ---------------- ADF -> markdown ----------------
def _inline(nodes):
    out = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            s = n.get("text",""); href = None
            for m in n.get("marks", []):
                mt = m.get("type")
                if mt == "strong": s = f"**{s}**"
                elif mt == "em": s = f"*{s}*"
                elif mt == "code": s = f"`{s}`"
                elif mt == "strike": s = f"~~{s}~~"
                elif mt == "link": href = m.get("attrs",{}).get("href")
            out.append(f"[{s}]({href})" if href else s)
        elif t == "hardBreak": out.append("\n")
        elif t in ("inlineCard","blockCard","embedCard"):
            u = n.get("attrs",{}).get("url",""); out.append(f"[{u}]({u})")
        elif t == "mention": out.append("@" + n.get("attrs",{}).get("text","").lstrip("@"))
        elif t == "emoji": out.append(n.get("attrs",{}).get("text",""))
        elif t == "status": out.append(n.get("attrs",{}).get("text",""))
        elif t == "inlineExtension": out.append("")
        else: out.append(_inline(n.get("content")))
    return "".join(out)

def adf_to_md(doc, depth=0):
    if not doc: return ""
    if isinstance(doc, str): return doc
    out = []
    ind = "    " * depth
    for n in doc.get("content", []) or []:
        t = n.get("type")
        if t == "paragraph": out.append(_inline(n.get("content")) + "\n")
        elif t == "heading": out.append("#" * n.get("attrs",{}).get("level",2) + " " + _inline(n.get("content")) + "\n")
        elif t in ("bulletList","orderedList"):
            for i, li in enumerate(n.get("content", []), 1):
                marker = "* " if t == "bulletList" else f"{i}. "
                first, rest = True, []
                for c in li.get("content", []):
                    if c.get("type") == "paragraph" and first:
                        out.append(ind + marker + _inline(c.get("content")) + "\n"); first = False
                    elif c.get("type") in ("bulletList","orderedList","taskList"):
                        out.append(adf_to_md({"content":[c]}, depth+1))
                    else:
                        txt = adf_to_md({"content":[c]}, depth+1)
                        if first: out.append(ind + marker + txt.strip() + "\n"); first = False
                        else: out.append(txt)
            out.append("\n") if depth == 0 else None
        elif t == "taskList":
            for ti in n.get("content", []):
                st = "x" if ti.get("attrs",{}).get("state") == "DONE" else " "
                out.append(ind + f"- [{st}] " + _inline(ti.get("content")) + "\n")
            out.append("\n") if depth == 0 else None
        elif t == "rule": out.append("---\n")
        elif t == "codeBlock": out.append("```\n" + _inline(n.get("content")) + "\n```\n")
        elif t == "blockquote": out.append("> " + adf_to_md(n).replace("\n", "\n> ").rstrip("> ") + "\n")
        elif t in ("mediaSingle","mediaGroup","media"): out.append("![](media)\n")
        elif t == "table": out.append("(table omitted)\n")
        else: out.append(adf_to_md(n, depth))
        if t in ("paragraph","heading","rule","codeBlock") and depth == 0: out.append("\n")
    s = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", s)

# ---------------- markdown -> ADF ----------------
INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]*\]\((https?://[^)\s]+)\)|https?://[^\s)\]]+)")
def inline_nodes(text):
    nodes, pos = [], 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos: nodes.append({"type":"text","text":text[pos:m.start()]})
        tok = m.group(0)
        if tok.startswith("**"): nodes.append({"type":"text","text":tok[2:-2],"marks":[{"type":"strong"}]})
        elif tok.startswith("`"): nodes.append({"type":"text","text":tok[1:-1],"marks":[{"type":"code"}]})
        elif tok.startswith("["):
            mm = re.match(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", tok); label, url = mm.group(1) or mm.group(2), mm.group(2)
            nodes.append({"type":"text","text":label,"marks":[{"type":"link","attrs":{"href":url}}]})
        else: nodes.append({"type":"text","text":tok,"marks":[{"type":"link","attrs":{"href":tok}}]})
        pos = m.end()
    if pos < len(text): nodes.append({"type":"text","text":text[pos:]})
    return [n for n in nodes if n.get("text") != ""] or [{"type":"text","text":" "}]

def para(lines):
    content = []
    for i, l in enumerate(lines):
        if i: content.append({"type":"hardBreak"})
        content += inline_nodes(l)
    return {"type":"paragraph","content":content}

def md_to_adf(md):
    lines = md.replace("\r\n","\n").split("\n")
    doc = []; i = 0
    def parse_list(start, level):
        """level 階層の箇条書き（* / - / 1.）を読み、(node, next_i) を返す"""
        items = []; kind = None; j = start
        while j < len(lines):
            l = lines[j]
            m = re.match(r"^( *)([*-]|\d+\.) (.*)$", l)
            tm = re.match(r"^( *)- \[([ x])\] (.*)$", l)
            if tm and len(tm.group(1)) // 4 == level: break   # タスクは別ブロック
            if not m:
                if l.strip() == "": j += 1; continue   # リスト内の空行は無視（次がリストなら継続）
                break
            lv = len(m.group(1)) // 4
            if lv < level: break
            if lv > level:
                child, j = parse_list(j, lv)
                if items: items[-1]["content"].append(child)
                continue
            k = "orderedList" if m.group(2)[0].isdigit() else "bulletList"
            kind = kind or k
            if k != kind: break
            items.append({"type":"listItem","content":[para([m.group(3)])]}); j += 1
        # 末尾の空行は消費しない
        while j > start and j <= len(lines) and j-1 < len(lines) and lines[j-1].strip() == "": j -= 1
        return {"type":kind or "bulletList","content":items}, j
    while i < len(lines):
        l = lines[i]
        if l.strip() == "": i += 1; continue
        hm = re.match(r"^(#{1,6}) (.*)$", l)
        if hm: doc.append({"type":"heading","attrs":{"level":len(hm.group(1))},"content":inline_nodes(hm.group(2))}); i += 1; continue
        if re.match(r"^---+\s*$", l): doc.append({"type":"rule"}); i += 1; continue
        if re.match(r"^- \[[ x]\] ", l):
            items = []
            while i < len(lines) and re.match(r"^- \[[ x]\] ", lines[i]):
                tm = re.match(r"^- \[([ x])\] (.*)$", lines[i])
                items.append({"type":"taskItem","attrs":{"localId":str(uuid.uuid4()),"state":"DONE" if tm.group(1)=="x" else "TODO"},"content":inline_nodes(tm.group(2))}); i += 1
            doc.append({"type":"taskList","attrs":{"localId":str(uuid.uuid4())},"content":items}); continue
        if re.match(r"^([*-]|\d+\.) ", l):
            node, i = parse_list(i, 0); doc.append(node); continue
        if l.startswith("```"):
            j = i + 1; buf = []
            while j < len(lines) and not lines[j].startswith("```"): buf.append(lines[j]); j += 1
            doc.append({"type":"codeBlock","content":[{"type":"text","text":"\n".join(buf)}]}); i = j + 1; continue
        buf = []
        while i < len(lines) and lines[i].strip() != "" and not re.match(r"^(#{1,6} |---+\s*$|- \[[ x]\] |([*-]|\d+\.) |```)", lines[i]):
            buf.append(lines[i]); i += 1
        doc.append(para(buf))
    return {"type":"doc","version":1,"content":doc}

def norm(md):
    s = re.sub(r"[ \t]+\n", "\n", md.replace("\r\n","\n")); s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()

# ---------------- commands ----------------
def cmd_myself(a):
    me = req("GET", "/myself"); print(me.get("displayName"), me.get("emailAddress"))

def cmd_fetch(a):
    jql = a.jql or DEFAULT_JQL
    if a.keys: jql = f"key in ({a.keys})" + (f" OR ({jql})" if jql else "")
    if not jql: sys.exit("--jql かプロファイル jira.jql が必要")
    nodes, token = [], None
    while True:
        body = {"jql": jql, "fields": FIELDS, "maxResults": 100, "expand": "" }
        if token: body["nextPageToken"] = token
        r = req("POST", "/search/jql", data=json.dumps(body))
        for iss in r.get("issues", []):
            f = iss["fields"]
            f["description"] = adf_to_md(f.get("description")) if f.get("description") else None
            c = f.get("comment") or {}
            f["comment"] = {"total": c.get("total", len(c.get("comments",[]))), "comments": [
                {"id": x["id"], "body": adf_to_md(x.get("body")), "created": x["created"], "updated": x.get("updated"),
                 "author": {"accountId": x["author"].get("accountId"), "displayName": x["author"].get("displayName")}} for x in c.get("comments", [])]}
            for k in ("assignee","priority","status","issuetype"):
                if f.get(k): f[k] = {kk: f[k].get(kk) for kk in ("name","id","displayName","accountId","emailAddress") if f[k].get(kk) is not None}
            nodes.append({"id": iss["id"], "key": iss["key"], "fields": f})
        token = r.get("nextPageToken")
        if not token or r.get("isLast"): break
    nodes.sort(key=lambda n: int(n["key"].split("-")[1]))
    Path(a.out).write_text(json.dumps({"issues":{"nodes":nodes}, "source":"jira_api.py fetch", "jql": jql, "fetched_at": datetime.now(TZ).isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fetched {len(nodes)} issues → {a.out}")
    if a.summary:
        import subprocess
        cmd = [sys.executable, str(Path(__file__).with_name("jira_dump_summary.py")), "--profile", a.profile, "--dump", a.out, "--out", a.summary] + (["--full", a.full] if a.full else [])
        print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())

def cmd_transitions(a):
    r = req("GET", f"/issue/{a.key}/transitions")
    for t in r.get("transitions", []): print(f"{t['id']:>4}  {t['name']}  → {t.get('to',{}).get('name')}")

def cmd_adf(a):
    md = Path(a.md).read_text(encoding="utf-8"); adf = md_to_adf(md)
    if a.back:
        back = adf_to_md(adf); ok = norm(back) == norm(md)
        print("roundtrip:", "OK" if ok else "DIFF")
        if not ok:
            for l in difflib.unified_diff(norm(md).split("\n"), norm(back).split("\n"), "md", "adf→md", lineterm="", n=1): print(l)
    else: print(json.dumps(adf, ensure_ascii=False, indent=1))

def cmd_write(a):
    pay = json.load(open(a.payload, encoding="utf-8")); dump = json.load(open(a.dump, encoding="utf-8"))
    before = {n["key"]: n["fields"] for n in dump["issues"]["nodes"]}
    only = set(k.strip() for k in a.only.split(",") if k.strip()) if a.only else None
    log = [f"# jira_api.py write — {datetime.now(TZ).strftime('%Y-%m-%d %H:%M %z')} — {'APPLY' if a.apply else 'DRY RUN'}", ""]
    def L(s): log.append(s); print(s)
    for key, t in pay["tickets"].items():
        if only and key not in only: continue
        if not t or (not t.get("comment") and not t.get("description") and not t.get("fields") and not t.get("transition")): continue
        L(f"## {key}")
        cur = req("GET", f"/issue/{key}?fields=updated,status,description")
        if key in before and before[key].get("updated") != cur["fields"]["updated"]:
            L(f"- ⚠ 鮮度: dump {before[key].get('updated')} ≠ now {cur['fields']['updated']}" + ("（--force で続行）" if a.force else " → スキップ"))
            if not a.force: continue
        if t.get("comment"):
            if a.apply:
                r = req("POST", f"/issue/{key}/comment", data=json.dumps({"body": md_to_adf(t["comment"])})); L(f"- comment: id={r.get('id')}")
            else: L(f"- comment: {len(t['comment'])} chars（dry）")
        if t.get("comment2"):   # 作り直し元への継続コメント（placeholder は new_tickets 作成後に置換するため後段で書く）
            pass
        fields = dict(t.get("fields") or {})
        if t.get("description"): fields["description"] = md_to_adf(t["description"])
        if fields:
            if a.apply:
                req("PUT", f"/issue/{key}", data=json.dumps({"fields": fields})); L(f"- fields: {sorted(fields)}")
                if t.get("description"):
                    got = req("GET", f"/issue/{key}?fields=description")["fields"].get("description")
                    back = adf_to_md(got); ok = norm(back) == norm(t["description"])
                    L(f"- description verify: {'OK' if ok else '⚠ DIFF'}")
                    if not ok:
                        for l in list(difflib.unified_diff(norm(t['description']).split("\n"), norm(back).split("\n"), "payload", "jira", lineterm="", n=0))[:20]: L("    " + l)
            else: L(f"- fields: {sorted(fields)}（dry）")
        if t.get("transition"):
            if a.apply: req("POST", f"/issue/{key}/transitions", data=json.dumps({"transition":{"id": str(t["transition"]["id"])}})); L(f"- transition → {t['transition'].get('to')}")
            else: L(f"- transition → {t['transition'].get('to')}（dry）")
    created = {}
    for n in pay.get("new_tickets", []):
        ph = n["placeholder"]; f = dict(n["fields"]); f["description"] = md_to_adf(f["description"]) if f.get("description") else None
        f.setdefault("project", {"key": PK}); f.setdefault("issuetype", {"name": n.get("issueTypeName") or ISSUE_TYPE})
        if n.get("parent") and "parent" not in f: f["parent"] = {"key": n["parent"]}   # エピック配下に起票
        if a.apply:
            r = req("POST", "/issue", data=json.dumps({"fields": f})); created[ph] = r["key"]; L(f"## {ph} → 新規 {r['key']}")
            if n.get("comment"): req("POST", f"/issue/{r['key']}/comment", data=json.dumps({"body": md_to_adf(n["comment"].replace(ph, r["key"]))}))
            if n.get("transition"): req("POST", f"/issue/{r['key']}/transitions", data=json.dumps({"transition":{"id": str(n["transition"]["id"])}}))
        else: L(f"## {ph} 新規起票 `{f.get('summary')}`（parent {n.get('parent')}・dry）")
    for key, t in pay["tickets"].items():   # 作り直し元の継続コメント（placeholder を実キーに置換）
        if not t or not t.get("comment2") or (only and key not in only): continue
        body = t["comment2"]
        for ph, k in created.items(): body = body.replace(ph, k)
        if a.apply: r = req("POST", f"/issue/{key}/comment", data=json.dumps({"body": md_to_adf(body)})); L(f"- {key} continuation comment: id={r.get('id')}")
        else: L(f"- {key} continuation comment（dry）")
    for l in pay.get("links", []):
        fr, to = created.get(l["from"], l["from"]), created.get(l["to"], l["to"])
        if only and fr not in only and to not in only: continue
        if a.apply:
            req("POST", "/issueLink", data=json.dumps({"type":{"name": l["type"]}, "inwardIssue":{"key": fr}, "outwardIssue":{"key": to}})); L(f"- link {fr} —{l['type']}→ {to}")
        else: L(f"- link {fr} —{l['type']}→ {to}（dry）")
    Path(a.log).write_text("\n".join(log) + "\n", encoding="utf-8"); print(f"log → {a.log}")
    if a.apply and a.report:
        rp = Path(a.report); body = rp.read_text(encoding="utf-8") if rp.exists() else ""
        body = body.replace("## 実行ログ\n（承認後に追記）\n", "## 実行ログ\n") if "（承認後に追記）" in body else body
        rp.write_text(body.rstrip("\n") + "\n\n### jira_api.py write --apply (" + log[0].split(" — ")[1] + ")\n" + "\n".join(log[2:]) + "\n", encoding="utf-8"); print(f"report ← {a.report}")

{"myself": cmd_myself, "fetch": cmd_fetch, "write": cmd_write, "transitions": cmd_transitions, "adf": cmd_adf}[a.cmd](a)
