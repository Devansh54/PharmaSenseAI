from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.citation import citation_formatter_tool
from pharmasense.agents.base import BaseAgent

class ReportWriterOutput(BaseModel):
    report_text: str = Field(..., description="The final synthesized report.")
    limitations_noted: list[str] = Field(default_factory=list, description="All limitations aggregated from specialists.")
    citations_resolved: list[dict] = Field(default_factory=list, description="List of resolved citation objects.")

def create_report_writer_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/report_writer/instructions.md")
    return BaseAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"citation_formatter_tool": citation_formatter_tool},
        output_model=ReportWriterOutput,
    )
