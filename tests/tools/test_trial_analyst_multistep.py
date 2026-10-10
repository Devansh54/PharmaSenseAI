import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.config import DATABASE_URL
from pharmasense.agents.trial import create_trial_data_analyst, TrialDataAnalystOutput
from pharmasense.llm.contracts import LLMRequest, Message, ToolCall, LLMResponse

class MockLLM:
    def __init__(self):
        self.call_count = 0
        self.requests = []
        
    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.call_count += 1
        
        if self.call_count == 1:
            # Step 1: Call trials_by_compound
            tool_call = ToolCall(
                id="call_1",
                name="sql_query_tool",
                arguments={"query_id": "trials_by_compound", "parameters": {"compound_id": "DKU-1001"}}
            )
            return LLMResponse(
                content="",
                tool_calls=[tool_call],
                parsed=None,
                provider_metadata={}
            )
        elif self.call_count == 2:
            # Step 2: Call site_enrollment for TRL-0001
            tool_call = ToolCall(
                id="call_2",
                name="sql_query_tool",
                arguments={"query_id": "site_enrollment", "parameters": {"trial_id": "TRL-0001"}}
            )
            return LLMResponse(
                content="",
                tool_calls=[tool_call],
                parsed=None,
                provider_metadata={}
            )
        else:
            # Step 3: Return final output
            return LLMResponse(
                content="{}",
                tool_calls=[],
                parsed=TrialDataAnalystOutput(summary="Found trial and sites.", limitations=[]),
                provider_metadata={}
            )

def test_multistep_trial_analyst():
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        llm = MockLLM()
        task_desc = "User Prompt: Summarize the available clinical-trial and research findings for compound DKU-1001.\n\nINSTRUCTION: You MUST use the `trials_by_compound` query_id first to retrieve all clinical trials associated with the requested compound. If the user also asks for associated sites, you may subsequently use `site_enrollment` for the identified trials."
        
        agent = create_trial_data_analyst(session, llm, task_desc=task_desc)
        result, tools = agent.run("test prompt")
        
        assert llm.call_count == 3
        assert result.summary == "Found trial and sites."
        assert len(tools) == 2
        assert tools[0]["tool_name"] == "sql_query_tool"
        assert tools[1]["tool_name"] == "sql_query_tool"

def test_agent_hallucinates_output_schema_as_tool():
    class HallucinatingLLM:
        def __init__(self):
            self.call_count = 0
            
        def complete(self, request: LLMRequest) -> LLMResponse:
            self.call_count += 1
            tc = ToolCall(
                id=f'call_{self.call_count}',
                name='TrialDataAnalystOutput',
                arguments={'summary': 'Directly returned as tool', 'limitations': ['None']}
            )
            return LLMResponse(content='', tool_calls=[tc], parsed=None, provider_metadata={})

    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        llm = HallucinatingLLM()
        agent = create_trial_data_analyst(session, llm)
        result, tools = agent.run("test prompt")
        
        # It should intercept the tool call on the first try and return!
        assert llm.call_count == 1
        assert result.summary == "Directly returned as tool"
        assert len(tools) == 0

def test_agent_invalid_json_retry():
    class InvalidJsonLLM:
        def __init__(self):
            self.call_count = 0
            
        def complete(self, request: LLMRequest) -> LLMResponse:
            self.call_count += 1
            if self.call_count == 1:
                from pharmasense.llm.contracts import LLMInvalidOutputError
                raise LLMInvalidOutputError("Structured output is not valid JSON")
            else:
                from pharmasense.agents.trial import TrialDataAnalystOutput
                return LLMResponse(
                    content='{}',
                    tool_calls=[],
                    parsed=TrialDataAnalystOutput(summary='Fixed on retry', limitations=[]),
                    provider_metadata={}
                )

    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        llm = InvalidJsonLLM()
        agent = create_trial_data_analyst(session, llm)
        result, tools = agent.run("test prompt")
        
        assert llm.call_count == 2
        assert result.summary == "Fixed on retry"

def test_trial_analyst_empty_result_handling():
    class MockEmptyResultLLM:
        def __init__(self):
            self.call_count = 0
            
        def complete(self, request: LLMRequest) -> LLMResponse:
            self.call_count += 1
            
            if self.call_count == 1:
                tc = ToolCall(
                    id="call_1",
                    name="sql_query_tool",
                    arguments={"query_id": "trials_by_compound", "parameters": {"compound_id": "ZXQ-9999"}}
                )
                return LLMResponse(content="", tool_calls=[tc], parsed=None, provider_metadata={})
            elif self.call_count == 2:
                # To simulate the fix, the LLM should output the final response on iteration 2 instead of calling again.
                from pharmasense.agents.trial import TrialDataAnalystOutput
                return LLMResponse(
                    content="",
                    tool_calls=[],
                    parsed=TrialDataAnalystOutput(summary="No matching structured records found.", limitations=["No results found for ZXQ-9999."]),
                    provider_metadata={}
                )
            
            raise RuntimeError("Agent looped instead of returning structured output")

    db_url = os.environ.get("EVAL_DATABASE_URL", "sqlite://")
    engine = create_engine(db_url)
    with Session(engine) as session:
        llm = MockEmptyResultLLM()
        agent = create_trial_data_analyst(session, llm)
        result, tools = agent.run("Find trials for ZXQ-9999.")
        
        assert llm.call_count == 2
        assert "No matching structured records" in result.summary
        assert len(tools) == 1
        assert tools[0]["tool_name"] == "sql_query_tool"
