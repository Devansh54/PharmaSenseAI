from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.vector_search import vector_search_tool
from pharmasense.agents.base import BaseAgent
from typing import List

class LiteratureResearchOutput(BaseModel):
    findings: str = Field(..., description="Summary of evidence from literature.")
    citations: list[str] = Field(default_factory=list, description="List of document chunk references.")
    no_evidence_found: bool = Field(default=False, description="True if no supporting evidence was retrieved.")

    @field_validator("citations", mode="before")
    @classmethod
    def force_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v

    @field_validator("no_evidence_found", mode="before")
    @classmethod
    def force_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "yes", "1")
        return bool(v)

class LiteratureResearchAgent(BaseAgent):
    def validate_finalization(self, output_obj: BaseModel, executed_tools: List[dict]) -> None:
        if output_obj.citations:
            valid_chunk_ids = set()
            for t in executed_tools:
                if t["tool_name"] == "vector_search_tool" and "error" not in t["result"]:
                    for c in t["result"].get("chunks", []):
                        if "chunk_id" in c:
                            valid_chunk_ids.add(c["chunk_id"])
            
            output_obj.citations = [
                c for c in output_obj.citations
                if c in valid_chunk_ids
            ]

    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, list[dict]]:
        try:
            return super().run(prompt, single_tool_mode)
        except RuntimeError as e:
            if "Agent exceeded max iterations" in str(e):
                return LiteratureResearchOutput(
                    findings="No relevant literature found or could not execute search.",
                    citations=[],
                    no_evidence_found=True
                ), getattr(self, "executed_tools", [])
            raise

def create_literature_research_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/literature_research/instructions.md")
    return LiteratureResearchAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"vector_search_tool": vector_search_tool},
        output_model=LiteratureResearchOutput,
    )
