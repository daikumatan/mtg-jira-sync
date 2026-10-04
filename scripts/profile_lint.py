#!/usr/bin/env python3
"""
プロファイル lint: frontmatter の必須キー・型・整合性を検査する。新案件のプロファイルを作ったら、ドライランの前に通す。
usage: python profile_lint.py <profile.md> [<profile.md> ...] [--public]
  --public : 公開リポジトリに置く見本用。実在しそうな値（実テナント名・UUID 形式の cloud_id 等）を警告する
exit: 0 エラー無し（警告は可）/ 2 エラー有り
"""
import argparse, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--public", action="store_true")
a = ap.parse_args()
try:
    import yaml
except ImportError:
    sys.exit("PyYAML が無い（pip install pyyaml）")

def get(d, path, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur

total_err = 0
for f in a.files:
    p = Path(f).expanduser(); err, warn = [], []
    if p.name.lower() == "readme.md": continue
    txt = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
    if not m: print(f"✗ {p.name}: YAML frontmatter が無い"); total_err += 1; continue
    try: d = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e: print(f"✗ {p.name}: YAML 構文エラー: {e}"); total_err += 1; continue
    body = m.group(2)
    # 基本
    if get(d, "profile") != p.stem: err.append(f"profile '{get(d,'profile')}' がファイル名 '{p.stem}' と一致しない")
    st = get(d, "status")
    if st not in ("draft", "verified"): err.append(f"status は draft|verified（現在 {st!r}）")
    for k in ("jira.site", "jira.project_key", "jira.parent", "jira.issue_type"):
        if not get(d, k): err.append(f"{k} が空")
    site = get(d, "jira.site", "")
    if site and not re.match(r"^https://[^/]+$", site): err.append(f"jira.site は https://<host> の形（現在 {site!r}）")
    pk = get(d, "jira.project_key", "")
    if pk and not re.match(r"^[A-Z][A-Z0-9_]+$", pk): err.append(f"jira.project_key の形式が不正: {pk!r}")
    parent = get(d, "jira.parent", "")
    if parent and pk and not str(parent).startswith(pk + "-"): err.append(f"jira.parent {parent!r} が project_key {pk} と食い違う")
    if not get(d, "jira.jql"): warn.append("jira.jql が空（手順 1 で必要）")
    tr = get(d, "jira.transitions") or {}
    rid = str(get(d, "jira.resolved_transition_id") or "")
    if not tr: (err if st == "verified" else warn).append("jira.transitions が空（初回に getTransitionsForJiraIssue で埋める）")
    if not rid: (err if st == "verified" else warn).append("jira.resolved_transition_id が空")
    elif tr and rid not in {str(v) for v in tr.values()}: err.append(f"resolved_transition_id {rid} が transitions の値に無い")
    lt = get(d, "jira.link_types")
    if not isinstance(lt, list) or "Relates" not in lt: err.append("jira.link_types は Relates を含むリスト")
    pars = get(d, "jira.parents") or {}
    if not isinstance(pars, dict): err.append("jira.parents は {別名: KEY-nn} の辞書")
    else:
        for al, v in pars.items():
            if pk and not str(v).startswith(pk + "-"): err.append(f"jira.parents.{al} {v!r} が project_key {pk} と食い違う")
    for i, r in enumerate(get(d, "jira.placement") or []):
        if not isinstance(r, dict): err.append(f"jira.placement[{i}] は辞書"); continue
        kinds = [bool(r.get("summary") and r.get("parent")), bool(r.get("under") and r.get("forbid_summary")), bool(r.get("under") and r.get("require_link_under"))]
        if sum(kinds) != 1: err.append(f"jira.placement[{i}] は summary+parent / under+forbid_summary / under+require_link_under のいずれか 1 種")
        for kk in ("summary", "forbid_summary"):
            if r.get(kk):
                try: re.compile(r[kk])
                except re.error as e: err.append(f"jira.placement[{i}].{kk} が正規表現として不正: {e}")
    # summary / labels
    rr = get(d, "summary.ref_regex"); rl = get(d, "labels.ref_label"); pr = get(d, "summary.prefix_regex")
    for name, rx in (("summary.ref_regex", rr), ("summary.prefix_regex", pr)):
        if rx:
            try: re.compile(rx)
            except re.error as e: err.append(f"{name} が正規表現として不正: {e}")
    if rr and re.compile(rr).groups < 1: err.append("summary.ref_regex にキャプチャ群 (…) が無い")
    if rl and not rr: err.append("labels.ref_label があるのに summary.ref_regex が無い")
    if rl:
        try: rl.format(n=1)
        except (KeyError, ValueError, IndexError): err.append(f"labels.ref_label {rl!r} は {{n}} を含む format 文字列")
    if not isinstance(get(d, "labels.fixed"), list): err.append("labels.fixed はリスト（空なら []）")
    for kk in ("labels.track", "labels.meeting_type"):
        v = get(d, kk)
        if v is not None and not isinstance(v, dict): err.append(f"{kk} は辞書")
    mt = get(d, "labels.meeting_type") or {}
    if any(k not in ("weekly", "internal", "customer") for k in mt): err.append(f"labels.meeting_type のキーは weekly|internal|customer（現在 {list(mt)}）")
    tr_ = get(d, "labels.track") or {}
    if tr_ and pars and not set(tr_) <= (set(pars.values()) | {get(d, "jira.parent")}): warn.append(f"labels.track に jira.parents/parent に無いキーがある: {sorted(set(tr_) - set(pars.values()) - {get(d, 'jira.parent')})}")
    # parties
    ps = get(d, "parties") or []
    if not ps: err.append("parties が空（少なくとも自社 1 件）")
    codes = [str(x.get("code", "")) for x in ps]
    if len(set(codes)) != len(codes): err.append(f"parties.code が重複: {codes}")
    for x in ps:
        for k in ("code", "name_en", "name_ja", "role"):
            if not x.get(k): err.append(f"parties[{x.get('code','?')}].{k} が空")
        if x.get("code") and not re.match(r"^[a-z][a-z0-9]*$", str(x["code"])): err.append(f"parties.code {x['code']!r} は英小文字のみ（content JSON のキーになる）")
    if not any(x.get("role") == "self" for x in ps): err.append("role: self の当事者が無い")
    # language
    lc = get(d, "language.comment"); ld = get(d, "language.description")
    if not isinstance(lc, list) or not lc or not set(lc) <= {"en", "ja"}: err.append(f"language.comment は en/ja のリスト（現在 {lc!r}）")
    if ld not in ("en", "ja", "any"): err.append(f"language.description は en|ja|any（現在 {ld!r}）")
    # tracker
    if not isinstance(get(d, "tracker.enabled"), bool): err.append("tracker.enabled は true|false")
    if get(d, "tracker.enabled"):
        for k in ("tracker.name", "tracker.link_label", "tracker.gate_token"):
            if not get(d, k): err.append(f"{k} が空（tracker.enabled のとき必須）")
        if get(d, "tracker.kind") == "excel" and not (get(d, "tracker.sheet") and get(d, "tracker.columns")): warn.append("tracker.kind=excel だが sheet/columns が未設定（手順 2 で必要）")
        if not get(d, "tracker.todo_marker"): warn.append("tracker.todo_marker が空（確定アクションの印）")
    # description
    secs = get(d, "description.sections") or {}
    for k in ("background", "dod", "materials"):
        if not secs.get(k): err.append(f"description.sections.{k} が空")
    for k in secs:
        if k not in ("purpose", "background", "dod", "deliverable_contents", "nice_to_have", "materials"): err.append(f"description.sections.{k} は未知のキー（purpose/background/dod/deliverable_contents/nice_to_have/materials）")
    rules = get(d, "description.rules") or {}
    for k in rules:
        if k not in ("sections_strict", "background_std", "background_max", "background_line_chars", "dod_std", "dod_max", "done_evidence"): err.append(f"description.rules.{k} は未知のキー")
    for k in ("background_std", "background_max", "background_line_chars", "dod_std", "dod_max"):
        if rules.get(k) is not None and not (isinstance(rules[k], int) and rules[k] > 0): err.append(f"description.rules.{k} は正の整数")
    if rules.get("background_std") and rules.get("background_max") and rules["background_std"] > rules["background_max"]: err.append("description.rules.background_std > background_max")
    if rules.get("dod_std") and rules.get("dod_max") and rules["dod_std"] > rules["dod_max"]: err.append("description.rules.dod_std > dod_max")
    if rules.get("sections_strict") and not secs.get("purpose"): warn.append("sections_strict だが description.sections.purpose 未定義（Purpose 節を使うなら定義）")
    if get(d, "description.title_line") is None: warn.append("description.title_line 未設定（既定 true）")
    if get(d, "meeting.tz_offset_hours") is None: warn.append("meeting.tz_offset_hours 未設定（既定 9）")
    # 本文 A〜F
    for sec in ("A.", "B.", "C.", "D.", "E.", "F."):
        if not re.search(rf"^## {re.escape(sec)}", body, re.M): warn.append(f"本文に '## {sec}' 節が無い")
    # 公開見本チェック
    if a.public:
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", str(get(d, "jira.cloud_id", ""))) and not set(str(get(d, "jira.cloud_id"))) <= set("0-"):
            warn.append("cloud_id が実在しそうな UUID（見本は 0000… にする）")
        if site and not re.search(r"example", site): warn.append(f"jira.site が example ドメインでない: {site}")
        if st == "verified": warn.append("見本は status: draft にする")
    tag = "✗" if err else ("△" if warn else "✓")
    print(f"{tag} {p.name}" + (f" ({get(d,'profile')}, {st})" if not err else ""))
    for e in err: print(f"   ERROR {e}")
    for w in warn: print(f"   warn  {w}")
    total_err += len(err)
sys.exit(2 if total_err else 0)
