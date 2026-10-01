"""Timeout + bounded transient-retry policy for provider calls."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from pharmasense.llm.contracts import LLMGatewayError, LLMProviderError, LLMTimeoutError

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential-backoff retry policy.

    `max_retries` is the number of retries *after* the first attempt,
    so a call can be attempted at most `max_retries + 1` times.
    """

    max_retries: int = 2
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_seconds: float = 0.1


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, LLMTimeoutError):
        return True
    if isinstance(exc, LLMProviderError):
        return exc.transient
    return False


def call_with_retry(fn: Callable[[], T], policy: RetryPolicy) -> T:
    """Call `fn`, retrying on transient failures up to `policy.max_retries` times.

    Uses exponential backoff with jitter. Non-transient gateway errors
    (e.g. `LLMInvalidOutputError`, or an `LLMProviderError` with
    `transient=False`) and any non-gateway exception are raised
    immediately without retrying.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except LLMGatewayError as exc:
            attempt += 1
            if not _is_retryable(exc) or attempt > policy.max_retries:
                raise
            delay = min(
                policy.base_delay_seconds * (2 ** (attempt - 1)),
                policy.max_delay_seconds,
            )
            delay += random.uniform(0, policy.jitter_seconds)
            logger.warning(
                "Transient LLM error on attempt %s/%s (%s); retrying in %.2fs",
                attempt,
                policy.max_retries + 1,
                exc,
                delay,
            )
            time.sleep(delay)
