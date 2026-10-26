"""Code checks on an extracted (or user-corrected) liquidation analysis. No AI.

grounding_problems  every number in a row must be printed in that row's source_text, and the source_text must be
                    in the exhibit the model was given (HW6 ground() idea, applied row by row).
assess              grounding + the filing's own arithmetic (crossfoot) + recomputed vs filed recoveries
                    (reconcile) + safety flags -> 'reconciled' or 'needs_review', with visible warnings.
"""

from __future__ import annotations

from decimal import Decimal

from app.sanitize import numbers_in_text
from engine.schema import LiquidationAnalysis
from engine.waterfall import crossfoot, reconcile, run_scenario

TOL = Decimal("0.0005")


def _flat(text: str) -> str:
    return " ".join(text.split()).casefold()


def _printed(value: float, numbers: set[Decimal]) -> bool:
    target = abs(Decimal(str(value)))
    return any(abs(n - target) <= TOL for n in numbers)


def grounding_problems(a: LiquidationAnalysis, exhibit_text: str) -> list[str]:
    """Numbers the model reported that its own cited row does not show, or cited rows not in the document."""
    flat_doc = _flat(exhibit_text)
    problems = []
    rows = [("asset", r.label, r.source_text, [r.book_value, *r.recovery_pct, *r.recovery_value]) for r in a.assets]
    rows += [("adjustment", r.label, r.source_text, list(r.amounts)) for r in a.adjustments]
    rows += [("claim", r.label, r.source_text,
              [r.amount, r.amount_high, *r.filed_recovery_pct, *r.filed_recovery_value]) for r in a.claims]
    for kind, label, source, values in rows:
        if not source:
            problems.append(f"{kind} '{label}': no source row given")
            continue
        if _flat(source) not in flat_doc:
            problems.append(f"{kind} '{label}': the cited source row is not in the document: '{source[:120]}'")
            continue
        printed = {abs(n) for n in numbers_in_text(source)}
        missing = [v for v in values if v not in (None, 0) and not _printed(v, printed)]
        if missing:
            problems.append(f"{kind} '{label}': {', '.join(f'{m:g}' for m in missing)} not printed in its source row "
                            f"'{source[:120]}'")
    doc_numbers = {abs(n) for n in numbers_in_text(exhibit_text)}
    for name, values in (("gross proceeds", a.gross_proceeds_stated), ("net distributable value", a.net_distributable_value_stated)):
        missing = [v for v in values if v != 0 and not _printed(v, doc_numbers)]
        if missing:
            problems.append(f"stated {name} {', '.join(f'{m:g}' for m in missing)} not printed in the document")
    return problems


def rounding_step_from_values(a: LiquidationAnalysis) -> float:
    """Computed by code from the extracted amounts: 0.1 if any amount has a decimal, else 1."""
    values = [v for r in a.assets for v in r.recovery_value] + [c.amount for c in a.claims]
    return 0.1 if any(abs(v - round(v)) > 1e-9 for v in values) else 1.0


def assess(a: LiquidationAnalysis, exhibit_text: str | None = None, injection_flags: list[str] | None = None,
           quarantined: int = 0, layout_warnings: list[str] | None = None) -> dict:
    """Everything the interface needs to show: status, warnings, and the engine's numbers (all computed by code)."""
    warnings = []
    grounding = grounding_problems(a, exhibit_text) if exhibit_text is not None else []
    warnings += [{"kind": "grounding", "severity": "error", "message": m} for m in grounding]
    foot = crossfoot(a)
    warnings += [{"kind": "crossfoot", "severity": "error",
                  "message": f"{c.scenario}: {c.item}: computed {c.computed:,.2f} vs stated {c.filed:,.2f}"} for c in foot if not c.ok]
    rec = reconcile(a)
    warnings += [{"kind": "reconciliation", "severity": "error",
                  "message": f"{c.scenario}: {c.item}: engine {c.computed:,.2f} vs filed {c.filed:,.2f}"} for c in rec.failures]
    warnings += [{"kind": "injection_flag", "severity": "warning", "message": f"visible text {f}"} for f in injection_flags or []]
    warnings += [{"kind": "layout", "severity": "warning", "message": m} for m in layout_warnings or []]
    if quarantined:
        warnings.append({"kind": "hidden_content", "severity": "warning",
                         "message": f"{quarantined} hidden item(s) withheld from the model"})
    computed = []
    for i in range(len(a.scenarios)):
        r = run_scenario(a, i)
        computed.append({"scenario": r.scenario, "gross_proceeds": r.gross_proceeds, "adjustments": r.adjustments,
                         "net_distributable_value": r.net_distributable_value, "residual": r.residual,
                         "fulcrum": r.fulcrum,
                         "classes": [{"label": c.label, "priority": c.priority, "claim": c.claim,
                                      "recovered": c.recovered, "pct": c.pct} for c in r.classes]})
    errors = [w for w in warnings if w["severity"] == "error"]
    return {
        "status": "reconciled" if not errors else "needs_review",
        "grounded": not grounding,
        "crossfoot_ok": all(c.ok for c in foot),
        "reconciles_with_filed": rec.ties,
        "max_pct_gap": round(rec.max_pct_gap, 3),
        "warnings": warnings,
        "computed_by_engine": computed,
    }
