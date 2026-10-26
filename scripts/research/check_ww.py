"""Deterministic integrity check on extracted WW International asset table: does sum of per-asset $ equal stated total, and does book*% ~= $?"""
import sys, re
sys.stdout.reconfigure(encoding="utf-8")
t = open(sys.argv[1], encoding="utf-8").read()
num = lambda s: 0.0 if s.strip() in ("—", "-", "") else float(s.replace(",", "").replace("%", ""))
assets = ["Cash and Cash Equivalents","Accounts Receivable","Prepaids & Other Current Assets","Fixed Assets","Goodwill","Intangibles","Investment in Subs","Other LT Assets"]
rows = {}
for line in t.splitlines():
    c = [x.strip() for x in line.split("|")]
    if c[0] in assets and len(c) == 9:
        rows[c[0]] = dict(book=num(c[1]), pct=[num(x) for x in c[3:6]], amt=[num(x) for x in c[6:9]])
    if c[0] == "Total Assets Recoveries": total = [num(x) for x in c[2:5]]; tbook = num(c[1])
print("parsed asset rows:", len(rows), "of", len(assets))
for k, r in rows.items():
    implied = [round(r["book"] * p / 100) for p in r["pct"]]
    print(f"  {k:35s} book={r['book']:>9,.0f} pct={r['pct']} amt={r['amt']} book*pct={implied}")
s = [sum(r["amt"][i] for r in rows.values()) for i in range(3)]
print("sum of asset $ (L/M/H):", s, " stated total:", total, " book sum:", sum(r['book'] for r in rows.values()), "stated:", tbook)
