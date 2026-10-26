"""Model access and token/cost accounting, carried over from HW6 (hw6-vendor-desk, agent.py).

Kept as in HW6: EvidenceResponsesModel, build_model, token_counts, cost_usd, load_prices.
Changed:
    load_api_key  checks this repo folder first, then each parent folder, and keeps going until one supplies
                  PORTKEY_API_KEY (HW6 stopped at the first .env it found, even one without the key).
    usage_record  no longer tied to HW6's RunOutcome; one record per agent call, any agent.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "gpt-6-luna"  # the only model allowed on the course key
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PRICES_FILE = ROOT / "data" / "prices.json"
MILLION = Decimal(1_000_000)


class EvidenceResponsesModel(OpenAIResponsesModel):
    """OpenAIResponsesModel that also keeps each API response's id, model, full `usage` object and prompt-cache
    diagnostics, exactly as the API returned them (PydanticAI's normalized usage drops some nested fields).

    Hooks the non-streaming path only, which is the one agent.run / run_sync use.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_responses: list[dict] = []

    def _process_response(self, response, model_settings, model_request_parameters):
        if not isinstance(response, str):  # a non-JSON body is left to PydanticAI's own error handling
            diagnostics = getattr(response, "prompt_cache_diagnostics", None)
            self.api_responses.append(
                {
                    "response_id": response.id,
                    "model": response.model,
                    "usage": response.usage.model_dump(mode="json") if response.usage else None,
                    "prompt_cache_diagnostics": diagnostics.model_dump(mode="json") if diagnostics else None,
                }
            )
        return super()._process_response(response, model_settings, model_request_parameters)


def load_api_key() -> str:
    """PORTKEY_API_KEY from the environment, else from .env in this repo, else from .env in a parent folder.
    The value is never printed or logged."""
    for folder in [ROOT, *ROOT.parents]:
        if os.getenv("PORTKEY_API_KEY", "").strip():
            break
        if (folder / ".env").exists():
            load_dotenv(folder / ".env", override=False)
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not key:
        raise SystemExit("PORTKEY_API_KEY is not set. Put it in a .env file in this folder or the folder above it.")
    return key


def build_model(api_key: str) -> EvidenceResponsesModel:
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        # Portkey keeps a response cache: without force-refresh an identical request gets an earlier
        # response replayed (same response id) and never reaches the model. Every run must be a real call.
        default_headers={"x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"},
        timeout=120.0,
        max_retries=2,
    )
    return EvidenceResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# ---------- token and cost evidence ----------


def load_prices() -> dict[str, Decimal]:
    return json.loads(PRICES_FILE.read_text(encoding="utf-8"), parse_float=Decimal)[MODEL_NAME]


def token_counts(usage: dict) -> dict[str, int]:
    """The billing-relevant counts from one raw Responses API usage object."""
    inp = usage.get("input_tokens") or 0
    in_details = usage.get("input_tokens_details") or {}
    out_details = usage.get("output_tokens_details") or {}
    cached = in_details.get("cached_tokens") or 0
    written = in_details.get("cache_write_tokens") or 0
    return {
        "input_tokens": inp,
        "cached_tokens": cached,
        "cache_write_tokens": written,
        "uncached_input_tokens": inp - cached - written,
        "output_tokens": usage.get("output_tokens") or 0,
        "reasoning_tokens": out_details.get("reasoning_tokens") or 0,
        "total_tokens": usage.get("total_tokens") or 0,
    }


def cost_usd(counts: dict[str, int], prices: dict[str, Decimal]) -> dict[str, float]:
    """Dollar cost from data/prices.json. Reasoning tokens are already inside output_tokens."""
    parts = {
        "uncached_input": counts["uncached_input_tokens"] * prices["input_per_1m"],
        "cached_input": counts["cached_tokens"] * prices["cached_input_per_1m"],
        "cache_write": counts["cache_write_tokens"] * prices["cache_write_per_1m"],
        "output": counts["output_tokens"] * prices["output_per_1m"],
    }
    parts = {k: v / MILLION for k, v in parts.items()}
    parts["total"] = sum(parts.values())
    return {k: float(v) for k, v in parts.items()}


def usage_record(run_id: str, agent: str, api_responses: list[dict], prices: dict[str, Decimal],
                 earlier_response_ids: set[str] | frozenset[str] = frozenset()) -> dict:
    """One usage-log entry for one agent call: per-request counts and cost, plus run totals."""
    requests, totals, missing = [], {}, False
    for resp in api_responses:
        if resp["usage"] is None:  # not reported: no counts, no cost, never a measured zero
            missing = True
            requests.append({**resp, "cost_usd": None})
            continue
        counts = token_counts(resp["usage"])
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
        requests.append({**resp, "cost_usd": cost_usd(counts, prices)})
    return {
        "run_id": run_id,
        "agent": agent,
        "model_requested": MODEL_NAME,
        "models_reported_by_api": sorted({r["model"] for r in api_responses}),
        "api_requests": requests,
        # a response id seen in an earlier run means a gateway replay, not a new model call
        "replayed_response_ids": [r["response_id"] for r in api_responses if r["response_id"] in earlier_response_ids],
        "usage_missing_on_some_request": missing,
        "totals": totals or None,
        "cost_usd": cost_usd(totals, prices) if totals else None,
        "prices_per_1m_usd": {k: float(v) for k, v in prices.items()},
    }
