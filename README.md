# Credit Recovery Copilot: liquidation-analysis stress-tester

Reads the Chapter 7 liquidation analysis that a Chapter 11 debtor files with its disclosure statement (the
"best interests" exhibit), recomputes the recovery waterfall in code, checks it against the debtor's own numbers,
and lets an analyst stress the assumptions to see which creditor class is the fulcrum.

**Status:** working app (FastAPI + one static page), extractor agent (gpt-6-luna), deterministic engine, safety
checks and human-correction fallback, all tested. Evidence screenshots: `docs/screenshots/` (rebuild with
`python scripts/capture_screenshots.py` while the server runs).

## Quick start (about 5 minutes)

Requires Python 3.12+ (tested on 3.14) and internet access for the model call.

1. Clone and enter the repository:

   ```bash
   git clone https://github.com/tugrul-ozsoy/credit-recovery-copilot.git
   cd credit-recovery-copilot
   ```

2. Create a virtual environment and install (about 2-3 minutes):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Provide the key. The app reads `PORTKEY_API_KEY` from `.env` in this folder first, then from `.env` in the folder
   above it (the course's `submissions/.env` layout works as is). See `.env.example`. Only `PORTKEY_API_KEY` is used,
   with model `gpt-6-luna`.

4. Start the app and open http://127.0.0.1:8000:

   ```bash
   python -m app.server
   ```

5. Pick a filing (WW International is the quickest), press **Run AI extraction** (one gpt-6-luna call, about
   10-20 s, about $0.002), or open a saved run. Then move the stress-test sliders and, if a run needs review, correct
   fields with your name. The four bundled filings are public and need no download.

## Extract a filing from the command line (live AI call)

```bash
python -m app.extract data/cases/ww_international/source.htm          # one extraction -> output/extractions/
python scripts/extract_eval.py --run ww_international                   # extract, then score vs case.json
python scripts/review_extraction.py output/extractions/<file>.json      # fields, provenance, warnings
python scripts/review_extraction.py <file>.json --set "assets[1].recovery_value[0]=5427" --by "Your Name"
python scripts/injection_live_test.py                                   # extraction with a planted instruction
```

Each run appends tokens and cost to `output/usage_log.json` and the full exchange to `output/audit_trail.json`.

## Check the engine against the filings (no AI calls)

```bash
python -m pytest -q                     # 30 tests, no AI calls
python scripts/reconcile_cases.py       # filed vs recomputed recoveries -> output/reconciliation.json
```

| Case | Waterfall | Result |
|---|---|---|
| WW International (2025) | consolidated | ties: secured 7.3 / 8.8 / 10.9% vs filed 7 / 9 / 11% (filed rounded) |
| Wolfspeed (2025) | consolidated | ties: senior secured 79.0 / 100%, unsecured 0 / 3.8% |
| Enviva (2024) | legal-entity | does not tie, as expected (negative control: one consolidated waterfall cannot reproduce entity-level recoveries) |
| Dean Foods (2021, PDF from the claims agent Epiq) | 43 legal entities, aggregated | no answer key; the live run is grounded and cross-foots but is flagged NEEDS REVIEW (see `docs/pilot/dean_foods_live_test.json`) |

## Layout

| Path | What it is |
|---|---|
| `engine/schema.py` | Typed liquidation analysis (assets, adjustments, claim classes by priority) and case loader |
| `engine/waterfall.py` | Absolute-priority waterfall, stress overrides, fulcrum, cross-foot and reconciliation checks |
| `app/llm.py` | Portkey / gpt-6-luna model, `.env` lookup, token and cost accounting (from HW6) |
| `app/sanitize.py` | Hidden-text sanitizer, instruction-phrase flags, untrusted-data envelope, number checks (from HW6) |
| `app/logs.py` | Append-only JSON logs (from HW6) |
| `data/cases/` | Four public filings (three SEC EDGAR, one Epiq PDF); hand-keyed answer keys for three; see `data/cases/README.md` |
| `data/prices.json` | gpt-6-luna prices per 1M tokens |
| `scripts/research/` | The scripts used to find and extract the liquidation exhibits |
| `tests/` | Engine, extraction-safety and API tests (no AI calls) |
| `docs/screenshots/`, `docs/pilot/` | Evidence screenshots of real runs; Dean Foods live test and user-trial record |
| `report.html`, `scripts/build_report.py` | Final report (self-contained); rebuilt from the logs with `python scripts/build_report.py` |
| `slides.html`, `scripts/build_slides.py` | 10-slide reveal.js deck (reveal.js from a CDN, images embedded); `python scripts/build_slides.py` |
| `docs/fresh_clone/` | Fresh-clone test record: clone to reconciled live run in about 4 minutes with `.env` one folder up |

Not investment advice. A Chapter 7 liquidation analysis is the debtor's hypothetical floor for the best-interests
test, not a forecast of market or plan recoveries.
