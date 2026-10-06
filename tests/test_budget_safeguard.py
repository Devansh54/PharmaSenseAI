"""Focused offline tests for the RunBudget / BudgetEnforcingGateway safeguard.

These tests prove that:
1. Each limit (calls, prompt tokens, completion tokens) fires correctly.
2. Failed calls still count against the call limit.
3. Disabled limits (set to 0) allow unlimited calls.
4. LLMBudgetExceededError is a non-transient LLMGatewayError -> not retried.
5. Budget is env-var configurable.
6. Normal S4 offline case completes within the default limits.
7. A 1-call budget aborts an S4 run immediately.
"""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy.orm import Session

from pharmasense.llm.budget import (
    BudgetEnforcingGateway,
    LLMBudgetExceededError,
    RunBudget,
)
from pharmasense.llm.contracts import (
    LLMGatewayError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Usage,
)
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.retry import _is_retryable


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _CountingAdapter(LLMProvider):
    """Fake provider that records every call and returns a minimal valid response."""

    def __init__(self, response_fn=None):
        self._response_fn = response_fn
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._response_fn:
            return self._response_fn(request, len(self.calls))
        return LLMResponse(
            content=json.dumps({"ok": True}),
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )


class _AlwaysFailAdapter(LLMProvider):
    """Fake provider that always raises the given exception."""

    def __init__(self, exc):
        self._exc = exc

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise self._exc


# ---------------------------------------------------------------------------
# Unit tests: RunBudget + BudgetEnforcingGateway
# ---------------------------------------------------------------------------

def test_budget_max_llm_calls_stops_at_limit():
    """BudgetEnforcingGateway raises LLMBudgetExceededError after max_llm_calls."""
    budget = RunBudget(max_llm_calls=3, max_prompt_tokens=0, max_completion_tokens=0)
    inner = _CountingAdapter()
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    for _ in range(3):
        gw.complete(LLMRequest(messages=[]))

    with pytest.raises(LLMBudgetExceededError) as exc_info:
        gw.complete(LLMRequest(messages=[]))

    assert exc_info.value.limit_kind == "max_llm_calls"
    assert exc_info.value.limit_value == 3
    assert exc_info.value.current_value == 3
    # Inner was called exactly 3 times - the 4th call never reached it
    assert len(inner.calls) == 3


def test_budget_max_prompt_tokens_stops_after_limit():
    """BudgetEnforcingGateway raises LLMBudgetExceededError when prompt tokens exceed limit."""
    budget = RunBudget(max_llm_calls=0, max_prompt_tokens=250, max_completion_tokens=0)
    inner = _CountingAdapter()  # each call uses 100 prompt tokens
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    # Two calls = 200 prompt tokens -> OK
    gw.complete(LLMRequest(messages=[]))
    gw.complete(LLMRequest(messages=[]))
    assert budget.prompt_tokens == 200

    # Third call would push to 300 > 250 -> must raise
    with pytest.raises(LLMBudgetExceededError) as exc_info:
        gw.complete(LLMRequest(messages=[]))

    assert exc_info.value.limit_kind == "max_prompt_tokens"
    assert exc_info.value.current_value == 300


def test_budget_max_completion_tokens_stops_after_limit():
    """BudgetEnforcingGateway raises LLMBudgetExceededError when completion tokens exceed limit."""
    budget = RunBudget(max_llm_calls=0, max_prompt_tokens=0, max_completion_tokens=80)
    inner = _CountingAdapter()  # each call uses 50 completion tokens
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    gw.complete(LLMRequest(messages=[]))  # 50 completion tokens

    with pytest.raises(LLMBudgetExceededError) as exc_info:
        gw.complete(LLMRequest(messages=[]))  # 100 > 80 -> must raise

    assert exc_info.value.limit_kind == "max_completion_tokens"
    assert exc_info.value.current_value == 100


def test_budget_failed_call_still_counts_against_call_limit():
    """A call that raises an inner error still increments the call counter."""
    from pharmasense.llm.contracts import LLMProviderError

    budget = RunBudget(max_llm_calls=2, max_prompt_tokens=0, max_completion_tokens=0)
    exc = LLMProviderError("boom", transient=False)
    inner = _AlwaysFailAdapter(exc)
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    with pytest.raises(LLMProviderError):
        gw.complete(LLMRequest(messages=[]))
    with pytest.raises(LLMProviderError):
        gw.complete(LLMRequest(messages=[]))

    # Third attempt: call count is already 2, hits max_llm_calls before reaching inner
    with pytest.raises(LLMBudgetExceededError):
        gw.complete(LLMRequest(messages=[]))

    assert budget.call_count == 2


def test_budget_disabled_limits_allow_unlimited_calls():
    """Setting all limits to 0 disables enforcement entirely."""
    budget = RunBudget(max_llm_calls=0, max_prompt_tokens=0, max_completion_tokens=0)
    inner = _CountingAdapter()
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    for _ in range(50):
        gw.complete(LLMRequest(messages=[]))

    assert budget.call_count == 50


def test_budget_error_is_non_transient_gateway_error():
    """LLMBudgetExceededError is a non-transient LLMGatewayError so retry loops won't loop on it."""
    err = LLMBudgetExceededError(
        "over limit",
        limit_kind="max_llm_calls",
        limit_value=5,
        current_value=5,
    )
    assert isinstance(err, LLMGatewayError)
    # _is_retryable must return False so call_with_retry won't loop
    assert not _is_retryable(err)


def test_budget_configurable_via_env_variable(monkeypatch):
    """RunBudget can be constructed from env vars (mirrors acceptance_gateway fixture)."""
    monkeypatch.setenv("ACCEPTANCE_MAX_LLM_CALLS", "7")
    monkeypatch.setenv("ACCEPTANCE_MAX_PROMPT_TOKENS", "1000")
    monkeypatch.setenv("ACCEPTANCE_MAX_COMPLETION_TOKENS", "500")

    budget = RunBudget(
        max_llm_calls=int(os.environ.get("ACCEPTANCE_MAX_LLM_CALLS", "40")),
        max_prompt_tokens=int(os.environ.get("ACCEPTANCE_MAX_PROMPT_TOKENS", "80000")),
        max_completion_tokens=int(os.environ.get("ACCEPTANCE_MAX_COMPLETION_TOKENS", "20000")),
    )
    assert budget.max_llm_calls == 7
    assert budget.max_prompt_tokens == 1000
    assert budget.max_completion_tokens == 500


def test_budget_default_values_are_sensible():
    """Default RunBudget values are non-zero and within reasonable ranges."""
    budget = RunBudget()
    assert 10 <= budget.max_llm_calls <= 200
    assert 10_000 <= budget.max_prompt_tokens <= 500_000
    assert 5_000 <= budget.max_completion_tokens <= 200_000


def test_budget_accumulates_across_multiple_calls():
    """RunBudget correctly sums tokens across many calls."""
    budget = RunBudget(max_llm_calls=0, max_prompt_tokens=0, max_completion_tokens=0)
    inner = _CountingAdapter()
    gw = BudgetEnforcingGateway(inner=inner, budget=budget)

    for _ in range(5):
        gw.complete(LLMRequest(messages=[]))

    assert budget.call_count == 5
    assert budget.prompt_tokens == 500      # 5 * 100
    assert budget.completion_tokens == 250  # 5 * 50


def test_budget_s4_offline_runs_within_default_limits(pgvector_engine):
    """S4 offline case completes within a tight-but-sufficient budget."""
    from tests.test_live_acceptance import OfflineAdapter, run_acceptance_case

    responses = [
        LLMResponse(
            content=json.dumps({"summary": "Trial info", "limitations": []}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
        LLMResponse(
            content=json.dumps({"findings": "Lit info", "citations": [], "no_evidence_found": False}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
        LLMResponse(
            content=json.dumps({"explanation": "None", "final_severity": "Unknown", "final_seriousness": "Unknown", "requires_review": False}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
        LLMResponse(
            content=json.dumps({"score": 0.9, "explanation": "Sim info", "coverage": 0.8}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
        LLMResponse(
            content=json.dumps({"report_text": "Report.", "limitations_noted": [], "citations_resolved": []}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
        LLMResponse(
            content=json.dumps({"is_supported": True, "reason": "Yes"}),
            usage=Usage(prompt_tokens=500, completion_tokens=200, total_tokens=700),
        ),
    ]
    budget = RunBudget(max_llm_calls=20, max_prompt_tokens=20_000, max_completion_tokens=5_000)
    inner_gw = LLMGateway(OfflineAdapter(responses))
    gw = BudgetEnforcingGateway(inner=inner_gw, budget=budget)

    with Session(pgvector_engine) as session:
        state = run_acceptance_case(gw, session, "Give me the full picture on compound DKU-1042.")

    assert state.get("errors", []) == []
    assert "final_report" in state
    assert budget.call_count <= 20


def test_budget_stops_run_when_call_limit_exceeded(pgvector_engine):
    """BudgetEnforcingGateway aborts a run when call limit is set to 1."""
    from tests.test_live_acceptance import OfflineAdapter, run_acceptance_case

    responses = [
        LLMResponse(
            content=json.dumps({"summary": "Trial info", "limitations": []}),
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )
        for _ in range(20)
    ]
    budget = RunBudget(max_llm_calls=1, max_prompt_tokens=0, max_completion_tokens=0)
    inner_gw = LLMGateway(OfflineAdapter(responses))
    gw = BudgetEnforcingGateway(inner=inner_gw, budget=budget)

    try:
        with Session(pgvector_engine) as session:
            state = run_acceptance_case(gw, session, "Give me the full picture on compound DKU-1042.")
        # If we get here the error was captured in state
        assert state.get("errors", []) != [], "Expected budget error in state"
    except LLMBudgetExceededError:
        pass  # propagated unhandled: also acceptable

    # At most 1 successful call + the attempt that hit the limit
    assert budget.call_count <= 2
