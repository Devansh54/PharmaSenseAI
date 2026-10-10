from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.citation import citation_formatter_tool
from pharmasense.agents.base import BaseAgent
from typing import List

class ReportWriterOutput(BaseModel):
    report_text: str = Field(..., description="The final synthesized report.")
    limitations_noted: list[str] = Field(default_factory=list, description="All limitations aggregated from specialists.")
    citations_resolved: list[dict] = Field(default_factory=list, description="List of resolved citation objects.")

    @field_validator("limitations_noted", "citations_resolved", mode="before")
    @classmethod
    def force_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

class ReportWriterAgent(BaseAgent):
    def validate_finalization(self, output_obj: BaseModel, executed_tools: List[dict]) -> None:
        if output_obj.citations_resolved:
            valid_chunk_ids = set()
            for t in executed_tools:
                if t["tool_name"] == "citation_formatter_tool" and "error" not in t["result"]:
                    for c in t["result"].get("citations", []):
                        if "chunk_id" in c:
                            valid_chunk_ids.add(c["chunk_id"])
            
            output_obj.citations_resolved = [
                c for c in output_obj.citations_resolved
                if c.get("chunk_id") in valid_chunk_ids
            ]

def create_report_writer_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/report_writer/instructions.md")
    return ReportWriterAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"citation_formatter_tool": citation_formatter_tool},
        output_model=ReportWriterOutput,
    )
