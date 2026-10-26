"""Deterministic recovery waterfall. No AI: every number the app shows is computed here.

    gross proceeds  = sum of asset recoveries (the filed $ per line, or book value x an overridden %)
    net value (NDV) = gross proceeds + signed adjustments (wind-down costs, trustee fees, carve-outs, inflows)
    distribution    = absolute priority: classes are paid in `priority` order; classes with the same priority
                      share pro rata; whatever is left after the last class is residual value (to equity).

crossfoot()  checks the filing's own arithmetic (assets add to gross, gross + adjustments = NDV).
reconcile()  recomputes every filed scenario and compares each class's recovery with what the debtor filed.
             A case that does not tie is reported, not forced: e.g. Enviva used legal-entity waterfalls that a
             single consolidated waterfall cannot reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby

from engine.schema import ClaimClass, LiquidationAnalysis

EPS = 1e-9


@dataclass(frozen=True)
class ClassResult:
    label: str
    priority: int
    claim: float
    recovered: float
    pct: float  # recovered / claim x 100; 0 for a zero claim


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    gross_proceeds: float
    adjustments: float
    net_distributable_value: float
    classes: list[ClassResult]
    residual: float  # value left after every class
    fulcrum: list[str]  # the most senior class(es) not paid in full; empty if every class is paid in full


def distribute(ndv: float, claims: list[ClaimClass], amounts: dict[str, float] | None = None
               ) -> tuple[list[ClassResult], float]:
    """Pay `ndv` down the claims by priority, pro rata within a priority. Returns (results in input order, residual).
    `amounts` overrides claim sizes by label (for stress tests)."""
    amounts = amounts or {}
    remaining = max(ndv, 0.0)
    paid: dict[str, ClassResult] = {}
    ordered = sorted(claims, key=lambda c: c.priority)
    for priority, tier in groupby(ordered, key=lambda c: c.priority):
        tier = list(tier)
        sizes = {c.label: max(amounts.get(c.label, c.amount), 0.0) for c in tier}
        total = sum(sizes.values())
        pay = min(remaining, total)
        remaining -= pay
        for c in tier:
            got = pay * sizes[c.label] / total if total > EPS else 0.0
            pct = 100.0 * got / sizes[c.label] if sizes[c.label] > EPS else 0.0
            paid[c.label] = ClassResult(c.label, priority, sizes[c.label], got, pct)
    return [paid[c.label] for c in claims], remaining


def gross_proceeds(analysis: LiquidationAnalysis, i: int, pct_overrides: dict[str, float] | None = None) -> float:
    """Sum of asset recoveries in scenario i. An override replaces a line's filed $ with book value x pct / 100."""
    pct_overrides = pct_overrides or {}
    total = 0.0
    for a in analysis.assets:
        if a.label in pct_overrides:
            if a.book_value is None:
                raise ValueError(f"asset '{a.label}' has no book value, so a recovery % cannot be applied to it")
            total += a.book_value * pct_overrides[a.label] / 100.0
        else:
            total += a.recovery_value[i]
    return total


def _fulcrum(results: list[ClassResult]) -> list[str]:
    for priority, tier in groupby(sorted(results, key=lambda r: r.priority), key=lambda r: r.priority):
        tier = list(tier)
        if any(r.claim > EPS and r.recovered < r.claim - 1e-6 * r.claim for r in tier):
            return [r.label for r in tier]
    return []


def run_scenario(analysis: LiquidationAnalysis, i: int, pct_overrides: dict[str, float] | None = None,
                 adjustment_overrides: dict[str, float] | None = None,
                 claim_overrides: dict[str, float] | None = None) -> ScenarioResult:
    """Recompute scenario i, optionally with stressed asset recovery %, adjustment amounts or claim sizes."""
    adjustment_overrides = adjustment_overrides or {}
    gross = gross_proceeds(analysis, i, pct_overrides)
    adj = sum(adjustment_overrides.get(a.label, a.amounts[i]) for a in analysis.adjustments)
    ndv = gross + adj
    classes, residual = distribute(ndv, analysis.claims, claim_overrides)
    return ScenarioResult(analysis.scenarios[i], gross, adj, ndv, classes, residual, _fulcrum(classes))


# ---------- checks against the filing ----------


@dataclass(frozen=True)
class Check:
    scenario: str
    item: str
    computed: float
    filed: float
    tolerance: float

    @property
    def diff(self) -> float:
        return self.computed - self.filed

    @property
    def ok(self) -> bool:
        return abs(self.diff) <= self.tolerance


def crossfoot(analysis: LiquidationAnalysis) -> list[Check]:
    """The filing's own arithmetic, per scenario, allowing for each line being rounded to `rounding_step`."""
    step = analysis.rounding_step
    checks = []
    for i, name in enumerate(analysis.scenarios):
        gross = sum(a.recovery_value[i] for a in analysis.assets)
        checks.append(Check(name, "assets add to gross proceeds", gross, analysis.gross_proceeds_stated[i],
                            step * max(2, len(analysis.assets) / 2)))
        ndv = analysis.gross_proceeds_stated[i] + sum(a.amounts[i] for a in analysis.adjustments)
        checks.append(Check(name, "gross proceeds + adjustments = net distributable value", ndv,
                            analysis.net_distributable_value_stated[i], step * max(2, len(analysis.adjustments) / 2)))
    return checks


@dataclass
class Reconciliation:
    checks: list[Check] = field(default_factory=list)

    @property
    def ties(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def max_pct_gap(self) -> float:
        gaps = [abs(c.diff) for c in self.checks if c.item.endswith("recovery %")]
        return max(gaps, default=0.0)


def reconcile(analysis: LiquidationAnalysis, pct_tolerance: float = 0.5) -> Reconciliation:
    """Recompute every filed scenario from the filed asset values and adjustments, then compare each class's
    recovery % (within `pct_tolerance` points, enough for filings that round to whole percents) and recovery $
    (within a few rounding steps) with what the debtor filed."""
    step = analysis.rounding_step
    rec = Reconciliation()
    for i, name in enumerate(analysis.scenarios):
        result = run_scenario(analysis, i)
        for claim, r in zip(analysis.claims, result.classes):
            filed_pct = claim.filed_recovery_pct[i]
            if filed_pct is not None:
                rec.checks.append(Check(name, f"{claim.label}: recovery %", r.pct, filed_pct, pct_tolerance))
            if claim.filed_recovery_value and claim.filed_recovery_value[i] is not None:
                rec.checks.append(Check(name, f"{claim.label}: recovery $", r.recovered, claim.filed_recovery_value[i],
                                        3 * step + 0.0005 * claim.amount))
    return rec
