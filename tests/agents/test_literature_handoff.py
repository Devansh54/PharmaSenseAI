import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall, Message
from pharmasense.agents.literature import create_literature_research_agent, LiteratureResearchOutput
from pharmasense.tools.vector_search import VectorSearchInput, VectorSearchOutput
from pharmasense.llm.gateway import LLMGateway

class MockDefectiveLiteratureLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0
        self.requests = []
        
    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.requests.append(request)
        
        if self.call_count == 1:
            tc = ToolCall(
                id="call_vs",
                name="vector_search_tool",
                arguments={"query": "ZXQ-9999", "top_k": 5}
            )
            return LLMResponse(content="", tool_calls=[tc], parsed=None, provider_metadata={})
        
        elif self.call_count == 2:
            # Emulate the defect: string boolean, string citation, invented citation
            tc = ToolCall(
                id="call_out",
                name="LiteratureResearchOutput",
                arguments={
                    "findings": "No evidence.",
                    "citations": "invented_chunk_id",
                    "no_evidence_found": "True"
                }
            )
            return LLMResponse(content="", tool_calls=[tc], parsed=None, provider_metadata={})
            
        raise RuntimeError("Agent looped instead of coercing types")

def test_literature_search_empty_termination():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        llm = MockDefectiveLiteratureLLM()
        gateway = LLMGateway(llm)
        agent = create_literature_research_agent(session, gateway)
        
        def mock_vs_tool_empty(session, input_data: VectorSearchInput):
            return VectorSearchOutput(chunks=[], index_version="mock")
            
        agent.tools["vector_search_tool"] = mock_vs_tool_empty
        
        res, tools = agent.run("Find research on ZXQ-9999.")
        
        assert llm.call_count == 1
        assert isinstance(res, LiteratureResearchOutput)
        assert res.no_evidence_found is True
        assert res.citations == []
        assert res.findings == "No relevant literature found."

def test_literature_search_coercion():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        llm = MockDefectiveLiteratureLLM()
        gateway = LLMGateway(llm)
        agent = create_literature_research_agent(session, gateway)
        
        def mock_vs_tool_non_empty(session, input_data: VectorSearchInput):
            return VectorSearchOutput(chunks=[{"chunk_id": "valid_id", "doc_id": "doc_1", "title": "Test", "chunk_text": "text", "similarity_score": 0.9}], index_version="mock")
            
        agent.tools["vector_search_tool"] = mock_vs_tool_non_empty
        
        res, tools = agent.run("Find research on ZXQ-9999.")
        
        assert llm.call_count == 2
        assert isinstance(res, LiteratureResearchOutput)
        assert res.no_evidence_found is True  # Based on the mocked LLM output
        assert res.citations == []
        assert res.findings == "No evidence."

class MockLoopingLiteratureLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0
        self.requests = []
        
    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.requests.append(request)
        
        if self.call_count == 1:
            tc = ToolCall(
                id="call_vs",
                name="vector_search_tool",
                arguments={"query": "ZXQ-9999", "top_k": 5}
            )
            return LLMResponse(content="", tool_calls=[tc], parsed=None, provider_metadata={})
        
        # Keep returning garbage to hit max iterations
        return LLMResponse(content="I am stuck looping", tool_calls=None, parsed=None, provider_metadata={})

def test_literature_search_execution_error():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        llm = MockLoopingLiteratureLLM()
        gateway = LLMGateway(llm)
        agent = create_literature_research_agent(session, gateway)
        
        def mock_vs_tool_fail(session, input_data: VectorSearchInput):
            raise RuntimeError("Database connection lost.")
            
        agent.tools["vector_search_tool"] = mock_vs_tool_fail
        
        res, tools = agent.run("Find research on ZXQ-9999.")
        
        assert isinstance(res, LiteratureResearchOutput)
        assert res.no_evidence_found is False
        assert res.findings == "Search execution failed."
        assert "Database connection lost." in str(res.limitations)

def test_literature_search_format_failure():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        llm = MockLoopingLiteratureLLM()
        gateway = LLMGateway(llm)
        agent = create_literature_research_agent(session, gateway)
        
        def mock_vs_tool_chunks(session, input_data: VectorSearchInput):
            return VectorSearchOutput(chunks=[{"chunk_id": "1", "chunk_text": "noise"}], index_version="mock")
            
        agent.tools["vector_search_tool"] = mock_vs_tool_chunks
        
        res, tools = agent.run("Find research on ZXQ-9999.")
        
        assert isinstance(res, LiteratureResearchOutput)
        assert res.no_evidence_found is False
        assert res.findings == "Agent failed to synthesize retrieved evidence."
        assert any("Agent exceeded max iterations" in l for l in res.limitations)