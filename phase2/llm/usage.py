"""Token usage normalization and cost accounting, including unknown usage."""
from __future__ import annotations

from typing import Dict, Optional

from phase2.llm.contracts import CostBreakdown, Usage

# Illustrative default price per 1,000 tokens, in USD. Override via
# GatewayConfig.pricing (or pass `pricing=` directly to `compute_cost`)
# to keep this accurate as provider pricing changes.
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4o": {"prompt": 0.0025, "completion": 0.01},
    "gpt-4.1-mini": {"prompt": 0.0004, "completion": 0.0016},
}


def normalize_usage(usage: Optional[Usage]) -> Usage:
    """Return a `Usage` even when the provider omitted usage data.

    Missing usage is marked `is_estimated=True` with zeroed counts so
    downstream cost/observability code can always rely on a `Usage`
    object being present, while still being able to detect that the
    figures are not real token counts.
    """
    if usage is None:
        return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, is_estimated=True)
    return usage


def compute_cost(
    usage: Usage,
    model: str,
    pricing: Optional[Dict[str, Dict[str, float]]] = None,
) -> CostBreakdown:
    """Compute a cost breakdown for `usage` against `model`'s pricing.

    If `usage` is an estimated placeholder for missing provider usage,
    or `model` has no known pricing, the returned `CostBreakdown`
    reports `total_cost=None` with an explanatory `note` rather than a
    misleading cost of $0.
    """
    table = pricing if pricing is not None else DEFAULT_PRICING
    rates = table.get(model)

    if usage.is_estimated:
        return CostBreakdown(
            prompt_cost=None,
            completion_cost=None,
            total_cost=None,
            pricing_known=rates is not None,
            note="usage_missing_from_provider",
        )

    if rates is None:
        return CostBreakdown(
            prompt_cost=None,
            completion_cost=None,
            total_cost=None,
            pricing_known=False,
            note=f"no_pricing_for_model:{model}",
        )

    prompt_cost = (usage.prompt_tokens / 1000.0) * rates["prompt"]
    completion_cost = (usage.completion_tokens / 1000.0) * rates["completion"]
    return CostBreakdown(
        prompt_cost=round(prompt_cost, 8),
        completion_cost=round(completion_cost, 8),
        total_cost=round(prompt_cost + completion_cost, 8),
        pricing_known=True,
    )
