"""Reproducible evidence screenshots of the running app (headless Edge or Chrome, no AI calls).

    python -m app.server                      # in one terminal
    python scripts/capture_screenshots.py     # in another -> docs/screenshots/*.png + manifest.json

Each shot opens a saved, real run by name through a deep link (?run=...), so the images show executed results.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
BASE = "http://127.0.0.1:8000/"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "msedge", "google-chrome", "chromium"]

WW = "ww_international-4e51bb02dce2"
WOLF = "wolfspeed-24601fd7322e"
ENV = "enviva-0323dcfed869"
ENV_REVIEWED = "enviva-0323dcfed869-reviewed-1"
INJECTION = "ww_international-7fd6e19c9c87"
DEAN = "dean_foods-59494a252416"
PPE = "Property, Plant & Equipment|13.7"
ENVIVA_EDITS = ([f"claims[{i}].priority:2" for i in range(1, 6)] + [f"claims[{i}].priority:3" for i in (6, 7)]
                + [f"claims[{i}].priority:4" for i in range(8, 21)])

SHOTS = [
    ("01_app_full_ww_reconciled", {"case": "ww_international", "run": WW}, 4700,
     "Whole app after a live WW International extraction: RECONCILED"),
    ("02_ww_extraction_usage_activity", {"case": "ww_international", "run": WW,
     "only": "usage-card,activity-card,safety-card,recon-card"}, 1650,
     "WW: tokens, cost, runtime, agent activity, filed vs recalculated recoveries"),
    ("03_wolfspeed_stress_baseline", {"case": "wolfspeed", "run": WOLF, "scenario": "1", "only": "stress-card"}, 1450,
     "Wolfspeed High case on filed assumptions: unsecured classes are the fulcrum"),
    ("04_wolfspeed_stress_ppe_13_7", {"case": "wolfspeed", "run": WOLF, "scenario": "1", "o": PPE, "only": "stress-card"}, 1450,
     "Wolfspeed High case with PP&E at 13.7% of book: fulcrum moves to the Senior Secured Notes"),
    ("05_enviva_needs_review", {"case": "enviva", "run": ENV, "only": "activity-card,safety-card,recon-card"}, 2000,
     "Enviva: NEEDS REVIEW, grounded and cross-footed but not reproducible by one consolidated waterfall"),
    ("06_enviva_pending_corrections", {"case": "enviva", "run": ENV, "only": "table-card", "edit": ENVIVA_EDITS,
     "by": "Demo reviewer"}, 3400, "Enviva: a reviewer edits claim priorities; corrections pending, not applied yet"),
    ("07_enviva_after_correction", {"case": "enviva", "run": ENV_REVIEWED, "only": "activity-card,recon-card"}, 1900,
     "Enviva after 20 human corrections: provenance kept, engine rerun, still NEEDS REVIEW"),
    ("08_safety_planted_instruction", {"case": "ww_international", "run": INJECTION,
     "only": "usage-card,activity-card,safety-card"}, 1150,
     "Safety test: planted hidden + visible instruction; hidden one withheld, visible one flagged; still 108/108"),
    ("09_dean_foods_needs_review", {"case": "dean_foods", "run": DEAN, "only": "usage-card,activity-card,safety-card,recon-card"}, 2100,
     "Dean Foods live run (public Epiq PDF): grounded, totals add up, NEEDS REVIEW (43-entity filing), layout warning on p. 5"),
    ("10_dean_foods_stress_lc", {"case": "dean_foods", "run": DEAN, "scenario": "0", "o": "LC Recoveries [3]|39.6", "only": "stress-card"}, 1450,
     "Dean Foods Low case, LC recoveries 27.7% -> 39.6%: admin paid in full, fulcrum moves to unsecured (illustrative; base does not reconcile)"),
]


def browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("No Edge or Chrome found for headless screenshots.")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exe, manifest = browser(), []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        for k, (name, query, height, caption) in enumerate(SHOTS):
            url = BASE + "?" + urlencode(query, doseq=True)
            png = OUT / f"{name}.png"
            png.unlink(missing_ok=True)
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={tmp}/p{k}",
                            f"--window-size=1440,{height}", "--virtual-time-budget=12000", f"--screenshot={png}", url],
                           check=False, capture_output=True, timeout=120)
            for _ in range(120):  # Edge's launcher can return before the image is written
                if png.exists() and png.stat().st_size > 10_000:
                    time.sleep(0.5)
                    break
                time.sleep(0.5)
            ok = png.exists() and png.stat().st_size > 10_000
            manifest.append({"file": png.relative_to(ROOT).as_posix(), "url": url, "caption": caption, "ok": ok,
                             "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            print(("ok  " if ok else "FAIL"), png.name)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0 if all(m["ok"] for m in manifest) else 1


if __name__ == "__main__":
    sys.exit(main())
