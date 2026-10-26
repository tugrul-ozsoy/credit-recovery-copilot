# Bundled cases

Public SEC filings only. No private, team or competition material is used anywhere in this project.

| Folder | Filing | Exhibit | Waterfall |
|---|---|---|---|
| `ww_international/` | [WW International 8-K, EX-99.1](https://www.sec.gov/Archives/edgar/data/105319/000119312525114307/d934787dex991.htm): Disclosure Statement for the Joint Prepackaged Plan, dated as of May 6, 2025 | Exhibit B | consolidated |
| `wolfspeed/` | [Wolfspeed 8-K, EX-99.1](https://www.sec.gov/Archives/edgar/data/895419/000119312525153145/d755867dex991.htm): Solicitation Version Disclosure Statement, dated June 27, 2025 | Exhibit D | consolidated |
| `enviva/` | [Enviva 8-K, EX-99.2](https://www.sec.gov/Archives/edgar/data/1592057/000110465924096073/tm2423134d1_ex99-2.htm): Disclosure Statement for the Joint Chapter 11 Plan, dated August 30, 2024 | Exhibit E | legal-entity (negative control) |

Each folder holds:

| File | What it is |
|---|---|
| `source.htm` | The filing as downloaded from EDGAR (SHA-256 in `case.json`) |
| `exhibit.txt` | The liquidation-analysis exhibit as text (`scripts/research/html2text.py`, page sections cut with `pages.py`) |
| `summary_table.txt` | Just the summary waterfall table from the exhibit |
| `case.json` | Ground truth: the summary table hand-keyed into `engine/schema.py`'s `CaseFile`, with notes on every judgment call |

How the ground truth was checked: every non-zero number in each `case.json` row was matched against the same row
of `summary_table.txt`, spot-checked in `source.htm`, and the filing's own totals cross-foot within rounding
(`tests/test_engine.py::test_filing_arithmetic_crossfoots`).
