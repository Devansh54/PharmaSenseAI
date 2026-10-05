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

def test_evidence_validation_rejects_hallucinated_0_score():
    """Verify that hallucinating 0.000 relevance on non-zero chunks is rejected."""
    from pharmasense.llm.contracts import Message
    from pharmasense.utils.formatters import compact_tool_result
    from pharmasense.orchestration.graph import OutputGuardrailNode
    from pharmasense.llm.gateway import LLMGateway
    from unittest.mock import MagicMock
    from pharmasense.llm.contracts import LLMResponse

    # 1. Create a mock tool result representing what the vector search actually returned
    tool_result = {
        "chunks": [
            {
                "chunk_id": "TEST-001::chunk::0",
                "doc_id": "TEST-001",
                "title": "Literature Review: Test",
                "chunk_text": "A meta-analysis of trials targeting JAK2 found that survival improved, though Myalgia was a toxicity.",
                "similarity_score": 0.785
            }
        ]
    }

    # 2. Compact it using the formatter that was just fixed
    compacted_str = compact_tool_result(tool_result)
    assert "0.785" in compacted_str, "Formatter must preserve the similarity_score"
    assert "Myalgia" in compacted_str, "Formatter must preserve the chunk_text"

    # 3. Create mock messages representing the agent's context
    messages = [
        Message(role="tool", content=compacted_str, name="vector_search_tool")
    ]

    # 4. Create a state with a hallucinated report claiming 0.000 score
    bad_state = {
        "messages": messages,
        "final_report": {
            "report_content": "The vector search returned chunks, but they all had a relevance score of 0.000 and contained no usable information about JAK2."
        },
        "evidence_repaired": True
    }

    # 5. Run the guardrail offline using a mock LLM
    mock_llm = MagicMock()
    guardrail = OutputGuardrailNode(mock_llm)

    # Register the mock response for the rejection
    mock_llm.complete.return_value = LLMResponse(
        content='{"is_supported": false, "reason": "Claims 0.000 score but context shows 0.785"}',
        parsed={"is_supported": False, "reason": "Claims 0.000 score but context shows 0.785"}
    )

    result_state = guardrail(bad_state)
    assert "errors" in result_state
    assert "Evidence validation failed" in result_state["errors"][0]

def test_evidence_validation_accepts_grounded_abstain():
    """Verify that a grounded abstaining report is accepted."""
    from pharmasense.llm.contracts import Message
    from pharmasense.utils.formatters import compact_tool_result
    from pharmasense.orchestration.graph import OutputGuardrailNode
    from pharmasense.llm.gateway import LLMGateway
    from pharmasense.llm.contracts import LLMResponse
    from unittest.mock import MagicMock

    tool_result = {
        "chunks": [
            {
                "chunk_id": "TEST-002::chunk::0",
                "doc_id": "TEST-002",
                "title": "Literature",
                "chunk_text": "JAK2 inhibition causes fatigue.",
                "similarity_score": 0.720
            }
        ]
    }

    compacted_str = compact_tool_result(tool_result)
    messages = [Message(role="tool", content=compacted_str, name="vector_search_tool")]

    good_state = {
        "messages": messages,
        "final_report": {
            "report_content": "The retrieved documents contain JAK2-related toxicity information, but the available excerpts do not provide sufficient direct evidence to establish cardiotoxicity."
        }
    }

    mock_llm = MagicMock()
    guardrail = OutputGuardrailNode(mock_llm)

    mock_llm.complete.return_value = LLMResponse(
        content='{"is_supported": true, "reason": "Accurately reflects the context"}',
        parsed={"is_supported": True, "reason": "Accurately reflects the context"}
    )

    result_state = guardrail(good_state)
    assert result_state.get("validation_feedback") is None
    assert "errors" not in result_state
