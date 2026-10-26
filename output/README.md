# Run logs (real evidence)

Every file here was written by the app during real runs. Nothing was edited by hand.

| File | What it holds |
|---|---|
| `usage_log.json` | One entry per live extraction: model requested and reported, every API request's raw token usage, cost from `data/prices.json` |
| `audit_trail.json` | One entry per live extraction: what was sent to the model (the sanitized exhibit text), every structured answer and retry message, safety findings, result |
| `extractions/<case>-<run_id>.json` | The extraction, provenance of every field, and the code's assessment (grounding, cross-foot, reconciliation). `-reviewed-N` files add human corrections |
| `corrections.json` | Every human correction: who, which field, old and new value, status before and after |
| `extraction_eval.json` | Field-level scores against the hand-keyed answer keys (`scripts/extract_eval.py`) |
| `injection_test.json` | The live run on a filing with a planted instruction (`scripts/injection_live_test.py`) |
| `reconciliation.json` | Engine vs filed recoveries on the hand-keyed answer keys (`scripts/reconcile_cases.py`) |

**Privacy normalization (2026-10-26).** Some early log entries recorded the absolute path of the analysed file on
the author's laptop, which included local folder names. `scripts/normalize_log_paths.py` replaced those path strings
with repo-relative paths (or `<temp folder>/...` for the temporary copy used in the injection test). No other field
changed: run ids, timestamps, token counts, costs, extracted values, document text and SHA-256 hashes are as
recorded. New runs log repo-relative paths directly (`app/extract.py`).

The source filings are public, so the document text in these logs is public too. No API key is ever logged.
