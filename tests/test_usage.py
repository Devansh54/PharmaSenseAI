"""Unit tests for token usage normalization and cost accounting."""
import pytest

from phase2.llm.contracts import Usage
from phase2.llm.usage import compute_cost, normalize_usage


def test_normalize_usage_passes_through_real_usage():
    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    assert normalize_usage(usage) is usage


def test_normalize_usage_fills_in_missing_usage():
    normalized = normalize_usage(None)
    assert normalized.is_estimated is True
    assert normalized.total_tokens == 0


def test_compute_cost_known_model():
    usage = Usage(prompt_tokens=2000, completion_tokens=1000, total_tokens=3000)
    pricing = {"m": {"prompt": 0.01, "completion": 0.02}}
    cost = compute_cost(usage, "m", pricing=pricing)
    assert cost.prompt_cost == pytest.approx(0.02)
    assert cost.completion_cost == pytest.approx(0.02)
    assert cost.total_cost == pytest.approx(0.04)
    assert cost.pricing_known is True


def test_compute_cost_unknown_model():
    usage = Usage(prompt_tokens=100, completion_tokens=100, total_tokens=200)
    cost = compute_cost(usage, "unknown-model", pricing={})
    assert cost.pricing_known is False
    assert cost.total_cost is None
    assert cost.note.startswith("no_pricing_for_model")


def test_compute_cost_estimated_usage_never_charges():
    usage = normalize_usage(None)
    cost = compute_cost(usage, "gpt-4o-mini")
    assert cost.total_cost is None
    assert cost.note == "usage_missing_from_provider"
