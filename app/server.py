"""Web app: FastAPI over the extractor agent, the deterministic engine and the review fallback.

    python -m app.server            # then open http://127.0.0.1:8000

Every number the page shows comes from engine/waterfall.py (computed) or from an extraction file (extracted /
corrected). The browser only formats numbers. Live extractions are rate-limited and run one at a time.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.evaluate import score
from app.extract import EXTRACTIONS, USAGE_LOG, extract
from app.llm import ROOT
from app.locate import locate_exhibit
from app.logs import read_json_array
from app.review import apply_corrections, review_rows, save
from engine.schema import LiquidationAnalysis, case_slugs, load_case, source_path
from engine.waterfall import ScenarioResult, run_scenario

STATIC = ROOT / "static"
RUN_NAME = re.compile(r"^[a-z_]+-[0-9a-f]{12}(-reviewed-\d+)?$")
MAX_LIVE_RUNS_PER_HOUR = int(os.getenv("MAX_LIVE_RUNS_PER_HOUR", "20"))  # overspending guard

app = FastAPI(title="Credit Recovery Copilot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_run_lock = threading.Lock()
_recent_runs: list[float] = []


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


# ---------- cases and saved runs ----------


def _runs_for(slug: str) -> list[dict]:
    runs = []
    for f in sorted(EXTRACTIONS.glob(f"{slug}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({"name": f.stem, "run_id": r.get("run_id"), "timestamp_utc": r.get("timestamp_utc"),
                     "status": (r.get("result") or {}).get("assessment", {}).get("status", "error"),
                     "reviewed": "-reviewed-" in f.stem, "corrections": len(r.get("corrections", [])),
                     "injection_test": "ww_with_injection" in (r.get("source") or {}).get("file", "")})
    return runs


@app.get("/api/cases")
def cases() -> list[dict]:
    out = []
    order = {"ww_international": 0, "wolfspeed": 1, "enviva": 2, "dean_foods": 3}  # simple case first
    for slug in sorted(case_slugs(), key=lambda s: order.get(s, 9)):
        c = load_case(slug)
        out.append({"slug": slug, "company": c.source.company, "filing": c.source.filing, "exhibit": c.source.exhibit,
                    "filed_date": c.source.filed_date, "url": c.source.url, "saved_runs": _runs_for(slug)})
    return out


@app.get("/api/cases/{slug}/exhibit")
def exhibit(slug: str) -> dict:
    """Step 1 of a run (code only, ~1 s): find and sanitize the exhibit."""
    if slug not in case_slugs():
        raise HTTPException(404, "unknown case")
    e = locate_exhibit(source_path(slug))
    return {"heading": e.heading, "first_page": e.first_page, "last_page": e.last_page,
            "pages_in_filing": e.pages_in_filing, "skipped_mentions": len(e.skipped_heading_hits),
            "chars": len(e.text), "quarantined": len(e.quarantined), "injection_indicators": e.injection_indicators,
            "layout_warnings": e.layout_warnings}


@app.post("/api/cases/{slug}/extract")
def run_extraction(slug: str) -> dict:
    """Step 2: one live gpt-6-luna extraction (10-20 s), validated and assessed by code."""
    if slug not in case_slugs():
        raise HTTPException(404, "unknown case")
    now = time.time()
    _recent_runs[:] = [t for t in _recent_runs if now - t < 3600]
    if len(_recent_runs) >= MAX_LIVE_RUNS_PER_HOUR:
        raise HTTPException(429, f"Live-run limit reached ({MAX_LIVE_RUNS_PER_HOUR} per hour). Open a saved run instead.")
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(429, "Another extraction is running. Try again when it finishes.")
    try:
        _recent_runs.append(now)
        rec = extract(source_path(slug), slug)
    finally:
        _run_lock.release()
    return view(Path(rec["file"]).stem)


# ---------- one run ----------


def _load(name: str) -> dict:
    if not RUN_NAME.match(name):
        raise HTTPException(400, "bad run name")
    path = EXTRACTIONS / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, "run not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _activity(rec: dict) -> list[dict]:
    src, safety = rec["source"], rec["safety"]
    steps = [
        {"by": "code", "title": "Located the liquidation-analysis exhibit",
         "detail": f"'{src['exhibit_heading']}' on pages {src['exhibit_pages'][0]}-{src['exhibit_pages'][1]} of "
                   f"{src['pages_in_filing']}; skipped {len(src['skipped_heading_hits'])} earlier mentions "
                   f"(table of contents, cross-references)."},
        {"by": "code", "title": "Sanitized the exhibit only (untrusted filing text)",
         "detail": f"{rec['exhibit_chars']:,} characters sent to the model; {len(safety['quarantined'])} hidden item(s) "
                   f"withheld; {len(safety['injection_indicators'])} instruction-like phrase(s) flagged"
                   + (f"; {len(safety.get('layout_warnings', []))} page(s) whose layout the visibility rules could not "
                      f"resolve (plain text sent, flagged for review)" if safety.get("layout_warnings") else "") + "."},
    ]
    if rec.get("error"):
        steps.append({"by": "gpt-6-luna", "title": "Extraction failed", "detail": rec["error"]})
        return steps
    a = rec["result"]["analysis"]
    steps.append({"by": "gpt-6-luna", "title": "Extractor agent copied the summary waterfall table",
                  "detail": f"{len(a['assets'])} asset lines, {len(a['adjustments'])} adjustments, {len(a['claims'])} "
                            f"claim classes, {len(a['scenarios'])} scenarios, each row with its cited source row; "
                            f"{rec['attempts']} attempt(s) in {rec['seconds']} s."})
    for msg in rec.get("retry_messages", []):
        steps.append({"by": "code", "title": "Validator sent one targeted correction request", "detail": msg[:600]})
    original = rec.get("original_assessment") or rec["result"]["assessment"]
    steps.append({"by": "code", "title": "Validator checked the extraction",
                  "detail": f"Every number printed in its cited row: {'yes' if original['grounded'] else 'NO'}. "
                            f"Table totals add up: {'yes' if original['crossfoot_ok'] else 'NO'}."})
    for c in rec.get("corrections", []):
        steps.append({"by": f"person: {c['by']}", "title": f"Corrected {len(c['changes'])} field(s)",
                      "detail": "; ".join(f"{x['field']}: {x['old']} -> {x['new']}" for x in c["changes"])[:600]})
    now = rec["result"]["assessment"]
    steps.append({"by": "engine", "title": "Deterministic engine recomputed every filed scenario",
                  "detail": f"Recoveries match the filed table: {'yes' if now['reconciles_with_filed'] else 'NO'} "
                            f"(largest gap {now['max_pct_gap']:.2f} percentage points)."})
    return steps


def _model_reported(run_id: str) -> list[str]:
    for e in read_json_array(USAGE_LOG):
        if e.get("run_id") == run_id:
            return e.get("models_reported_by_api", [])
    return []


@app.get("/api/runs/{name}")
def view(name: str) -> dict:
    rec = _load(name)
    out = {k: rec.get(k) for k in ("run_id", "timestamp_utc", "case", "seconds", "attempts", "tokens", "cost_usd",
                                   "error", "source", "safety", "retry_messages", "corrections")}
    out.update(name=name, activity=_activity(rec), model_reported=_model_reported(rec["run_id"]),
               injection_test="ww_with_injection" in rec["source"]["file"])
    if rec.get("result"):
        out["result"] = rec["result"]
        out["review_rows"] = review_rows(rec)
        try:  # reference check: the hand-keyed answer key, never shown to the model
            key = load_case(rec["case"]).analysis
            if key is None:
                raise ValueError("No hand-keyed answer key exists for this case, so field accuracy is not scored.")
            s = score(key, LiquidationAnalysis.model_validate(rec["result"]["analysis"]))
            out["reference_check"] = {k: s[k] for k in ("fields_scored", "correct", "accuracy", "wrong", "missing")}
        except Exception as exc:
            out["reference_check"] = {"error": str(exc)[:300]}
    return out


class Correction(BaseModel):
    field: str
    value: float | int | str | None


class CorrectionRequest(BaseModel):
    by: str = Field(min_length=1, max_length=80)
    corrections: list[Correction] = Field(min_length=1, max_length=60)


@app.post("/api/runs/{name}/corrections")
def correct(name: str, body: CorrectionRequest) -> dict:
    rec = _load(name)
    if not rec.get("result"):
        raise HTTPException(400, "this run has no extraction to correct")
    if "original_assessment" not in rec:
        rec["original_assessment"] = rec["result"]["assessment"]
    try:
        fixed = apply_corrections(rec, [(c.field, c.value) for c in body.corrections], body.by)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(400, f"correction rejected: {exc}"[:400])
    return view(save(fixed).stem)


# ---------- stress test (engine only, no AI) ----------


class ScenarioRequest(BaseModel):
    scenario: int = Field(ge=0)
    asset_pct: dict[str, float] = Field(default_factory=dict, description="asset label -> recovery % of book value")
    cost_multiplier: float = Field(default=1.0, ge=0, le=5)


def _result(r: ScenarioResult) -> dict:
    return {"gross_proceeds": r.gross_proceeds, "adjustments": r.adjustments,
            "net_distributable_value": r.net_distributable_value, "residual": r.residual, "fulcrum": r.fulcrum,
            "classes": [{"label": c.label, "priority": c.priority, "claim": c.claim, "recovered": c.recovered,
                         "pct": c.pct} for c in r.classes]}


@app.post("/api/runs/{name}/scenario")
def scenario(name: str, body: ScenarioRequest) -> dict:
    rec = _load(name)
    if not rec.get("result"):
        raise HTTPException(400, "this run has no extraction")
    a = LiquidationAnalysis.model_validate(rec["result"]["analysis"])
    if body.scenario >= len(a.scenarios):
        raise HTTPException(400, "unknown scenario")
    books = {x.label: x.book_value for x in a.assets}
    for label, pct in body.asset_pct.items():
        if label not in books or books[label] is None:
            raise HTTPException(400, f"unknown asset or no book value: {label}")
        if not 0 <= pct <= 1000:
            raise HTTPException(400, "recovery % must be between 0 and 1000")
    i = body.scenario
    costs = {x.label: x.amounts[i] * body.cost_multiplier for x in a.adjustments if x.amounts[i] < 0}
    base = run_scenario(a, i)
    stressed = run_scenario(a, i, body.asset_pct or None, costs if body.cost_multiplier != 1 else None)
    return {"scenario": a.scenarios[i], "units": a.units, "base": _result(base), "stressed": _result(stressed),
            "assumptions": {"asset_pct": body.asset_pct, "cost_multiplier": body.cost_multiplier}}


@app.get("/api/usage")
def usage() -> dict:
    entries = read_json_array(USAGE_LOG)
    tot = {"runs": len(entries), "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    for e in entries:
        t = e.get("totals") or {}
        tot["input_tokens"] += t.get("input_tokens", 0)
        tot["cached_tokens"] += t.get("cached_tokens", 0)
        tot["output_tokens"] += t.get("output_tokens", 0)
        tot["cost_usd"] += (e.get("cost_usd") or {}).get("total", 0)
    return tot


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    print(f"Credit Recovery Copilot: open http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
