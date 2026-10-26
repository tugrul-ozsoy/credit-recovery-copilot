"""Typed form of a filed Chapter 7 liquidation analysis (the "best interests" exhibit to a disclosure statement).

The same model is the hand-keyed ground truth in data/cases/<case>/case.json and, later, the extractor agent's
structured output. All money is in the table's own units (see `units`); percentages are plain numbers (40.0 = 40%).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AssetLine(BaseModel):
    label: str
    book_value: float | None = Field(default=None, description="Estimated net book value, in the table's units")
    recovery_pct: list[float | None] = Field(description="Recovery as % of book value, one per scenario (40.0 = 40%)")
    recovery_value: list[float] = Field(description="Recovered amount per scenario, in the table's units; a dash is 0")
    source_text: str | None = Field(default=None, description="The table row copied exactly from the document text (provenance)")


class Adjustment(BaseModel):
    label: str
    amounts: list[float] = Field(description="Signed amount per scenario: costs negative, inflows positive")
    source_text: str | None = Field(default=None, description="The table row copied exactly from the document text (provenance)")


class ClaimClass(BaseModel):
    label: str
    priority: int = Field(ge=1, description="Payment order: 1 is paid first; classes with the same number share pro rata")
    amount: float = Field(ge=0, description="Allowed claim; the low end if the filing gives a range")
    amount_high: float | None = Field(default=None, ge=0, description="High end, when the filing gives a range")
    filed_recovery_pct: list[float | None] = Field(description="Filed recovery % per scenario; a dash is 0")
    filed_recovery_value: list[float | None] = Field(default_factory=list, description="Filed recovery $ per scenario")
    source_text: str | None = Field(default=None, description="The table row copied exactly from the document text (provenance)")


class LiquidationAnalysis(BaseModel):
    case_name: str
    units: Literal["USD thousands", "USD millions"]
    rounding_step: float = Field(default=1.0, gt=0, description="Smallest unit the table shows (1 for $000s, 0.1 for $mm.0)")
    scenarios: list[str] = Field(min_length=1)
    assets: list[AssetLine]
    gross_proceeds_stated: list[float]
    adjustments: list[Adjustment]
    net_distributable_value_stated: list[float]
    claims: list[ClaimClass]
    totals_source_text: list[str] = Field(default_factory=list, description="The total asset recoveries row and the net distributable value row, copied exactly from the document text (provenance)")

    @model_validator(mode="after")
    def _one_value_per_scenario(self) -> LiquidationAnalysis:
        n = len(self.scenarios)
        rows = [("gross_proceeds_stated", self.gross_proceeds_stated),
                ("net_distributable_value_stated", self.net_distributable_value_stated)]
        rows += [(f"asset '{a.label}' recovery_pct", a.recovery_pct) for a in self.assets]
        rows += [(f"asset '{a.label}' recovery_value", a.recovery_value) for a in self.assets]
        rows += [(f"adjustment '{a.label}'", a.amounts) for a in self.adjustments]
        rows += [(f"claim '{c.label}' filed_recovery_pct", c.filed_recovery_pct) for c in self.claims]
        rows += [(f"claim '{c.label}' filed_recovery_value", c.filed_recovery_value) for c in self.claims
                 if c.filed_recovery_value]
        bad = [f"{name} has {len(values)} values" for name, values in rows if len(values) != n]
        if bad:
            raise ValueError(f"every per-scenario list needs {n} values ({', '.join(self.scenarios)}): " + "; ".join(bad))
        return self


class SourceInfo(BaseModel):
    company: str
    filing: str
    exhibit: str
    filed_date: str
    url: str
    source_file: str = "source.htm"
    source_sha256: str


class CaseFile(BaseModel):
    """One bundled case: where it came from, the keyed table, and what kind of waterfall the debtor used."""

    slug: str
    source: SourceInfo
    structure: Literal["consolidated", "entity_level", "collateral_pools"] = Field(
        description="consolidated: one waterfall for all debtors; entity_level: separate waterfalls per legal "
                    "entity, aggregated; collateral_pools: separate waterfalls per collateral pool")
    keyed_by: str
    notes: list[str] = Field(default_factory=list)
    analysis: LiquidationAnalysis | None = Field(default=None, description="Hand-keyed answer key; None if not keyed")


CASES_DIR = Path(__file__).resolve().parents[1] / "data" / "cases"


def load_case(slug: str) -> CaseFile:
    return CaseFile.model_validate(json.loads((CASES_DIR / slug / "case.json").read_text(encoding="utf-8")))


def case_slugs() -> list[str]:
    return sorted(p.parent.name for p in CASES_DIR.glob("*/case.json"))


def keyed_slugs() -> list[str]:
    """Cases with a hand-keyed answer key (used by the engine reproduction tests)."""
    return [s for s in case_slugs() if load_case(s).analysis is not None]


def source_path(slug: str) -> Path:
    case = load_case(slug)
    return CASES_DIR / slug / case.source.source_file
