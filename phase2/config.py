"""Configuration for the Phase 2 shared LLM Gateway."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from phase2.llm.retry import RetryPolicy
from phase2.llm.usage import DEFAULT_PRICING

DEFAULT_MODEL = os.environ.get("PHARMASENSE_LLM_MODEL", "gpt-4o-mini")
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("PHARMASENSE_LLM_TIMEOUT_SECONDS", "30"))
DEFAULT_MAX_RETRIES = int(os.environ.get("PHARMASENSE_LLM_MAX_RETRIES", "2"))

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENAI_ORG_ENV = "OPENAI_ORG_ID"


@dataclass(frozen=True)
class GatewayConfig:
    """Runtime configuration for `LLMGateway`.

    All defaults come from environment variables so the same code runs
    unchanged across local, CI, and later-phase deployments (Step 2 of
    the repository guide: "a single, swappable LLM access function").
    """

    model: str = DEFAULT_MODEL
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    retry_policy: RetryPolicy = field(
        default_factory=lambda: RetryPolicy(max_retries=DEFAULT_MAX_RETRIES)
    )
    pricing: Dict[str, Dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_PRICING))


@dataclass(frozen=True)
class OpenAIAdapterConfig:
    """Configuration specific to the OpenAI SDK adapter.

    Kept separate from `GatewayConfig` so the gateway itself never
    depends on provider-specific settings (API key, base URL, org id).
    """

    model: str = DEFAULT_MODEL
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_API_KEY_ENV))
    base_url: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_BASE_URL_ENV))
    organization: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_ORG_ENV))
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        """Whether enough credentials are present to make a live call."""
        return bool(self.api_key)
