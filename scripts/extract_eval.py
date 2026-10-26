"""Test 2: score a real extraction against the hand-keyed ground truth in data/cases/<case>/case.json.

    python scripts/extract_eval.py output/extractions/ww_international-<run_id>.json
    python scripts/extract_eval.py --run ww_international      # make a new live extraction first, then score it

The model never sees case.json; it is read here, after the run. Writes output/extraction_eval.json (appends).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evaluate import score
from app.logs import append_json, utc_now
from engine.schema import CASES_DIR, LiquidationAnalysis, load_case

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "extraction_eval.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("extraction", nargs="?", help="output/extractions/<case>-<run_id>.json")
    p.add_argument("--run", metavar="CASE", help="run a new live extraction of data/cases/CASE/source.htm first")
    args = p.parse_args()
    if args.run:
        from app.extract import extract
        rec = extract(CASES_DIR / args.run / "source.htm", args.run)
        path = ROOT / rec["file"]
    else:
        path = Path(args.extraction)
    rec = json.loads(path.read_text(encoding="utf-8"))
    gt = load_case(rec["case"]).analysis
    result = {"timestamp_utc": utc_now(), "extraction_file": path.resolve().relative_to(ROOT).as_posix(),
              "run_id": rec["run_id"], "case": rec["case"], "attempts": rec["attempts"], "seconds": rec["seconds"],
              "tokens": rec["tokens"], "cost_usd": rec["cost_usd"]}
    if rec.get("error"):
        result["error"] = rec["error"]
    else:
        ex = LiquidationAnalysis.model_validate(rec["result"]["analysis"])
        result["final"] = score(gt, ex)
        if rec.get("first_attempt") and rec["attempts"] > 1:
            try:
                result["first_attempt"] = score(gt, LiquidationAnalysis.model_validate(rec["first_attempt"]))
            except Exception as exc:
                result["first_attempt"] = {"error": f"first attempt failed schema validation: {exc}"[:500]}
        a = rec["result"]["assessment"]
        result["assessment"] = {k: a[k] for k in ("status", "grounded", "crossfoot_ok", "reconciles_with_filed", "max_pct_gap")}
        result["warnings"] = a["warnings"]
    append_json(OUT, result)
    print(json.dumps({k: v for k, v in result.items() if k != "warnings"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
