import sys, re
sys.stdout.reconfigure(encoding="utf-8")
t = open(sys.argv[1], encoding="utf-8").read()
num = lambda s: 0.0 if s.strip() in ("—", "-", "", "—%") else float(s.replace(",", "").replace("%", ""))
rows = []
for line in t.splitlines():
    c = [x.strip() for x in line.split("|")]
    if len(c) == 8 and c[0].isdigit() and int(c[0]) <= 8:
        rows.append((c[1], num(c[3]), num(c[6]), num(c[7]), num(c[4]), num(c[5])))
    if c[0] == "9": tot = c
print("asset rows parsed:", len(rows))
for r in rows: print("  ", r)
print("sum low/high $:", sum(r[2] for r in rows), sum(r[3] for r in rows), " stated total row:", tot)
