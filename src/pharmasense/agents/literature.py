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
    limitations: list[str] = Field(default_factory=list, description="Any search limitations or execution errors encountered.")

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
            res, tools = super().run(prompt, single_tool_mode)
            tool_errors = [t["result"]["error"] for t in tools if isinstance(t.get("result"), dict) and t.get("result", {}).get("error")]
            if hasattr(res, "limitations") and tool_errors:
                res.limitations.extend(tool_errors)
            return res, tools
        except RuntimeError as e:
            if "Agent exceeded max iterations" in str(e):
                tools = getattr(self, "executed_tools", [])
                tool_errors = [t["result"]["error"] for t in tools if isinstance(t.get("result"), dict) and t.get("result", {}).get("error")]
                return LiteratureResearchOutput(
                    findings="No relevant literature found or could not execute search.",
                    citations=[],
                    no_evidence_found=True,
                    limitations=["Agent exceeded max iterations before producing valid output."] + tool_errors
                ), tools
            raise

    def check_early_termination(self) -> BaseModel | None:
        if not hasattr(self, "executed_tools") or not self.executed_tools:
            return None
            
        last_tool = self.executed_tools[-1]
        if last_tool["tool_name"] == "vector_search_tool":
            res = last_tool["result"]
            if not res.get("error") and res.get("chunks") is not None and len(res["chunks"]) == 0:
                return LiteratureResearchOutput(
                    findings="No relevant literature found.",
                    citations=[],
                    no_evidence_found=True
                )
        return None

def create_literature_research_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/literature_research/instructions.md")
    return LiteratureResearchAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"vector_search_tool": vector_search_tool},
        output_model=LiteratureResearchOutput,
    )
