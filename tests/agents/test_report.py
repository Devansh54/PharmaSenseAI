import pytest
from pharmasense.llm.contracts import LLMProvider, LLMRequest, LLMResponse, ToolCall
from pharmasense.agents.report import create_report_writer_agent, ReportWriterOutput
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pharmasense.llm.gateway import LLMGateway
import json

class MockNoEvidenceLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0
        
    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        
        if self.call_count == 1:
            # Emulate the LLM formatting 'limitations_noted' as a string instead of a list,
            # and inventing a citation because it wasn't told not to.
            out_args = {
                "report_text": "No evidence was found for the compound ZXQ-9999.",
                "limitations_noted": "No matching structured records were found.",
                "citations_resolved": [{"doc_id": "invented", "title": "Invented Paper"}]
            }
            tc = ToolCall(id='1', name='ReportWriterOutput', arguments=out_args)
            return LLMResponse(content='', tool_calls=[tc], parsed=None)
            
        raise RuntimeError("Agent looped!")

def test_report_writer_no_evidence_handling():
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        gateway = LLMGateway(MockNoEvidenceLLM())
        agent = create_report_writer_agent(session, gateway)
        
        prompt = "Trial Analyst: No matching structured records were found."
        res, tools = agent.run(prompt)
        
        assert isinstance(res, ReportWriterOutput)
        assert "No evidence" in res.report_text
        # Ensure limitation was preserved and coerced to a list
        assert "No matching structured records" in res.limitations_noted[0]
        # Ensure hallucinated citation was stripped
        assert res.citations_resolved == []


def test_report_writer_conversational_json_rescue():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock
    
    class MockGroqClient:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0
            
        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()
            
            if self.call_count == 1:
                mock_choice.message.content = "Here is the final report since no data was found:\n```json\n{\n  \"report_text\": \"No evidence found.\",\n  \"limitations_noted\": [\"No records\"],\n  \"citations_resolved\": []\n}\n```"
                mock_choice.message.tool_calls = None
            else:
                raise RuntimeError("Agent looped unexpectedly")
                
            mock_choice.finish_reason = "stop"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 20
            return mock_completion

    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockGroqClient()
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)
        
        agent = create_report_writer_agent(session, gateway)
        res, tools = agent.run('Write a report based on empty findings.')
        
        assert "No evidence found." in res.report_text
        assert mock_client.call_count == 1


def test_report_writer_no_evidence_pure_text():
    from pharmasense.llm.groq_adapter import GroqAdapter
    from pharmasense.config import GroqAdapterConfig
    from unittest.mock import MagicMock
    
    class MockGroqClient:
        def __init__(self):
            self.chat = MagicMock()
            self.chat.completions.create.side_effect = self.create_completion
            self.call_count = 0
            
        def create_completion(self, **kwargs):
            self.call_count += 1
            mock_choice = MagicMock()
            
            mock_choice.message.content = "No cited evidence was available to resolve because both upstream specialists reported no results."
            mock_choice.message.tool_calls = None
                
            mock_choice.finish_reason = "stop"
            mock_completion = MagicMock()
            mock_completion.choices = [mock_choice]
            mock_completion.usage.prompt_tokens = 10
            mock_completion.usage.completion_tokens = 20
            return mock_completion

    engine = create_engine('sqlite://')
    with Session(engine) as session:
        mock_client = MockGroqClient()
        adapter = GroqAdapter(config=GroqAdapterConfig(api_key='fake', model='llama'), client=mock_client)
        gateway = LLMGateway(adapter)
        
        agent = create_report_writer_agent(session, gateway)
        prompt = "Trial Analyst:\nSummary: No matching structured records found.\nLimitations: ['No results found for ZXQ-9999.']\nLiterature Research:\nSummary: No relevant literature found."
        
        res, tools = agent.run(prompt)
        assert "No cited evidence" in res.report_text
        assert "No results found for ZXQ-9999." in res.limitations_noted
