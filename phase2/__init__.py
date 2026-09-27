"""PharmaSense Phase 2: shared LLM gateway.

This package provides the single, provider-independent entry point
(`phase2.llm.gateway.LLMGateway`) that every agent/tool in later
phases uses to call an LLM. See `phase2.llm.contracts` for the shared
request/response types and `phase2.llm.openai_adapter` for the OpenAI
SDK-backed provider.
"""
