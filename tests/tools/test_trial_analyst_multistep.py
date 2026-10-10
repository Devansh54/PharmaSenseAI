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
