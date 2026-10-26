# User trial record: Dean Foods (credit recovery analysis)

Recorded 2026-10-26. This file separates what a user reported from what was measured in this project.

## A. Earlier external user trial (user-reported, not verified)

- **Who:** an Asset Management student (identity withheld). The person's role in this solo course project is
  limited to independent user testing and feedback.
- **What was reported:** the project owner reports that the student tried the application for a Dean Foods
  credit-recovery analysis on a different computer.
- **Evidence on file:** none. There are no screenshots, logs, run IDs, timings, ratings or written feedback from
  that session.
- **Open question:** the application had not been committed or published at the time of the reported session, and
  the Dean Foods filing was first added to this codebase at about 01:20 ET on 2026-10-26. It is therefore not
  established which version of the tool was used, or how. It must be confirmed with the user before being cited as a
  trial of this application.
- **Naming:** no permission to identify the user is recorded, so no identifying details are kept here.

## B. Reproduced technical test (measured in this project)

Not a second user trial: this is the project's own live run of the same public filing, on the project owner's
laptop, through the real browser interface. Full record: `docs/pilot/dean_foods_live_test.json`.

| Item | Measured |
|---|---|
| Source | Dean Foods / Southern Foods Group, Appendix B - Liquidation Analysis (public Epiq download, 51 pages, USD millions) |
| Run | `dean_foods-59494a252416`, executed 2026-10-26 05:22:37 UTC |
| Model call | gpt-6-luna (API reported `gpt-6-luna-global`), 1 request, 1 attempt, 21.66 s |
| Tokens / cost | 4,972 input (0 cached), 2,888 output (1,584 reasoning), $0.00206 |
| Extracted | 7 asset lines, 3 deductions, 11 claim classes, 2 scenarios (Low, High); 170 extracted fields |
| Grounding | every number found in the row the agent cited: yes |
| Filing arithmetic | totals cross-foot within rounding: yes |
| Reconciliation | **NEEDS REVIEW**: one consolidated waterfall does not reproduce the filed class recoveries (largest gap 77.6 points); the filing aggregates 43 Debtor-entity waterfalls |
| Safety | p. 5 layout could not be resolved by the PDF visibility rules (embedded spreadsheet); plain text sent and flagged for review |
| Scenario | Low case, LC Recoveries 27.7% -> 39.6%: net distributable value $198.0m -> $224.5m (engine), Administrative Claims paid in full, fulcrum moves to the unsecured classes (illustrative, because the base case does not reconcile) |

## C. Unverified or missing

- Any quote, opinion, usability rating or satisfaction level from the user: none recorded.
- Time taken by the user, with or without the tool: not measured.
- The other computer's setup, the data used, and the results seen: not recorded.
- Manual baseline for the same task: not measured in this project, so **no time saving is claimed**.
