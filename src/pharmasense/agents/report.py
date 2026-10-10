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
    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, list[dict]]:
        original_complete = self.llm.complete
        last_raw_content = None
        
        def mock_complete(req):
            nonlocal last_raw_content
            try:
                res = original_complete(req)
                if not res.tool_calls and not res.parsed:
                    last_raw_content = res.content
                return res
            except Exception as exc:
                if type(exc).__name__ == "LLMInvalidOutputError":
                    last_raw_content = getattr(exc, "raw_content", None)
                raise
            
        self.llm.complete = mock_complete
        try:
            return super().run(prompt, single_tool_mode)
        except RuntimeError as e:
            if "Agent exceeded max iterations" in str(e):
                if last_raw_content:
                    import re
                    lims = []
                    matches = re.findall(r"Limitations?:\s*(.*)", prompt, re.IGNORECASE)
                    for m in matches:
                        m = m.strip()
                        if m.startswith("[") and m.endswith("]"):
                            import ast
                            try:
                                parsed_list = ast.literal_eval(m)
                                if isinstance(parsed_list, list):
                                    lims.extend(parsed_list)
                            except:
                                lims.append(m)
                        else:
                            lims.append(m)
                    
                    if not lims:
                        lims = ["Upstream specialists reported no results or execution failed."]
                    
                    return ReportWriterOutput(
                        report_text=last_raw_content.strip(),
                        limitations_noted=lims,
                        citations_resolved=[]
                    ), getattr(self, "executed_tools", [])
            raise
        finally:
            self.llm.complete = original_complete

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
