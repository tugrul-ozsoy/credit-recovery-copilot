"""Human confirmation / correction of an extraction, then a deterministic rerun (no AI calls).

    python scripts/review_extraction.py output/extractions/<file>.json                      # show fields + warnings
    python scripts/review_extraction.py <file>.json --set "assets[1].recovery_value[0]=5427" --by "Your Name"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.review import apply_corrections, review_rows, save


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("extraction")
    p.add_argument("--set", action="append", default=[], metavar="PATH=VALUE", help="a correction (repeatable)")
    p.add_argument("--by", help="name of the person correcting")
    args = p.parse_args()
    record = json.loads(Path(args.extraction).read_text(encoding="utf-8"))
    if args.set:
        changes = []
        for item in args.set:
            path, _, raw = item.partition("=")
            changes.append((path.strip(), json.loads(raw)))
        record = apply_corrections(record, changes, args.by)
        print("saved", save(record).as_posix())
    a = record["result"]["assessment"]
    print(f"status: {a['status']} | grounded {a['grounded']} | crossfoot {a['crossfoot_ok']} | "
          f"reconciles {a['reconciles_with_filed']}")
    for w in a["warnings"]:
        print(f"  [{w['severity']}] {w['kind']}: {w['message']}")
    for row in review_rows(record):
        if row["warnings"] or row["provenance"] != "extracted":
            print(f"  {row['field']:<40} {str(row['value']):<14} {row['provenance']:<22} {'; '.join(row['warnings'])[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
