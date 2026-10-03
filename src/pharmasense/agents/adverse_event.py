from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.ae_classifier import ae_severity_classifier_tool
from pharmasense.tools.sql_query import sql_query_tool
from pharmasense.agents.base import BaseAgent

class AETriageOutput(BaseModel):
    explanation: str = Field(..., description="Explanation of the adverse event status.")
    final_severity: str = Field(..., description="The calculated severity.")
    final_seriousness: Optional[str] = Field(..., description="The final seriousness, strictly matching the tool output. Null if unknown.")
    requires_review: bool = Field(..., description="Whether this event requires human review.")

def create_ae_triage_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/ae_triage/instructions.md")
    return BaseAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={
            "sql_query_tool": sql_query_tool,
            "ae_severity_classifier_tool": ae_severity_classifier_tool
        },
        output_model=AETriageOutput,
    )
