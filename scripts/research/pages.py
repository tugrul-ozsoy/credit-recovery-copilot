import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
t = open(sys.argv[1], encoding="utf-8").read()
pages = t.split("=====PAGEBREAK=====")
a, b = int(sys.argv[2]), int(sys.argv[3])
sel = pages[a:b+1]
if len(sys.argv) > 4:
    out = "\n=====PAGEBREAK=====\n".join(sel)
    open(sys.argv[4], "w", encoding="utf-8").write(out)
    print("chars", len(out), "est_tokens", len(out)//4)
else:
    for i, p in zip(range(a, b+1), sel):
        print(f"\n######## page_idx {i}\n{p.strip()}")
