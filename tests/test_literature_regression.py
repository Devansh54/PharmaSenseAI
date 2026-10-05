import pytest
import os
from unittest.mock import MagicMock
from pharmasense.agents.literature import create_literature_research_agent
from pharmasense.llm.contracts import LLMRequest, LLMResponse

def test_literature_research_does_not_hardcode_model():
    """Verify that Literature Research specialist does not hardcode gpt-4o-mini
    and instead defers to the LLMGateway configured model."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = LLMResponse(content='{"findings": "test", "citations": []}', parsed={"findings": "test", "citations": []})
    
    agent = create_literature_research_agent(session=MagicMock(), llm=mock_llm)
    
    # 1. The agent itself should not have a hardcoded model_name
    assert agent.model_name is None, "Literature agent must not hardcode a model_name"
    
    # 2. When the agent runs, the LLMRequest must not have a hardcoded model
    agent.run("test prompt")
    
    req: LLMRequest = mock_llm.complete.call_args[0][0]
    # In BaseAgent, req.model will be equal to agent.model_name (which is None)
    assert req.model is None or req.model == "", "LLMRequest sent by literature agent must not hardcode a model"

def test_gateway_configuration_is_dynamic():
    """Verify that GatewayConfig dynamic model factory picks up the environment correctly."""
    from pharmasense.config import GatewayConfig, GroqAdapterConfig
    
    os.environ["LLM_MODEL"] = "qwen/qwen3.8-27b"
    config = GatewayConfig()
    assert config.model == "qwen/qwen3.8-27b"
    
    groq_config = GroqAdapterConfig()
    assert groq_config.model == "qwen/qwen3.8-27b"
    
    # Revert if needed
    os.environ.pop("LLM_MODEL", None)
