"""Extractor agent: one liquidation-analysis exhibit in, one validated LiquidationAnalysis out (gpt-6-luna).

    python -m app.extract data/cases/ww_international/source.htm

Pipeline for one run:
    1. Code: locate the exhibit in the filing and sanitize only those pages (app/locate.py).
    2. Model: one PydanticAI run. Output is engine.schema.LiquidationAnalysis, every row with its source_text.
    3. Code, inside the run: an output validator checks grounding (every number printed in its cited row) and the
       filing's own arithmetic. If either fails, the model gets ONE targeted retry listing exactly what failed.
       Code computes those sums; the model is only asked to re-read the table.
    4. Code, after the run: rounding_step is set from the values, then app/checks.assess() runs the engine.
    5. Evidence: output/usage_log.json (tokens, cost), output/audit_trail.json (what was sent, every attempt),
       output/extractions/<case>-<run_id>.json (result, provenance, assessment).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits, capture_run_messages
from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from app.checks import assess, grounding_problems, rounding_step_from_values
from app.llm import MODEL_NAME, ROOT, build_model, load_api_key, load_prices, usage_record
from app.locate import Exhibit, locate_exhibit
from app.logs import append_json, read_json_array, utc_now
from app.sanitize import envelope
from engine.schema import LiquidationAnalysis
from engine.waterfall import crossfoot

PROMPT_FILE = ROOT / "prompts" / "extractor.md"
OUTPUT = ROOT / "output"
USAGE_LOG = OUTPUT / "usage_log.json"
AUDIT_TRAIL = OUTPUT / "audit_trail.json"
EXTRACTIONS = OUTPUT / "extractions"
SETTINGS = OpenAIResponsesModelSettings(openai_reasoning_effort="medium")
LIMITS = UsageLimits(request_limit=4, total_tokens_limit=80_000)  # 1 normal call + 1 retry; caps a runaway loop
MAX_CORRECTIONS = 1


def validation_problems(output: LiquidationAnalysis, exhibit_text: str) -> list[str]:
    """What the targeted retry tells the model. Sums are computed here, in code."""
    problems = grounding_problems(output, exhibit_text)
    problems += [f"{c.scenario}: {c.item}: the rows you extracted give {c.computed:,.2f} but the stated total you "
                 f"extracted is {c.filed:,.2f}. Re-read the table: a row may be missing, duplicated, mis-signed or "
                 f"shifted by a column." for c in crossfoot(output) if not c.ok]
    return problems


def build_extractor(model) -> Agent[str, LiquidationAnalysis]:
    agent = Agent(
        model,
        output_type=LiquidationAnalysis,
        instructions=PROMPT_FILE.read_text(encoding="utf-8"),
        deps_type=str,  # the sanitized exhibit text, for the validator
        retries=MAX_CORRECTIONS,
    )

    @agent.output_validator
    def grounded_and_consistent(ctx: RunContext[str], output: LiquidationAnalysis) -> LiquidationAnalysis:
        problems = validation_problems(output, ctx.deps)
        if problems and ctx.retry < MAX_CORRECTIONS:
            raise ModelRetry("Fix only these problems and return the whole table again:\n- " + "\n- ".join(problems))
        return output  # still-failing output is kept and shown to a person as needs_review, never silently fixed

    return agent


def user_prompt(exhibit: Exhibit, nonce: str) -> str:
    return ("Extract the summary waterfall table from this liquidation-analysis exhibit.\n\n"
            + envelope(exhibit.text, nonce, label="liquidation analysis exhibit"))


def _attempts(messages) -> tuple[list[dict], list[str]]:
    """Every structured answer the model gave (first attempt, retry) and every retry message code sent back."""
    answers, retries = [], []
    for msg in messages:
        for part in msg.parts:
            if isinstance(msg, ModelResponse) and isinstance(part, ToolCallPart):
                answers.append(part.args_as_dict())
            elif isinstance(msg, ModelRequest) and isinstance(part, RetryPromptPart):
                retries.append(str(part.content)[:4000])
    return answers, retries


def _display_path(path: Path) -> str:
    """Repo-relative path for the logs; never the local absolute path (it would publish the user's folder names)."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return f"<outside repo>/{path.name}"


def provenance_for(analysis: dict) -> dict[str, str]:
    """Every leaf field of the model's answer is 'extracted'; rounding_step is set by code."""
    out = {}

    def walk(value, path):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")
        else:
            out[path] = "extracted"

    walk(analysis, "")
    out["rounding_step"] = "computed (code)"
    return out


def extract(source: str | Path, case: str | None = None) -> dict:
    source = Path(source)
    case = case or source.parent.name
    run_id, nonce = uuid.uuid4().hex[:12], uuid.uuid4().hex[:12]
    exhibit = locate_exhibit(source)
    model = build_model(load_api_key())
    agent = build_extractor(model)
    prompt = user_prompt(exhibit, nonce)
    started, output, error = time.perf_counter(), None, None
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(prompt, deps=exhibit.text, usage_limits=LIMITS, model_settings=SETTINGS)
            output = result.output
        except Exception as exc:  # logged as evidence, never hidden
            error = f"{type(exc).__name__}: {exc}"[:2000]
    seconds = round(time.perf_counter() - started, 2)
    answers, retries = _attempts(messages)

    earlier = {r["response_id"] for e in read_json_array(USAGE_LOG) for r in e.get("api_requests", [])}
    usage = usage_record(run_id, "extractor", model.api_responses, load_prices(), earlier)
    usage.update(timestamp_utc=utc_now(), case=case, seconds=seconds, error=error)
    append_json(USAGE_LOG, usage)

    record = {
        "run_id": run_id, "timestamp_utc": usage["timestamp_utc"], "case": case, "agent": "extractor",
        "model_requested": MODEL_NAME, "seconds": seconds, "error": error,
        "source": {"file": _display_path(source), "sha256": exhibit.source_sha256,
                   "exhibit_heading": exhibit.heading, "exhibit_pages": [exhibit.first_page, exhibit.last_page],
                   "pages_in_filing": exhibit.pages_in_filing, "skipped_heading_hits": exhibit.skipped_heading_hits},
        "safety": {"quarantined": [q.model_dump() for q in exhibit.quarantined],
                   "invisible_characters_removed": exhibit.invisible_characters_removed,
                   "injection_indicators": exhibit.injection_indicators,
                   "layout_warnings": exhibit.layout_warnings},
        "exhibit_text_sha256": hashlib.sha256(exhibit.text.encode("utf-8")).hexdigest(),
        "exhibit_chars": len(exhibit.text),
        "attempts": len(answers), "retry_messages": retries,
        "tokens": usage["totals"], "cost_usd": usage["cost_usd"],
    }
    if output is not None:
        output = output.model_copy(update={"rounding_step": rounding_step_from_values(output)})
        analysis = output.model_dump(mode="json")
        record["result"] = {
            "analysis": analysis,
            "provenance": provenance_for(analysis),
            "assessment": assess(output, exhibit.text, exhibit.injection_indicators, len(exhibit.quarantined),
                                 exhibit.layout_warnings),
        }
    record["first_attempt"] = answers[0] if answers else None
    append_json(AUDIT_TRAIL, {**record, "document_text_sent_to_model": exhibit.text, "all_attempts": answers})
    EXTRACTIONS.mkdir(parents=True, exist_ok=True)
    out_file = EXTRACTIONS / f"{case}-{run_id}.json"
    out_file.write_text(json.dumps({**record, "exhibit_text": exhibit.text}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    record["file"] = out_file.relative_to(ROOT).as_posix()
    return record


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="disclosure statement HTML (e.g. data/cases/ww_international/source.htm)")
    p.add_argument("--case", help="case name for the logs (default: the source's folder name)")
    args = p.parse_args()
    r = extract(args.source, args.case)
    t = r["tokens"] or {}
    print(f"run {r['run_id']} | {r['seconds']} s | attempts {r['attempts']} | input {t.get('input_tokens', 0):,} "
          f"(cached {t.get('cached_tokens', 0):,}) | output {t.get('output_tokens', 0):,} | "
          f"cost ${(r['cost_usd'] or {}).get('total', 0):.5f} | {r['file']}")
    if r.get("error"):
        print("ERROR:", r["error"])
        return 1
    a = r["result"]["assessment"]
    print(f"status: {a['status']} | grounded {a['grounded']} | crossfoot {a['crossfoot_ok']} | "
          f"reconciles {a['reconciles_with_filed']}")
    for w in a["warnings"]:
        print(f"  [{w['severity']}] {w['kind']}: {w['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
