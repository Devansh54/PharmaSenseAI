import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch

from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.config import GroqAdapterConfig
from pharmasense.llm.gateway import LLMGateway
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.api.models import AnalysisRequest
from pharmasense.tools.vector_search import VectorSearchOutput
from pharmasense.agents.trial import TrialDataAnalystOutput
from pharmasense.agents.literature import LiteratureResearchOutput
from pharmasense.agents.report import ReportWriterOutput

class MockQ5GroqClient:
    def __init__(self, mode="success_empty"):
        self.chat = MagicMock()
        self.chat.completions.create.side_effect = self.create_completion
        self.call_count = 0
        self.mode = mode
        
    def create_completion(self, **kwargs):
        self.call_count += 1
        mock_choice = MagicMock()
        
        msgs = kwargs.get("messages", [])
        system_prompt = msgs[0].get("content", "") if msgs else ""
        prompt = msgs[-1].get("content", "") if msgs else ""
        
        if "Trial Data Analyst" in system_prompt:
            if "Tool 'sql_query_tool' returned" in prompt:
                # 2nd iteration: return empty result
                tc = MagicMock()
                tc.id = "call_1_out"
                tc.function.name = "TrialDataAnalystOutput"
                tc.function.arguments = json.dumps({"summary": "No matching structured records found.", "limitations": ["No results found for ZXQ-9999."], "no_evidence_found": True})
                mock_choice.message.tool_calls = [tc]
                mock_choice.message.content = None
            else:
                tc = MagicMock()
                tc.id = "call_1"
                tc.function.name = "sql_query_tool"
                tc.function.arguments = '{"query_id": "trials_by_compound", "parameters": {"compound_id": "ZXQ-9999"}}'
                mock_choice.message.tool_calls = [tc]
                mock_choice.message.content = None
                
        elif "Literature Research" in system_prompt:
            print("LIT PROMPT:", repr(prompt))
            if "Tool 'vector_search_tool' returned" in prompt:
                if self.mode == "success_empty":
                    tc = MagicMock()
                    tc.id = "call_2_out"
                    tc.function.name = "LiteratureResearchOutput"
                    tc.function.arguments = json.dumps({"findings": "No relevant literature found.", "citations": [], "no_evidence_found": True})
                    mock_choice.message.tool_calls = [tc]
                    mock_choice.message.content = None
                else:
                    # simulate failure by just returning garbage text, which will loop until iteration limit
                    mock_choice.message.content = "I failed to do the task."
                    mock_choice.message.tool_calls = None
            else:
                tc = MagicMock()
                tc.id = "call_2"
                tc.function.name = "vector_search_tool"
                tc.function.arguments = '{"query": "ZXQ-9999"}'
                mock_choice.message.tool_calls = [tc]
                mock_choice.message.content = None
                
        elif "Report Writer" in system_prompt:
            # Report Writer
            if self.mode == "success_empty":
                mock_choice.message.content = "No cited evidence was available to resolve because both upstream specialists reported no results."
                mock_choice.message.tool_calls = None
            else:
                mock_choice.message.content = "No cited evidence was available to resolve because one specialist failed."
                mock_choice.message.tool_calls = None
                
        elif "OutputGuardrailNode" in system_prompt or "verify that all claims" in system_prompt:
            # Let it pass
            tc = MagicMock()
            tc.id = "call_guard"
            tc.function.name = "ReviewDecisionOut"
            tc.function.arguments = json.dumps({"is_valid": True, "reasoning": "Ok", "feedback": ""})
            mock_choice.message.tool_calls = [tc]
            mock_choice.message.content = None
        elif "Router/Planner" in system_prompt:
            tc = MagicMock()
            tc.id = "planner_call"
            tc.function.name = "Plan"
            tc.function.arguments = json.dumps({"workflow_type": "parallel", "selected_specialists": ["Trial Data Analyst", "Literature Research"], "task_descriptions": {"Trial Data Analyst": prompt, "Literature Research": prompt}, "resolved_entities": {}})
            mock_choice.message.tool_calls = [tc]
            mock_choice.message.content = None
        else:
            print("UNKNOWN AGENT SYSTEM PROMPT:", repr(system_prompt))
            mock_choice.message.content = "Unknown agent."
            mock_choice.message.tool_calls = None
            
        mock_choice.finish_reason = "stop"
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage.prompt_tokens = 10
        mock_completion.usage.completion_tokens = 20
        return mock_completion

from pharmasense.tools.vector_search import VectorSearchInput, VectorSearchOutput
from pharmasense.tools.sql_query import SqlQueryInput

def mock_vector_search_tool(session: Session, input_data: VectorSearchInput, embedder=None) -> VectorSearchOutput:
    return VectorSearchOutput(chunks=[], index_version="mock-v1")

def mock_sql_query_tool(session: Session, input_data: SqlQueryInput) -> dict:
    return {"results": [], "query_name": "trials_by_compound"}

from pharmasense.api.main import create_analysis
from pharmasense.api.models import AnalysisRequest
import asyncio

def test_q5_e2e_success_empty():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockQ5GroqClient(mode="success_empty")
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)
        
        with patch('pharmasense.agents.literature.vector_search_tool', new=mock_vector_search_tool):
            with patch('pharmasense.agents.trial.sql_query_tool', new=mock_sql_query_tool):
                req = AnalysisRequest(user_prompt="Is there any evidence for the unknown compound ZXQ-9999 in the available research documents or structured trial data? Search the relevant available sources and cite matching records if any exist. If no relevant evidence is found, explicitly report no evidence. Do not invent compound associations, research findings, or citations.")
                
                async def run_req():
                    return await create_analysis(req, db=session, gateway=gateway)
                
                res = asyncio.run(run_req())
                
                print("SUCCESS EMPTY RESULT:")
                print("Status:", res.status)
                assert res.status == "no_evidence"

def test_q5_e2e_failure():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockQ5GroqClient(mode="failure")
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)
        
        def mock_vector_search_fail(session: Session, input_data: VectorSearchInput, embedder=None) -> VectorSearchOutput:
            raise RuntimeError("Database connection lost.")
            
        with patch('pharmasense.agents.literature.vector_search_tool', new=mock_vector_search_fail):
            with patch('pharmasense.agents.trial.sql_query_tool', new=mock_sql_query_tool):
                req = AnalysisRequest(user_prompt="Is there any evidence for the unknown compound ZXQ-9999 in the available research documents or structured trial data? Search the relevant available sources and cite matching records if any exist. If no relevant evidence is found, explicitly report no evidence. Do not invent compound associations, research findings, or citations.")
                
                async def run_req():
                    return await create_analysis(req, db=session, gateway=gateway)
                
                res = asyncio.run(run_req())
                
                print("FAILURE RESULT:")
                print("Status:", res.status)
                assert res.status == "failed"

if __name__ == "__main__":
    test_q5_e2e_success_empty()
    print("-" * 80)
    test_q5_e2e_failure()
