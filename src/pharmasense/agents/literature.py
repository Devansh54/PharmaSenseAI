from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.vector_search import vector_search_tool
from pharmasense.agents.base import BaseAgent

class LiteratureResearchOutput(BaseModel):
    findings: str = Field(..., description="Summary of evidence from literature.")
    citations: list[str] = Field(default_factory=list, description="List of document chunk references.")
    no_evidence_found: bool = Field(default=False, description="True if no supporting evidence was retrieved.")

def create_literature_research_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/literature_research/instructions.md")
    return BaseAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"vector_search_tool": vector_search_tool},
        output_model=LiteratureResearchOutput,
    )
