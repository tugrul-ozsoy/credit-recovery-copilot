"""Find the liquidation-analysis exhibit inside a full disclosure statement and sanitize only that exhibit.

A disclosure statement is 200-460 printed pages; the liquidation analysis is one exhibit of ~10-16 pages. The
filing is split at its CSS page breaks, the exhibit's cover page is found, and only those pages go through the
HW6 sanitizer (app/sanitize.py) and on to the model.

Table-of-contents hits are skipped: the cover page must be a short page that is only the heading
("EXHIBIT B  Liquidation Analysis"), not a page that lists the heading among other entries.

PDF appendices (e.g. a claims-agent download such as Dean Foods' "Appendix B Liquidation Analysis"): the pages from
the heading page through the first page that holds a recovery summary table are sanitized with the HW6 PDF rules and
sent; later pages (per-entity tables, notes) are not sent, and the Exhibit records which pages were used.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from app.sanitize import QuarantinedItem, injection_indicators, normalize_text, visible_html, visible_pdf_pages

PAGE_BREAK = re.compile(r"<[a-zA-Z][^>]*style\s*=\s*\"[^\"]*(?:page-break-before\s*:\s*always|break-before\s*:\s*page)[^>]*>", re.I)
HEADING = re.compile(r"^\W*(?:exhibit|appendix|schedule)\s+([a-z0-9]{1,3})\W{0,5}liquidation\s+analysis\W*$", re.I)
ANY_EXHIBIT_COVER = re.compile(r"^\W*exhibit\s+[a-z0-9]{1,3}\b", re.I)
STYLE_BLOCKS = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
COVER_MAX_CHARS = 200  # a cover page is just the heading; a table-of-contents page is much longer


def _quick_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;|&#xa0;", " ", text, flags=re.I)
    text = re.sub(r"&#8211;|&#8212;|&ndash;|&mdash;", "-", text, flags=re.I)
    return " ".join(text.split())


def split_pages(html: str) -> list[str]:
    """Raw HTML cut at each element that starts a new printed page."""
    starts = [0] + [m.start() for m in PAGE_BREAK.finditer(html)] + [len(html)]
    return [html[a:b] for a, b in zip(starts, starts[1:]) if b > a]


@dataclass
class Exhibit:
    source: str
    source_sha256: str
    heading: str
    first_page: int  # index into split_pages(), the cover page
    last_page: int
    pages_in_filing: int
    skipped_heading_hits: list[int]  # pages that mention the heading but are not the cover (table of contents etc.)
    text: str  # sanitized, normalized text of the exhibit: what the model sees
    quarantined: list[QuarantinedItem] = field(default_factory=list)
    invisible_characters_removed: int = 0
    injection_indicators: list[str] = field(default_factory=list)
    layout_warnings: list[str] = field(default_factory=list)  # pages the visibility rules could not resolve


PDF_SUMMARY = re.compile(r"recovery\s*%.*?total", re.I | re.S)
PDF_MAX_PAGES = 12


def _locate_pdf(path: Path, raw: bytes) -> Exhibit:
    import io

    reader = PdfReader(io.BytesIO(raw))
    texts = [" ".join((pg.extract_text() or "").split()) for pg in reader.pages]
    heads = [i for i, t in enumerate(texts) if re.search(r"(exhibit|appendix|schedule)\s+[a-z0-9]{1,3}\W{0,5}liquidation\s+analysis", t[:300], re.I)]
    if not heads:
        raise ValueError("No liquidation-analysis heading found at the top of any PDF page.")
    first = heads[0]
    window = range(first, min(first + PDF_MAX_PAGES, len(texts)))
    last = next((j for j in window if PDF_SUMMARY.search(texts[j])), window[-1])
    blocks, quarantined, layout = [], [], []
    for j in range(first, last + 1):
        [(_, visible)], q = visible_pdf_pages(raw, [j])
        plain = (reader.pages[j].extract_text() or "").strip()
        if plain and len(visible) < 0.9 * len(plain):
            # Embedded tables (e.g. a pasted spreadsheet) use coordinates and fills the visibility rules cannot
            # resolve: they would withhold most of the page. Send the plain text and show what the rules flagged.
            blocks.append(f"[page {j + 1}]\n{plain}")
            layout.append(f"page {j + 1}: visibility rules could not resolve the layout ({len(q)} fragments flagged "
                          f"as white or off-page, e.g. '{q[0].excerpt[:60]}'); plain text was sent - review this page")
        else:
            blocks.append(f"[page {j + 1}]\n{visible}")
            quarantined += q
    text, removed = normalize_text("\n\n".join(blocks))
    heading = re.search(r"(exhibit|appendix|schedule)\s+[a-z0-9]{1,3}\W{0,5}liquidation\s+analysis", texts[first], re.I).group(0)
    return Exhibit(
        source=path.as_posix(), source_sha256=hashlib.sha256(raw).hexdigest(), heading=heading,
        first_page=first + 1, last_page=last + 1, pages_in_filing=len(texts), skipped_heading_hits=heads[1:],
        text=text, quarantined=quarantined, invisible_characters_removed=removed,
        injection_indicators=injection_indicators(text), layout_warnings=layout,
    )


def locate_exhibit(path: str | Path) -> Exhibit:
    raw = Path(path).read_bytes()
    if raw[:5] == b"%PDF-":
        return _locate_pdf(Path(path), raw)
    html = raw.decode("utf-8", errors="replace")
    pages = split_pages(html)
    texts = [_quick_text(p) for p in pages]
    hits = [i for i, t in enumerate(texts) if re.search(r"liquidation\s+analysis", t, re.I) and re.search(r"exhibit", t, re.I)]
    covers = [i for i in hits if len(texts[i]) <= COVER_MAX_CHARS and HEADING.match(texts[i])]
    if not covers:
        raise ValueError("No liquidation-analysis exhibit cover page found (looked for a page that is only "
                         "'Exhibit X Liquidation Analysis').")
    first = covers[-1]  # the body exhibit comes after any front-matter mention
    last = len(pages) - 1
    for j in range(first + 1, len(pages)):  # the exhibit ends where the next exhibit's cover page starts
        if len(texts[j]) <= COVER_MAX_CHARS and ANY_EXHIBIT_COVER.match(texts[j]):
            last = j - 1
            break
    styles = "".join(STYLE_BLOCKS.findall(html))  # keep <style> rules so CSS-hidden text is still detected
    visible, quarantined = visible_html(styles + "".join(pages[first:last + 1]), where=f"exhibit pages {first}-{last}, ")
    text, removed = normalize_text(visible)
    return Exhibit(
        source=Path(path).as_posix(), source_sha256=hashlib.sha256(raw).hexdigest(), heading=texts[first],
        first_page=first, last_page=last, pages_in_filing=len(pages),
        skipped_heading_hits=[i for i in hits if i != first], text=text, quarantined=quarantined,
        invisible_characters_removed=removed, injection_indicators=injection_indicators(text),
    )
