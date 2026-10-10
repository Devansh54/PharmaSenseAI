import os
from pharmasense.api.main import build_gateway

def test_api_gateway_uses_configured_model_without_override():
    # Clear any environment variables that might interfere
    os.environ.pop("LLM_MODEL", None)
    os.environ.pop("PHARMASENSE_LLM_MODEL", None)
    
    # Build the gateway
    gateway = build_gateway()
    
    # Extract inner components
    llm_gateway = gateway._inner
    adapter = llm_gateway._provider
    
    # 1. GatewayConfig should not be overridden by the unavailable gpt-4o-mini
    assert llm_gateway._config.model == "qwen/qwen3.8-27b", "GatewayConfig must use the intended model qwen/qwen3.8-27b"
    
    # 2. Adapter config should also match
    assert adapter._config.model == "qwen/qwen3.8-27b", "GroqAdapterConfig must use the intended model qwen/qwen3.8-27b"
