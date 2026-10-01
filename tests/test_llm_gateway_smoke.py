"""Live smoke test for the OpenAI adapter.

This test makes a real network call against the OpenAI API and is
skipped automatically unless OPENAI_API_KEY is set in the environment,
since Phase 2 CI does not have live credentials configured by default.

Run locally with credentials to exercise it:
    OPENAI_API_KEY=sk-... pytest -v tests/test_llm_gateway_smoke.py
"""
import os

import pytest

from pharmasense.config import GatewayConfig, OpenAIAdapterConfig
from pharmasense.llm.contracts import LLMRequest, Message
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.openai_adapter import OpenAIAdapter

pytestmark = pytest.mark.smoke

_MISSING_CREDENTIALS = not os.environ.get("OPENAI_API_KEY")


@pytest.mark.skipif(_MISSING_CREDENTIALS, reason="OPENAI_API_KEY not set; skipping live smoke test")
def test_live_smoke_generate_returns_a_response():
    adapter_config = OpenAIAdapterConfig()
    adapter = OpenAIAdapter(config=adapter_config)
    gateway = LLMGateway(adapter, config=GatewayConfig(model=adapter_config.model))

    request = LLMRequest(
        messages=[Message(role="user", content="Reply with the single word: pong")],
        model=adapter_config.model,
    )
    response = gateway.generate(request)

    assert response.content
    assert response.usage is not None
