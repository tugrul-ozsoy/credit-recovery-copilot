"""Recompute every bundled filing and compare it with what the debtor filed (no AI calls).

    python scripts/reconcile_cases.py            # print the tables, write output/reconciliation.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.logs import utc_now
from engine.schema import keyed_slugs, load_case
from engine.waterfall import crossfoot, reconcile, run_scenario

OUT = Path(__file__).resolve().parents[1] / "output" / "reconciliation.json"


def main() -> None:
    report = {"generated_utc": utc_now(), "cases": []}
    for slug in keyed_slugs():
        case = load_case(slug)
        a = case.analysis
        rec = reconcile(a)
        foot = crossfoot(a)
        print(f"\n=== {case.source.company} ({case.structure}; {a.units}) -> "
              f"{'TIES' if rec.ties else 'DOES NOT TIE'} (max gap {rec.max_pct_gap:.1f} pts)")
        print(f"{'class':<52}" + "".join(f"{s:>22}" for s in a.scenarios))
        results = [run_scenario(a, i) for i in range(len(a.scenarios))]
        for k, c in enumerate(a.claims):
            cells = []
            for i, r in enumerate(results):
                filed = c.filed_recovery_pct[i]
                cells.append(f"{r.classes[k].pct:6.1f}% vs {filed if filed is not None else '-':>5}%")
            print(f"{c.label[:50]:<52}" + "".join(f"{x:>22}" for x in cells))
        print("fulcrum: " + " | ".join(f"{r.scenario}: {', '.join(r.fulcrum) or 'none'}" for r in results))
        report["cases"].append({
            "slug": slug, "company": case.source.company, "structure": case.structure, "units": a.units,
            "source_url": case.source.url, "ties": rec.ties, "max_pct_gap": round(rec.max_pct_gap, 3),
            "crossfoot_ok": all(c.ok for c in foot),
            "checks": [{"scenario": c.scenario, "item": c.item, "computed": round(c.computed, 4), "filed": c.filed,
                        "tolerance": c.tolerance, "ok": c.ok} for c in rec.checks + foot],
            "fulcrum": {r.scenario: r.fulcrum for r in results},
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(OUT.parents[1]).as_posix()}")


if __name__ == "__main__":
    main()
