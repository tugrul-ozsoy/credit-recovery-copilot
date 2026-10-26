"""Test 1: the deterministic waterfall reproduces the debtors' own filed recoveries (no AI, no network).

    WW International  consolidated waterfall, rounded % -> must tie
    Wolfspeed         consolidated waterfall            -> must tie
    Enviva            legal-entity waterfalls           -> must NOT tie (negative control: the check can fail)
"""

import pytest
from pydantic import ValidationError

from engine.schema import ClaimClass, LiquidationAnalysis, keyed_slugs, load_case
from engine.waterfall import crossfoot, distribute, reconcile, run_scenario


def claim(label, priority, amount):
    return ClaimClass(label=label, priority=priority, amount=amount, filed_recovery_pct=[None])


# ---------- the engine itself ----------


def test_priority_then_pro_rata():
    claims = [claim("senior", 1, 100), claim("junior a", 2, 60), claim("junior b", 2, 40)]
    results, residual = distribute(150, claims)
    assert [round(r.recovered, 6) for r in results] == [100, 30, 20]
    assert [round(r.pct, 6) for r in results] == [100, 50, 50]
    assert residual == 0


def test_residual_and_no_negative_value():
    claims = [claim("only", 1, 100)]
    results, residual = distribute(130, claims)
    assert results[0].pct == 100 and residual == pytest.approx(30)
    results, residual = distribute(-5, claims)
    assert results[0].recovered == 0 and residual == 0


def test_results_keep_input_order_and_zero_claims():
    claims = [claim("junior", 2, 50), claim("senior", 1, 50), claim("empty", 1, 0)]
    results, _ = distribute(75, claims)
    assert [r.label for r in results] == ["junior", "senior", "empty"]
    assert [r.recovered for r in results] == [25, 50, 0]


def test_schema_rejects_missing_scenario_values():
    case = load_case("ww_international").analysis.model_dump()
    case["claims"][0]["filed_recovery_pct"] = [7, 9]  # three scenarios, two values
    with pytest.raises(ValidationError, match="needs 3 values"):
        LiquidationAnalysis.model_validate(case)


# ---------- the bundled filings ----------


@pytest.mark.parametrize("slug", keyed_slugs())
def test_filing_arithmetic_crossfoots(slug):
    """Each filing's own table adds up (assets to gross, gross + adjustments to NDV), within rounding."""
    failures = [c for c in crossfoot(load_case(slug).analysis) if not c.ok]
    assert not failures, failures


@pytest.mark.parametrize("slug", ["ww_international", "wolfspeed"])
def test_consolidated_filings_reconcile(slug):
    rec = reconcile(load_case(slug).analysis)
    assert rec.ties, "\n".join(f"{c.scenario} {c.item}: computed {c.computed:,.2f} vs filed {c.filed:,.2f}"
                               for c in rec.failures)


def test_ww_secured_recoveries():
    a = load_case("ww_international").analysis
    secured = [run_scenario(a, i).classes[0].pct for i in range(3)]
    assert [round(p) for p in secured] == [7, 9, 11]  # filed, rounded to whole percents
    assert secured == pytest.approx([7.34, 8.83, 10.94], abs=0.01)


def test_wolfspeed_fulcrum_moves_when_ppe_recovery_falls():
    a = load_case("wolfspeed").analysis
    high = run_scenario(a, 1)
    assert high.classes[-1].pct == pytest.approx(3.77, abs=0.01)  # filed 3.8%
    assert "General Unsecured Claims" in high.fulcrum
    # Stress: PP&E recovers at the Low-case 13.7% inside the High case -> the secured notes become the fulcrum.
    stressed = run_scenario(a, 1, pct_overrides={"Property, Plant & Equipment": 13.7})
    assert stressed.fulcrum == ["Senior Secured Notes"]
    assert stressed.classes[0].pct == pytest.approx(83.57, abs=0.05)
    assert all(r.recovered == 0 for r in stressed.classes[1:])


def test_enviva_negative_control_does_not_tie():
    a = load_case("enviva").analysis
    rec = reconcile(a)
    assert not rec.ties
    assert rec.max_pct_gap > 20  # e.g. DIP: consolidated waterfall gives ~46%, filed 18.0%
    low = run_scenario(a, 0)
    # The value is all there (secured classes absorb the whole NDV, as filed); only its split by class differs.
    secured = sum(r.recovered for r in low.classes if r.priority <= 2)
    assert secured == pytest.approx(low.net_distributable_value)
    assert low.net_distributable_value == pytest.approx(a.net_distributable_value_stated[0], abs=0.2)
