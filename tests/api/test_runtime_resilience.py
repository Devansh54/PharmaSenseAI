import pytest
import asyncio
import json
import httpx
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from pharmasense.api.main import app, get_db_session, build_gateway
from pharmasense.db.models import Base
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, LLMProviderError, LLMTimeoutError
from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.config import GroqAdapterConfig

# Shared test in-memory SQLite database
test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=test_engine)

@pytest.fixture(autouse=True)
def manage_overrides():
    saved_overrides = dict(app.dependency_overrides)
    if get_db_session not in app.dependency_overrides:
        def override_db():
            with Session(test_engine) as session:
                yield session
        app.dependency_overrides[get_db_session] = override_db
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)


class SlowMockLLM(LLMProvider):
    """Simulates a slow LLM call to verify health-check responsiveness during analysis."""
    def __init__(self, delay_sec: float = 0.5):
        self.delay_sec = delay_sec

    def complete(self, request: LLMRequest) -> LLMResponse:
        import time
        time.sleep(self.delay_sec)
        return LLMResponse(
            content=json.dumps({
                "workflow_type": "single",
                "selected_specialists": ["Trial Data Analyst"],
                "task_descriptions": {"Trial Data Analyst": "Find trials"},
                "resolved_entities": {}
            }),
            parsed={
                "workflow_type": "single",
                "selected_specialists": ["Trial Data Analyst"],
                "task_descriptions": {"Trial Data Analyst": "Find trials"},
                "resolved_entities": {}
            }
        )


class RateLimitedMockLLM(LLMProvider):
    """Simulates Groq 429 rate limit exceeded error."""
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError(
            "rate_limit_exceeded: output-token-per-minute limit 1,000; requested 1,116",
            transient=True
        )


class TimeoutMockLLM(LLMProvider):
    """Simulates an upstream provider timeout."""
    def complete(self, request: LLMRequest) -> LLMResponse:
        raise LLMTimeoutError("Request to Groq API timed out after 30s")


@pytest.mark.anyio
async def test_health_live_responsive_during_slow_analysis():
    """Verify /health/live returns immediately without blocking while a slow analysis is running."""
    slow_llm = SlowMockLLM(delay_sec=0.4)
    app.dependency_overrides[build_gateway] = lambda: slow_llm

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Launch analysis task concurrently
        analysis_task = asyncio.create_task(
            client.post(
                "/v1/analyses",
                json={"user_prompt": "Which trials are below 60% enrollment?"},
                headers={"Origin": "https://devansh54.github.io"}
            )
        )

        # Allow analysis to start, then immediately probe health check
        await asyncio.sleep(0.05)
        health_resp = await client.get("/health/live")
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}

        # Wait for analysis task to complete
        await analysis_task


@pytest.mark.anyio
async def test_groq_429_returns_clean_429_with_cors():
    """Verify that an upstream Groq 429 returns an HTTP 429 with CORS headers intact."""
    app.dependency_overrides[build_gateway] = lambda: RateLimitedMockLLM()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/analyses",
            json={"user_prompt": "Safety profile of Compound Astra-401"},
            headers={"Origin": "https://devansh54.github.io"}
        )

        assert resp.status_code == 429
        data = resp.json()
        assert "rate limit exceeded" in data["detail"].lower()
        # Ensure CORS headers are present on the error response
        assert resp.headers.get("access-control-allow-origin") == "https://devansh54.github.io"


@pytest.mark.anyio
async def test_upstream_timeout_returns_504_with_cors():
    """Verify that provider timeouts return HTTP 504 with CORS headers intact."""
    app.dependency_overrides[build_gateway] = lambda: TimeoutMockLLM()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/analyses",
            json={"user_prompt": "Synthesize literature"},
            headers={"Origin": "https://devansh54.github.io"}
        )

        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()
        assert resp.headers.get("access-control-allow-origin") == "https://devansh54.github.io"


def test_groq_adapter_sets_bounded_max_tokens():
    """Verify GroqAdapter defaults max_tokens to 600 to respect Groq's 1000 TPM limit."""
    mock_client = MagicMock()
    mock_raw = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "{}"
    mock_choice.message.tool_calls = None
    mock_raw.choices = [mock_choice]
    mock_raw.usage = None
    mock_client.chat.completions.create.return_value = mock_raw

    config = GroqAdapterConfig(api_key="fake", max_output_tokens=600)
    adapter = GroqAdapter(config=config, client=mock_client)

    # Request without explicit max_tokens
    req = LLMRequest(model="qwen/qwen3.8-27b", messages=[])
    adapter.complete(req)

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs.get("max_tokens") == 600

    # Request with explicit max_tokens
    req_custom = LLMRequest(model="qwen/qwen3.8-27b", messages=[], max_tokens=350)
    adapter.complete(req_custom)

    kwargs_custom = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs_custom.get("max_tokens") == 350
