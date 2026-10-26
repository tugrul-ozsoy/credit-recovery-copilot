"""Build slides.html: 10 reveal.js slides (reveal.js from a CDN), screenshots embedded, charts drawn from real data.

    python scripts/build_slides.py            # -> slides.html

Chart data: the Wolfspeed stress test is recomputed here by engine/waterfall.py from the saved real extraction;
token and cost figures come from output/usage_log.json (via scripts/build_report.load_runs).
"""

from __future__ import annotations

import base64
import html
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_report import CASE_NAMES, REPO_URL, load_runs
from engine.schema import LiquidationAnalysis
from engine.waterfall import run_scenario

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "slides.html"
e = html.escape


def shot(name: str, height: str, pos: str = "top", caption: str = "") -> str:
    data = base64.b64encode((SHOTS / name).read_bytes()).decode()
    return (f'<figure class="shot"><img src="data:image/png;base64,{data}" style="height:{height};object-position:{pos}" '
            f'alt="{e(caption)}"><figcaption>{caption}</figcaption></figure>')


def bars(rows: list[tuple[str, float, float]], width=560, label_w=210) -> str:
    """Horizontal paired bars (filed basis vs stressed), values in %, drawn from real engine output."""
    h = 34 * len(rows) + 30
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">']
    scale = (width - label_w - 60) / 100
    for i, (label, base, new) in enumerate(rows):
        y = 10 + i * 34
        out.append(f'<text x="0" y="{y + 15}" class="bl">{e(label)}</text>')
        out.append(f'<rect x="{label_w}" y="{y + 2}" width="{max(base * scale, 1):.1f}" height="11" rx="3" class="b0"/>')
        out.append(f'<rect x="{label_w}" y="{y + 15}" width="{max(new * scale, 1):.1f}" height="11" rx="3" class="b1"/>')
        out.append(f'<text x="{label_w + max(base * scale, 1) + 6:.1f}" y="{y + 12}" class="bv0">{base:.1f}%</text>')
        out.append(f'<text x="{label_w + max(new * scale, 1) + 6:.1f}" y="{y + 25}" class="bv1">{new:.1f}%</text>')
    out.append(f'<rect x="{label_w}" y="{h - 14}" width="12" height="8" class="b0"/><text x="{label_w + 16}" y="{h - 7}" class="lg">filed assumptions</text>')
    out.append(f'<rect x="{label_w + 140}" y="{h - 14}" width="12" height="8" class="b1"/><text x="{label_w + 156}" y="{h - 7}" class="lg">PP&amp;E at 13.7% of book</text>')
    out.append("</svg>")
    return "".join(out)


def cost_chart(runs: list[dict], width=560) -> str:
    mx = max(r["cost"] for r in runs)
    h = 26 * len(runs) + 10
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img">']
    for i, r in enumerate(runs):
        y = 4 + i * 26
        w = (width - 250) * r["cost"] / mx
        short = {"ww_international": "WW", "wolfspeed": "Wolfspeed", "enviva": "Enviva", "dean_foods": "Dean Foods"}
        name = short[r["case"]] + (" · safety test" if r["injection"] else "")
        out.append(f'<text x="0" y="{y + 14}" class="bl">{e(name)}</text>')
        out.append(f'<rect x="170" y="{y + 3}" width="{w:.1f}" height="14" rx="3" class="{"b1" if r["status"] == "reconciled" else "bw"}"/>')
        out.append(f'<text x="{176 + w:.1f}" y="{y + 14}" class="bv1">${r["cost"]:.4f} · {r["seconds"]:.0f}s</text>')
    out.append("</svg>")
    return "".join(out)


def main() -> int:
    runs = load_runs()
    rec = json.loads((ROOT / "output" / "extractions" / "wolfspeed-24601fd7322e.json").read_text(encoding="utf-8"))
    a = LiquidationAnalysis.model_validate(rec["result"]["analysis"])
    base, stressed = run_scenario(a, 1), run_scenario(a, 1, {"Property, Plant & Equipment": 13.7})
    pick = ["Senior Secured Notes", "Administrative Claims", "Grants and Gov't Subsidies", "Convertible Notes due 2029", "General Unsecured Claims"]
    rows = [(c.label, b.pct, s.pct) for b, s in zip(base.classes, stressed.classes) for c in [b] if c.label in pick]
    consolidated = [r for r in runs if r["score"] and r["case"] in ("ww_international", "wolfspeed")]
    perfect = sum(1 for r in consolidated if r["score"]["correct"] == r["score"]["fields_scored"])
    fields = sum(r["score"]["fields_scored"] for r in consolidated)
    costs = [r["cost"] for r in runs]
    mean_cost = statistics.mean(costs)
    mean_in = statistics.mean(r["t"]["input_tokens"] for r in runs)
    mean_out = statistics.mean(r["t"]["output_tokens"] for r in runs)
    dean = json.loads((ROOT / "docs" / "pilot" / "dean_foods_live_test.json").read_text(encoding="utf-8"))
    fresh = json.loads((ROOT / "docs" / "fresh_clone" / "fresh_clone_test.json").read_text(encoding="utf-8"))

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credit Recovery Decision Copilot — slides</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css">
<style>
:root {{ --bg:#070b1a; --ink:#e8eefc; --muted:#9fb0d6; --cyan:#22d3ee; --blue:#3b82f6; --violet:#8b5cf6; --amber:#f59e0b; --glass:rgba(20,30,62,.55); --line:rgba(148,178,255,.22); }}
html, body, .reveal-viewport {{ background-color:#070b1a !important; background-image: radial-gradient(1200px 700px at 15% 10%, #1b2a6b 0%, transparent 60%), radial-gradient(900px 600px at 90% 90%, #3b1d6e 0%, transparent 55%) !important; }}
.reveal {{ font-family:"Segoe UI Variable","Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif; color:var(--ink); font-size:34px; }}
.reveal .slides {{ text-align:left; }}
.reveal h1, .reveal h2 {{ font-family:inherit; color:#fff; letter-spacing:-.5px; text-transform:none; margin:0 0 .35em; }}
.reveal h1 {{ font-size:2.1em; line-height:1.05; }} .reveal h2 {{ font-size:1.35em; }}
.eyebrow {{ color:var(--cyan); font-size:.5em; letter-spacing:.18em; text-transform:uppercase; font-weight:700; margin-bottom:.4em; }}
.muted {{ color:var(--muted); }} .small {{ font-size:.6em; }} .xs {{ font-size:.5em; color:var(--muted); }}
.glass {{ background:var(--glass); border:1px solid var(--line); border-radius:18px; padding:18px 22px; box-shadow:0 10px 40px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06); }}
@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{ .glass {{ backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }} }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; align-items:start; }}
.grid3 {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
.grid5 {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; }}
.kpi b {{ display:block; font-size:1.3em; color:#fff; font-variant-numeric:tabular-nums; }} .kpi span {{ font-size:.52em; color:var(--muted); }}
.pill {{ display:inline-block; font-size:.42em; font-weight:700; letter-spacing:.08em; padding:.25em .7em; border-radius:999px; border:1px solid var(--cyan); color:var(--cyan); }}
.pill.warn {{ border-color:var(--amber); color:#1a1205; background:var(--amber); }}
.reveal ul {{ margin:0; padding-left:1em; }} .reveal li {{ margin:.22em 0; font-size:.7em; line-height:1.38; }}
.shot {{ margin:0; }} .shot img {{ width:100%; object-fit:cover; border-radius:12px; border:1px solid var(--line); margin:0; box-shadow:0 12px 30px rgba(0,0,0,.45); }}
.shot figcaption {{ font-size:.46em; color:var(--muted); margin-top:8px; }}
svg text {{ font-family:"Segoe UI",system-ui,sans-serif; }}
.bl {{ fill:#dbe4ff; font-size:15px; }} .bv0 {{ fill:#9fb0d6; font-size:13px; }} .bv1 {{ fill:#e8eefc; font-size:13px; font-weight:600; }} .lg {{ fill:#9fb0d6; font-size:13px; }}
.b0 {{ fill:#475a8c; }} .b1 {{ fill:url(#g); fill:#22d3ee; }} .bw {{ fill:#f59e0b; }}
.pillar {{ text-align:left; }} .pillar b {{ display:block; color:var(--cyan); font-size:.66em; margin-bottom:.35em; }} .pillar span {{ font-size:.54em; color:#cfd9f5; line-height:1.4; display:block; }}
.quote {{ border-left:4px solid var(--cyan); padding-left:18px; font-size:.82em; line-height:1.35; color:#fff; }}
.reveal .progress {{ color:var(--cyan); }} .reveal .controls {{ color:var(--cyan); }}
.reveal .slide-number {{ background:transparent; color:var(--muted); font-size:14px; }}
@media (prefers-reduced-motion: reduce) {{ .reveal .slides section {{ transition:none !important; }} }}
</style></head><body>
<div class="reveal"><div class="slides">

<section>
  <div class="eyebrow">MGT 409 · AI Foundations for Managers · Final project</div>
  <h1>Credit Recovery<br>Decision Copilot</h1>
  <p class="muted" style="font-size:.75em;max-width:1000px">One AI agent copies a bankruptcy liquidation table with a cited source row for every number. Deterministic code recomputes the creditor waterfall, checks it against the debtor's filing, and lets an analyst stress the assumptions.</p>
  <p class="small">Tuğrul Özsoy · October 26, 2026<br><a href="{REPO_URL}" style="color:var(--cyan)">{REPO_URL.replace('https://', '')}</a></p>
</section>

<section>
  <div class="eyebrow">Why I built this</div>
  <h2>Liquidation value is not asset value minus a haircut</h2>
  <div class="grid2">
    <div class="glass"><ul>
      <li>Preparing for the UCLA Credit Pitch Competition, I had to understand liquidation recovery in a distressed credit.</li>
      <li>Recovery depends on asset-specific haircuts, secured vs unsecured claims, collateral and guarantees, legal-entity boundaries, administration costs and the order of payment.</li>
      <li>A model can look reasonable, add up, and still mislead if the waterfall or structure is wrong.</li>
    </ul></div>
    <div><p class="quote">Could this fragile, manual analysis become reproducible, auditable and source-grounded, while keeping a person in charge when the numbers do not reconcile?</p>
    <p class="xs" style="margin-top:22px">Built independently for MGT 409 from public Chapter 11 filings only. No competition research, team material or assumptions are used, and the app was not used for any competition submission.</p></div>
  </div>
</section>

<section>
  <div class="eyebrow">The problem</div>
  <h2>Small assumption changes move the fulcrum</h2>
  <div class="grid2">
    <div class="glass">{bars(rows)}<p class="xs">Wolfspeed, filed High case vs plant &amp; equipment at the Low-case 13.7% of book. Engine output from the real extraction.</p></div>
    <div><ul>
      <li>Net distributable value: <b>${base.net_distributable_value / 1e6:.2f}bn → ${stressed.net_distributable_value / 1e6:.2f}bn</b></li>
      <li>Fulcrum moves from the unsecured classes to the <b>Senior Secured Notes</b> ({stressed.classes[0].pct:.1f}%).</li>
      <li>Structure matters too: treating Enviva as one consolidated pool would give the DIP lender about 46%; the debtor filed 18%.</li>
      <li class="muted">Today: re-type a 9–17-page exhibit from a 217–460-page filing into Excel, rebuild the waterfall by hand.</li>
    </ul></div>
  </div>
</section>

<section>
  <div class="eyebrow">Our solution</div>
  <h2>AI copies. Code computes. People decide when it doesn't reconcile.</h2>
  <div class="grid5">
    <div class="glass pillar"><b>Source-grounded extraction</b><span>Every number carries the exact table row it came from; code checks it is really printed there.</span></div>
    <div class="glass pillar"><b>Deterministic waterfall</b><span>Absolute priority, pro rata within a class. No arithmetic in the model.</span></div>
    <div class="glass pillar"><b>Reconciliation</b><span>Recompute every filed scenario; RECONCILED only if it matches the debtor's own recoveries.</span></div>
    <div class="glass pillar"><b>Sensitivity</b><span>Sliders rerun the engine instantly, 0 tokens; the fulcrum is shown.</span></div>
    <div class="glass pillar"><b>Human review</b><span>NEEDS REVIEW is never hidden; corrections need a name and keep provenance.</span></div>
  </div>
  <p class="xs" style="margin-top:18px">vs a PDF chatbot: auditable row by row, identical numbers every run, and the filed recoveries act as an answer key that exposes a wrong structure.</p>
</section>

<section>
  <div class="eyebrow">Architecture</div>
  <h2>One agent, everything else code</h2>
  <svg viewBox="0 0 1100 305" width="100%"><defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#9fb0d6"/></marker></defs>
    <g font-size="17" fill="#e8eefc">
    <rect x="10" y="40" width="170" height="80" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="95" y="75" text-anchor="middle" font-weight="600">Public filing</text><text x="95" y="100" text-anchor="middle" font-size="13" fill="#9fb0d6">EDGAR HTML · Epiq PDF</text>
    <rect x="220" y="40" width="190" height="80" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="315" y="75" text-anchor="middle" font-weight="600">Locate + sanitize</text><text x="315" y="100" text-anchor="middle" font-size="13" fill="#9fb0d6">code · exhibit pages only</text>
    <rect x="450" y="28" width="210" height="104" rx="16" fill="#0e7490" stroke="#22d3ee"/><text x="555" y="68" text-anchor="middle" font-weight="700">Extractor agent</text><text x="555" y="93" text-anchor="middle" font-size="13" fill="#cffafe">gpt-6-luna · typed output</text><text x="555" y="114" text-anchor="middle" font-size="13" fill="#cffafe">no side-effect tools</text>
    <rect x="700" y="40" width="170" height="80" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="785" y="75" text-anchor="middle" font-weight="600">Validator</text><text x="785" y="100" text-anchor="middle" font-size="13" fill="#9fb0d6">grounding + totals</text>
    <rect x="910" y="40" width="180" height="80" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="1000" y="75" text-anchor="middle" font-weight="600">Engine</text><text x="1000" y="100" text-anchor="middle" font-size="13" fill="#9fb0d6">priority waterfall</text>
    <line x1="180" y1="80" x2="216" y2="80" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/><line x1="410" y1="80" x2="446" y2="80" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/><line x1="660" y1="70" x2="696" y2="70" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/>
    <line x1="700" y1="98" x2="664" y2="98" stroke="#f59e0b" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#ar)"/><text x="680" y="150" text-anchor="middle" font-size="13" fill="#f59e0b">≤ 1 targeted retry</text>
    <line x1="870" y1="80" x2="906" y2="80" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/>
    <rect x="700" y="200" width="180" height="70" rx="14" fill="rgba(34,211,238,.12)" stroke="#22d3ee"/><text x="790" y="232" text-anchor="middle" font-weight="700" fill="#22d3ee">RECONCILED</text><text x="790" y="255" text-anchor="middle" font-size="13" fill="#9fb0d6">matches the filing</text>
    <rect x="910" y="200" width="180" height="70" rx="14" fill="rgba(245,158,11,.14)" stroke="#f59e0b"/><text x="1000" y="232" text-anchor="middle" font-weight="700" fill="#f59e0b">NEEDS REVIEW</text><text x="1000" y="255" text-anchor="middle" font-size="13" fill="#9fb0d6">shown, never forced</text>
    <line x1="1000" y1="120" x2="800" y2="196" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/><line x1="1000" y1="120" x2="1000" y2="196" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/>
    <rect x="420" y="200" width="240" height="70" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="540" y="232" text-anchor="middle" font-weight="600">Person reviews / corrects</text><text x="540" y="255" text-anchor="middle" font-size="13" fill="#9fb0d6">named · logged · provenance</text>
    <path d="M1000,270 L1000,292 L540,292 L540,276" fill="none" stroke="#9fb0d6" stroke-width="2" marker-end="url(#ar)"/>
    <rect x="10" y="200" width="380" height="70" rx="14" fill="rgba(20,30,62,.7)" stroke="#5a6fb0"/><text x="200" y="232" text-anchor="middle" font-weight="600">Analyst stress test → engine</text><text x="200" y="255" text-anchor="middle" font-size="13" fill="#9fb0d6">sliders · fulcrum · 0 tokens</text>
    </g></svg>
  <p class="xs">FastAPI + one static page. Every run logs tokens and cost (usage_log.json), the text sent (audit_trail.json), the result and provenance (extractions/*.json).</p>
</section>

<section>
  <div class="eyebrow">Real demo</div>
  <h2>WW reconciles; Wolfspeed's fulcrum moves</h2>
  <div class="grid2">
    {shot("02_ww_extraction_usage_activity.png", "430px", "top", "WW International live run 4e51bb02dce2: RECONCILED, 13.4 s, $0.0016, 108/108 fields.")}
    {shot("04_wolfspeed_stress_ppe_13_7.png", "430px", "bottom", "Wolfspeed High case, PP&E 44.8% → 13.7%: Senior Secured Notes 100% → 83.6%, fulcrum moves.")}
  </div>
</section>

<section>
  <div class="eyebrow">Responsible failure</div>
  <h2>Enviva and Dean Foods: <span class="pill warn">⚠ NEEDS REVIEW</span></h2>
  <div class="grid2">
    {shot("05_enviva_needs_review.png", "410px", "top", "Enviva: every number grounded, totals add up — but legal-entity waterfalls cannot be reproduced by one consolidated engine.")}
    {shot("09_dean_foods_needs_review.png", "410px", "top", "Dean Foods (public Epiq PDF, 43 debtors): grounded, flagged NEEDS REVIEW, plus a page-layout warning.")}
  </div>
  <p class="xs">The tool says what it cannot verify instead of producing a confident, wrong recovery. A reviewer's corrections are logged, and still cannot force a reconciliation.</p>
</section>

<section>
  <div class="eyebrow">Tokenomics &amp; safety</div>
  <h2>About a fifth of a cent per filing — measured</h2>
  <div class="grid2">
    <div class="glass">{cost_chart(runs)}<p class="xs">All {len(runs)} live extractions from output/usage_log.json (cyan = reconciled, amber = needs review).</p></div>
    <div>
      <div class="grid3" style="margin-bottom:14px">
        <div class="glass kpi"><b>${mean_cost:.4f}</b><span>mean cost / run</span></div>
        <div class="glass kpi"><b>{mean_in:,.0f}</b><span>mean input tokens</span></div>
        <div class="glass kpi"><b>{mean_out:,.0f}</b><span>mean output tokens</span></div>
      </div>
      <ul>
        <li>Exhibit only: ~6K tokens instead of a ~159K-token filing (WW).</li>
        <li>20 runs/user/month ≈ ${mean_cost * 20:.2f}; 10,000 users ≈ ${mean_cost * 20 * 10000:,.0f}/month in model cost.</li>
        <li>Planted hidden + visible instruction: hidden withheld, visible flagged, still 108/108.</li>
        <li>Fabricated number → one targeted retry → corrected; caps of 4 requests / 80K tokens; rate limit.</li>
      </ul>
    </div>
  </div>
</section>

<section>
  <div class="eyebrow">Impact — what was actually measured</div>
  <h2>Accurate where verifiable, honest where not</h2>
  <div class="grid3" style="margin-bottom:18px">
    <div class="glass kpi"><b>{perfect}/{len(consolidated)}</b><span>live runs with every one of {fields:,} scored fields correct ({sum(1 for r in consolidated if r['case'] == 'ww_international')} repeats on WW, {sum(1 for r in consolidated if r['case'] == 'wolfspeed')} on Wolfspeed)</span></div>
    <div class="glass kpi"><b>{min(r['seconds'] for r in runs):.0f}–{max(r['seconds'] for r in runs):.0f} s</b><span>model time per filing; stress tests instant</span></div>
    <div class="glass kpi"><b>≈ 4 min</b><span>fresh clone → reconciled live run (graders' .env layout)</span></div>
  </div>
  <ul>
    <li><b>Dean Foods live test:</b> {dean['extracted']['claim_classes']} claim classes extracted in {dean['extraction_seconds_model_call']:.0f} s for ${dean['cost_usd']['total']:.4f}; correctly flagged NEEDS REVIEW.</li>
    <li class="muted"><b>Not measured:</b> time saved versus Excel, or a user's opinion. An earlier user trial was reported but has no artifacts, so no claim is made from it.</li>
  </ul>
</section>

<section>
  <div class="eyebrow">Conclusion</div>
  <h2>Reproducible numbers, visible assumptions, human judgment</h2>
  <div class="grid2">
    <div class="glass"><ul>
      <li>Source-grounded extraction + deterministic reconciliation turns a fragile spreadsheet exercise into an auditable one.</li>
      <li>Sensitivity is explicit: the fulcrum is always on screen.</li>
      <li>When structure is beyond the engine, a person decides — by design.</li>
    </ul></div>
    <div class="glass"><b style="color:var(--cyan);font-size:.6em">Next</b><ul>
      <li>Per-entity waterfalls with a reviewable entity map</li>
      <li>20+ double-keyed EDGAR cases</li>
      <li>Timed user study with permission to quote</li>
      <li>Grounded Q&amp;A agent that answers only through engine tools</li>
    </ul></div>
  </div>
  <p class="small" style="margin-top:22px"><a href="{REPO_URL}" style="color:var(--cyan)">{REPO_URL.replace('https://', '')}</a> · <span class="muted">Not investment advice.</span></p>
</section>

</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js"></script>
<script>Reveal.initialize({{ hash: true, controls: true, progress: true, slideNumber: "c/t", center: true, width: 1280, height: 720, margin: 0.05, transition: "fade" }});</script>
</body></html>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT.name}: {OUT.stat().st_size / 1e6:.1f} MB, {doc.count('<section')} slides; fresh clone {fresh['run']['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
