import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t = open(sys.argv[1], encoding="utf-8").read()
pages = t.split("=====PAGEBREAK=====")
print("TOTAL html pages:", len(pages))
print("FIRST PAGE:", re.sub(r"\s+", " ", pages[0])[:400])
a, b = int(sys.argv[2]), int(sys.argv[3])
for i in range(a, min(b+1, len(pages))):
    lines = [l for l in pages[i].strip().splitlines() if l.strip()]
    print(i, "| first:", (lines[0][:60] if lines else ""), "| last:", (lines[-1][:40] if lines else ""))
