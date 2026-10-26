"""One-off privacy fix for published evidence: replace absolute local paths in logs with repo-relative ones.

    python scripts/normalize_log_paths.py          # rewrites matching JSON files in output/, docs/, tests/fixtures/

Only path strings change. Run ids, timestamps, token counts, costs, extracted values, document text and SHA-256
hashes are untouched. Applied once on 2026-10-26 (see output/README.md).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = [
    (re.compile(r"[A-Za-z]:/Users/[^/\"]+/code/credit-recovery-copilot/"), ""),
    (re.compile(r"[A-Za-z]:/Users/[^/\"]+/grader_test/submissions/"), "<fresh-clone folder>/submissions/"),
    (re.compile(r"[A-Za-z]:/Users/[^\"]*?/Temp/[^\"]*?/(ww_with_injection\.htm)"), r"<temp folder>/\1"),
    (re.compile(r"[A-Za-z]:/Users/[^\"\s]+"), "<local path>"),
]


def main() -> int:
    changed = 0
    for folder in ("output", "docs", "tests/fixtures"):
        for f in (ROOT / folder).rglob("*.json"):
            text = f.read_text(encoding="utf-8")
            new = text
            for pattern, repl in RULES:
                new = pattern.sub(repl, new)
            if new != text:
                f.write_text(new, encoding="utf-8")
                changed += 1
                print("normalized", f.relative_to(ROOT).as_posix())
    print(f"{changed} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
