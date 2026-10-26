"""Table-aware EDGAR HTML -> text. Usage: python -I html2text.py in.htm out.txt
Cells joined with ' | ', rows on own line, page breaks -> '\n=====PAGEBREAK=====\n'."""
import sys, re, html
from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []; self.row = None; self.cell = None; self.skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs); style = (a.get("style") or "").lower().replace(" ", "")
        if tag in ("script", "style"): self.skip += 1
        if "page-break-before:always" in style or "break-before:page" in style:
            self.out.append("\n=====PAGEBREAK=====\n")
        if tag == "tr": self.row = []
        elif tag in ("td", "th"): self.cell = []
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4") and self.cell is None:
            self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.skip -= 1
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            t = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append(t); self.cell = None
        elif tag == "tr" and self.row is not None:
            cells = [c for c in self.row if c not in ("", "$", "%", ")")]
            # re-attach dangling ')' and '%' to previous cell
            merged = []
            for c in self.row:
                if c in ("%", ")", ")%", "%)") and merged: merged[-1] += c
                elif c in ("", "$"): continue
                else: merged.append(c)
            if merged: self.out.append("\n" + " | ".join(merged))
            self.row = None
        elif tag in ("p", "div") and self.cell is None:
            self.out.append("\n")
    def handle_data(self, d):
        if self.skip: return
        if self.cell is not None: self.cell.append(d)
        else: self.out.append(d)

src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
p = P(); p.feed(src)
txt = "".join(p.out).replace("\xa0", " ")
txt = re.sub(r"[ \t]+", " ", txt)
txt = re.sub(r"\n\s*\n+", "\n", txt)
open(sys.argv[2], "w", encoding="utf-8").write(txt)
print(sys.argv[2][-60:], "chars", len(txt), "pagebreaks", txt.count("=====PAGEBREAK====="))
