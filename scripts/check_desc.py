#!/usr/bin/env python3
"""書き込み応答の description（stdin）を検査。崩れ・禁止要素があれば NG を出す（exit 1）。
usage: python check_desc.py [--lang en|ja|any] < response_description.txt   （--lang はプロファイル language.description）"""
import sys, re, argparse
ap = argparse.ArgumentParser(); ap.add_argument("--lang", default="any"); a = ap.parse_args()
d = sys.stdin.read()
ng = []
if re.search(r"^\s*[*-]\s*\\\[[ x]\\\]", d, re.M): ng.append("チェックリストが箇条書きに崩れている（\\[ \\]）→ チェック行内のリンクを外へ")
if "<custom" in d: ng.append("スマートリンク記法 <custom …> が文字列として残っている → [URL](URL) に変換")
if "![](" in d: ng.append("画像参照 ![](…) が含まれる → 画像は往復で壊れる。コメントへ移動を案内")
if a.lang == "en" and re.search(r"[぀-ヿ一-鿿]", re.sub(r"\[[^\]]*\]\([^)]*\)", "", d)): ng.append("Description に日本語が含まれる（この案件は英語のみ）")
print("OK" if not ng else "NG\n- " + "\n- ".join(ng)); sys.exit(1 if ng else 0)
