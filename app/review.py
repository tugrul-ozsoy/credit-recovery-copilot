"""Fallback when an extraction does not reconcile: a person confirms or corrects fields, then the engine reruns.

Every value carries where it came from:
    extracted            copied from the filing by the extractor agent
    corrected            changed by a named person (old value kept in the corrections log)
    computed (code)      set by code from other values (rounding_step)
    computed (engine)    everything in assessment.computed_by_engine (NDV, recoveries, fulcrum, reconciliation)

Nothing here edits a value silently: a correction needs a field path, a new value and a person's name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.checks import assess
from app.llm import ROOT
from app.logs import append_json, utc_now
from engine.schema import LiquidationAnalysis

CORRECTIONS_LOG = ROOT / "output" / "corrections.json"
_STEP = re.compile(r"([A-Za-z_]+)|\[(\d+)\]")


def _parse(path: str) -> list[str | int]:
    parts = [m.group(1) if m.group(1) else int(m.group(2)) for m in _STEP.finditer(path)]
    if not parts or "".join(str(p) for p in parts) != re.sub(r"[.\[\]]", "", path):
        raise ValueError(f"bad field path {path!r}; use e.g. assets[1].recovery_value[0]")
    return parts


def get_field(data: dict, path: str):
    node = data
    for p in _parse(path):
        node = node[p]
    return node


def set_field(data: dict, path: str, value) -> object:
    parts = _parse(path)
    node = data
    for p in parts[:-1]:
        node = node[p]
    old = node[parts[-1]]
    node[parts[-1]] = value
    return old


def review_rows(record: dict) -> list[dict]:
    """Interface data for the confirmation screen: one row per field, with value, provenance and warnings."""
    analysis, provenance = record["result"]["analysis"], record["result"]["provenance"]
    warnings = record["result"]["assessment"]["warnings"]
    rows = []
    for path, source in provenance.items():
        label = None
        m = re.match(r"(assets|adjustments|claims)\[(\d+)\]", path)
        if m:
            label = analysis[m.group(1)][int(m.group(2))]["label"]
        flagged = [w["message"] for w in warnings if label and f"'{label}'" in w["message"]]
        rows.append({"field": path, "row_label": label, "value": get_field(analysis, path), "provenance": source,
                     "warnings": flagged})
    return rows


def apply_corrections(record: dict, corrections: list[tuple[str, object]], by: str) -> dict:
    """Return a new record with the corrections applied, provenance updated, and the engine rerun."""
    by = (by or "").strip()
    if not by:
        raise ValueError("a correction needs the name of the person making it")
    if not corrections:
        raise ValueError("no corrections given")
    analysis = json.loads(json.dumps(record["result"]["analysis"]))
    provenance = dict(record["result"]["provenance"])
    log = []
    for path, value in corrections:
        if path == "rounding_step":
            raise ValueError("rounding_step is computed by code and cannot be corrected")
        old = set_field(analysis, path, value)
        provenance[path] = f"corrected by {by}"
        log.append({"field": path, "old": old, "new": value})
    validated = LiquidationAnalysis.model_validate(analysis)  # a correction cannot break the schema either
    exhibit_text = record.get("exhibit_text")
    safety = record.get("safety", {})
    assessment = assess(validated, exhibit_text, safety.get("injection_indicators"), len(safety.get("quarantined", [])),
                        safety.get("layout_warnings"))
    entry = {"timestamp_utc": utc_now(), "run_id": record["run_id"], "case": record["case"], "by": by,
             "changes": log, "status_before": record["result"]["assessment"]["status"],
             "status_after": assessment["status"]}
    append_json(CORRECTIONS_LOG, entry)
    reviewed = {**record, "result": {"analysis": validated.model_dump(mode="json"), "provenance": provenance,
                                     "assessment": assessment},
                "corrections": [*record.get("corrections", []), entry]}
    return reviewed


def save(record: dict) -> Path:
    n = len(record.get("corrections", []))
    path = ROOT / "output" / "extractions" / f"{record['case']}-{record['run_id']}-reviewed-{n}.json"
    while path.exists():  # a second review of the same run must not replace the first one's evidence
        n += 1
        path = path.with_name(f"{record['case']}-{record['run_id']}-reviewed-{n}.json")
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
