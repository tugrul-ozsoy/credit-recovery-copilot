"""Score an extraction against the hand-keyed reference in data/cases/<case>/case.json (the model never sees it).

Used by scripts/extract_eval.py and by the app's "reference check" panel.
"""

from __future__ import annotations

import difflib
import re

from engine.schema import LiquidationAnalysis


def _key(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.casefold())


def _match(gt_rows, ex_rows) -> tuple[dict[int, int], list[int]]:
    """Pair each ground-truth row with the most similar extracted label (ratio >= 0.6), one-to-one."""
    pairs, used = {}, set()
    for i, g in enumerate(gt_rows):
        scored = sorted(((difflib.SequenceMatcher(None, _key(g.label), _key(e.label)).ratio(), j)
                         for j, e in enumerate(ex_rows) if j not in used), reverse=True)
        if scored and scored[0][0] >= 0.6:
            pairs[i] = scored[0][1]
            used.add(scored[0][1])
    return pairs, [j for j in range(len(ex_rows)) if j not in used]


def _same(a, b, tol=1e-6) -> bool:
    if a is None or b is None:
        return (a or 0) == (b or 0)
    return abs(float(a) - float(b)) <= tol


def score(gt: LiquidationAnalysis, ex: LiquidationAnalysis) -> dict:
    fields, wrong, missing = 0, [], []

    def check(name, g, e):
        nonlocal fields
        fields += 1
        if not _same(g, e):
            wrong.append({"field": name, "expected": g, "extracted": e})

    fields += 2
    if gt.units != ex.units:
        wrong.append({"field": "units", "expected": gt.units, "extracted": ex.units})
    if [s.casefold() for s in gt.scenarios] != [s.casefold() for s in ex.scenarios]:
        wrong.append({"field": "scenarios", "expected": gt.scenarios, "extracted": ex.scenarios})
    n = len(gt.scenarios)
    same_n = len(ex.scenarios) == n

    def per_scenario(name, g_list, e_list):
        for i in range(n):
            check(f"{name}[{gt.scenarios[i]}]", g_list[i], e_list[i] if same_n and i < len(e_list) else None)

    per_scenario("gross_proceeds_stated", gt.gross_proceeds_stated, ex.gross_proceeds_stated)
    per_scenario("net_distributable_value_stated", gt.net_distributable_value_stated, ex.net_distributable_value_stated)

    sections = {}
    for section, g_rows, e_rows, cols in (
        ("assets", gt.assets, ex.assets, ("book_value", "recovery_pct", "recovery_value")),
        ("adjustments", gt.adjustments, ex.adjustments, ("amounts",)),
        ("claims", gt.claims, ex.claims, ("amount", "amount_high", "filed_recovery_pct", "filed_recovery_value")),
    ):
        pairs, extra = _match(g_rows, e_rows)
        sections[section] = {"expected_rows": len(g_rows), "matched_rows": len(pairs),
                             "extra_rows": [e_rows[j].label for j in extra]}
        for i, g in enumerate(g_rows):
            e = e_rows[pairs[i]] if i in pairs else None
            for col in cols:
                gv = getattr(g, col)
                if col == "amount_high" and gv is None:
                    continue
                ev = getattr(e, col) if e is not None else None
                if isinstance(gv, list):
                    if e is None:
                        fields += n
                        missing += [f"{section}.{g.label}.{col}[{s}]" for s in gt.scenarios]
                    else:
                        per_scenario(f"{section}.{g.label}.{col}", gv, ev)
                else:
                    if e is None:
                        fields += 1
                        missing.append(f"{section}.{g.label}.{col}")
                    else:
                        check(f"{section}.{g.label}.{col}", gv, ev)
        if section == "claims":  # priority: same payment order and same pari passu groups as the filing
            for i, g in enumerate(g_rows):
                fields += 1
                if i not in pairs:
                    missing.append(f"claims.{g.label}.priority")
                    continue
                e = e_rows[pairs[i]]
                ok = all((g.priority > g2.priority) == (e.priority > e_rows[pairs[k]].priority)
                         and (g.priority == g2.priority) == (e.priority == e_rows[pairs[k]].priority)
                         for k, g2 in enumerate(g_rows) if k in pairs and k != i)
                if not ok:
                    wrong.append({"field": f"claims.{g.label}.priority (relative order)", "expected": g.priority,
                                  "extracted": e.priority})
    correct = fields - len(wrong) - len(missing)
    return {"fields_scored": fields, "correct": correct, "accuracy": round(correct / fields, 4) if fields else 0,
            "wrong": wrong, "missing": missing, "rows": sections}
