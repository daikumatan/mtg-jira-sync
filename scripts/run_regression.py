#!/usr/bin/env python3
"""
回帰テスト: fixtures の各ケースで jira_sync_report.py を実行し、payload（既定）と report md（--strict）が期待値と一致するか確かめる。
scripts/ を変更したら必ず回す。実案件の fixture はリポジトリの外に置き --fixtures-dir で追加する。

ケース dir の構成:
  case.json          {"profile": "<パス>", "date": "YYYY-MM-DD", "args": {"tracker_url": "...", "prev_links": {...},
                                                                 "meeting_type": "weekly|internal|customer", "meeting_name": "...", "parent": "...", "track_label": "..."}}
                     profile はケース dir → リポジトリ root → 絶対パス の順で解決
  dump.json / content.json / proposals.json     必須
  tracker_scan.json / transcript.txt            任意（あれば渡す）
  expected_payload.json / expected_report.md    期待値（--update で生成・更新）

usage:
  python run_regression.py [--fixtures-dir DIR ...] [--case NAME] [--update] [--strict] [--verbose]
exit: 0 一致 / 1 不一致・実行失敗 / 2 fixture 不備
"""
import argparse, json, subprocess, sys, tempfile, difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = Path(__file__).resolve().parent / "jira_sync_report.py"

ap = argparse.ArgumentParser()
ap.add_argument("--fixtures-dir", action="append", default=[], help="追加 fixture dir（複数可）。既定はリポジトリの tests/fixtures")
ap.add_argument("--case", default=None, help="このケース名だけ実行")
ap.add_argument("--update", action="store_true", help="期待値を現在の出力で上書き")
ap.add_argument("--strict", action="store_true", help="report md も比較する")
ap.add_argument("--verbose", action="store_true")
a = ap.parse_args()

dirs = [ROOT / "tests" / "fixtures"] + [Path(d).expanduser() for d in a.fixtures_dir]
cases = []
for d in dirs:
    if not d.is_dir():
        print(f"⚠ fixture dir が無い: {d}"); continue
    cases += sorted(p for p in d.iterdir() if (p / "case.json").is_file())
if a.case: cases = [c for c in cases if c.name == a.case]
if not cases: print("ケースが無い"); sys.exit(2)

def resolve_profile(case_dir, p):
    p = Path(p).expanduser()
    for cand in ([case_dir / p, ROOT / p] if not p.is_absolute() else [p]):
        if cand.is_file(): return cand
    return None

def norm_payload(s):
    d = json.loads(s)
    return json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True)

fail = 0; bad = 0
for c in cases:
    meta = json.loads((c / "case.json").read_text(encoding="utf-8"))
    prof = resolve_profile(c, meta["profile"])
    missing = [f for f in ("dump.json", "content.json", "proposals.json") if not (c / f).is_file()]
    if prof is None or missing:
        print(f"✗ {c.name}: fixture 不備 — " + ("profile が見つからない " if prof is None else "") + " ".join(missing)); bad += 1; continue
    with tempfile.TemporaryDirectory() as td:
        out_md, out_pl = Path(td) / "report.md", Path(td) / "payload.json"
        cmd = [sys.executable, str(REPORT), "--profile", str(prof), "--content", str(c / "content.json"), "--jira-dump", str(c / "dump.json"),
               "--proposals", str(c / "proposals.json"), "--date", meta["date"], "--out-md", str(out_md), "--out-payload", str(out_pl)]
        args = meta.get("args", {})
        if args.get("tracker_url"): cmd += ["--tracker-url", args["tracker_url"]]
        if args.get("prev_links"): cmd += ["--prev-links", json.dumps(args["prev_links"], ensure_ascii=False)]
        for k in ("meeting_type", "meeting_name", "parent", "track_label"):
            if args.get(k): cmd += ["--" + k.replace("_", "-"), args[k]]
        cmd += ["--out-preview", str(Path(td) / "preview.md")]
        if (c / "tracker_scan.json").is_file(): cmd += ["--tracker-scan", str(c / "tracker_scan.json")]
        if (c / "transcript.txt").is_file(): cmd += ["--transcript", str(c / "transcript.txt")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode not in (0, 2) or not out_pl.is_file():
            print(f"✗ {c.name}: 実行失敗 (exit {r.returncode})\n{r.stderr.strip()[-800:]}"); fail += 1; continue
        got_pl, got_md = norm_payload(out_pl.read_text(encoding="utf-8")), out_md.read_text(encoding="utf-8")
    exp_pl, exp_md = c / "expected_payload.json", c / "expected_report.md"
    if a.update:
        exp_pl.write_text(got_pl + "\n", encoding="utf-8"); exp_md.write_text(got_md, encoding="utf-8")
        print(f"↻ {c.name}: 期待値を更新"); continue
    if not exp_pl.is_file():
        print(f"✗ {c.name}: expected_payload.json が無い（--update で生成）"); bad += 1; continue
    ok = True
    if norm_payload(exp_pl.read_text(encoding="utf-8")) != got_pl:
        ok = False; print(f"✗ {c.name}: payload 不一致")
        if a.verbose: sys.stdout.writelines(difflib.unified_diff(norm_payload(exp_pl.read_text(encoding='utf-8')).splitlines(True), got_pl.splitlines(True), "expected", "got", n=2))
    if a.strict and exp_md.is_file() and exp_md.read_text(encoding="utf-8") != got_md:
        ok = False; print(f"✗ {c.name}: report md 不一致")
        if a.verbose: sys.stdout.writelines(difflib.unified_diff(exp_md.read_text(encoding='utf-8').splitlines(True), got_md.splitlines(True), "expected", "got", n=1))
    if ok: print(f"✓ {c.name}"); 
    else: fail += 1
print(f"\n{len(cases)} cases: fail={fail} fixture-error={bad}")
sys.exit(1 if fail else (2 if bad else 0))
