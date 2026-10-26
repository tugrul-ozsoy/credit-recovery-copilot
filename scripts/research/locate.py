import sys, re
t = open(sys.argv[1], encoding="utf-8").read()
pages = t.split("=====PAGEBREAK=====")
pat = re.compile(sys.argv[2], re.I)
for i, pg in enumerate(pages):
    n = len(pat.findall(pg))
    if n: print(f"page_idx {i}: {n} hits, len {len(pg)} | first line: {pg.strip()[:90]!r}")
