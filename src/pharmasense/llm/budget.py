"""Budget-enforcing LLM gateway wrapper.

Wraps any LLMProvider and raises LLMBudgetExceededError immediately when any
configured limit is hit.  Designed for use in acceptance-test harnesses and
CI where unbounded token/call consumption must be prevented.

Normal production code should not need this; the standard LLMGateway with its
bounded RetryPolicy is sufficient for production.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from pharmasense.llm.contracts import (
    LLMGatewayError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class LLMBudgetExceededError(LLMGatewayError):
    """Raised when a budget limit (calls, prompt tokens, completion tokens) is hit.

    Always non-transient: callers must not retry after this error.
    """

    def __init__(
        self,
        message: str,
        *,
        limit_kind: str,
        limit_value: int,
        current_value: int,
    ) -> None:
        super().__init__(message)
        self.limit_kind = limit_kind
        self.limit_value = limit_value
        self.current_value = current_value


@dataclass
class RunBudget:
    """Hard limits for a single acceptance-test run.

    All limits are configurable at construction time; set a limit to 0 to
    disable that specific check.

    Defaults are chosen to be generous enough for any normal acceptance case
    (a multi-specialist S4 fan-out has ~6-12 LLM calls and ~20k tokens
    total) while still stopping runaway loops well before Groq's daily quota
    is exhausted.
    """

    max_llm_calls: int = 40
    """Maximum total gateway complete() calls across the entire run."""

    max_prompt_tokens: int = 80_000
    """Maximum cumulative prompt (input) tokens.  Estimated tokens count too."""

    max_completion_tokens: int = 20_000
    """Maximum cumulative completion (output) tokens."""

    # --- internal accumulators (not part of the public API) ---
    _call_count: int = field(default=0, init=False, repr=False)
    _prompt_tokens: int = field(default=0, init=False, repr=False)
    _completion_tokens: int = field(default=0, init=False, repr=False)

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def prompt_tokens(self) -> int:
        return self._prompt_tokens

    @property
    def completion_tokens(self) -> int:
        return self._completion_tokens

    def _record(self, response: LLMResponse) -> None:
        """Accumulate usage from a completed call and check limits."""
        self._call_count += 1
        if response.usage is not None:
            self._prompt_tokens += response.usage.prompt_tokens
            self._completion_tokens += response.usage.completion_tokens
        self._check()

    def _pre_check(self) -> None:
        """Check call-count limit *before* issuing the call."""
        if self.max_llm_calls and self._call_count >= self.max_llm_calls:
            raise LLMBudgetExceededError(
                f"Budget exceeded: max_llm_calls={self.max_llm_calls} reached "
                f"(current={self._call_count}). Aborting run.",
                limit_kind="max_llm_calls",
                limit_value=self.max_llm_calls,
                current_value=self._call_count,
            )

    def _check(self) -> None:
        """Check token limits *after* a completed call."""
        if self.max_prompt_tokens and self._prompt_tokens > self.max_prompt_tokens:
            raise LLMBudgetExceededError(
                f"Budget exceeded: max_prompt_tokens={self.max_prompt_tokens} "
                f"(current={self._prompt_tokens}). Aborting run.",
                limit_kind="max_prompt_tokens",
                limit_value=self.max_prompt_tokens,
                current_value=self._prompt_tokens,
            )
        if self.max_completion_tokens and self._completion_tokens > self.max_completion_tokens:
            raise LLMBudgetExceededError(
                f"Budget exceeded: max_completion_tokens={self.max_completion_tokens} "
                f"(current={self._completion_tokens}). Aborting run.",
                limit_kind="max_completion_tokens",
                limit_value=self.max_completion_tokens,
                current_value=self._completion_tokens,
            )


class BudgetEnforcingGateway(LLMProvider):
    """LLMProvider wrapper that enforces a RunBudget.

    Wraps any existing LLMProvider (typically an LLMGateway) and intercepts
    every complete() call to track cumulative usage.  Raises
    LLMBudgetExceededError (a non-transient LLMGatewayError) the moment any
    configured limit is exceeded, so callers stop immediately.

    Usage::

        budget = RunBudget(max_llm_calls=30, max_prompt_tokens=60_000)
        gateway = BudgetEnforcingGateway(
            inner=LLMGateway(GroqAdapter(...)),
            budget=budget,
        )
        # Pass gateway to agents / orchestration graph normally.
    """

    def __init__(
        self,
        inner: LLMProvider,
        budget: Optional[RunBudget] = None,
    ) -> None:
        self._inner = inner
        self._budget = budget or RunBudget()

    @property
    def budget(self) -> RunBudget:
        return self._budget

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Pre-call: check call-count limit before consuming a slot.
        self._budget._pre_check()

        try:
            response = self._inner.complete(request)
        except LLMBudgetExceededError:
            raise  # never suppress our own sentinel
        except Exception:
            # Still count the attempt even on error so loops can't hide behind failures.
            self._budget._call_count += 1
            raise

        # Post-call: accumulate usage and check token limits.
        self._budget._record(response)

        logger.debug(
            "budget calls=%d/%d prompt_tok=%d/%d completion_tok=%d/%d",
            self._budget.call_count,
            self._budget.max_llm_calls,
            self._budget.prompt_tokens,
            self._budget.max_prompt_tokens,
            self._budget.completion_tokens,
            self._budget.max_completion_tokens,
        )
        return response
