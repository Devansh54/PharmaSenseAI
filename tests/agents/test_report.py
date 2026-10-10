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
