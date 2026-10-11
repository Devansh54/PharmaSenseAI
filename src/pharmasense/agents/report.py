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


import ast
import re

_FAILURE_PATTERNS = [
    r"\bfailed\b",
    r"\bfailure\b",
    r"\berror(?:s)?\b",
    r"could not execute",
    r"connection lost",
    r"timeout",
    r"exceeded max iterations",
]

_NO_EVIDENCE_PATTERNS = [
    r"no matching (?:structured )?records",
    r"no relevant literature",
    r"no results found",
    r"no data found",
    r"no evidence found",
    r"no evidence was found",
    r"no citable evidence",
    r"no matching records",
    r"no_evidence_found\s*[:=]\s*true",
    r"reported no results",
]

_POSITIVE_PATTERNS = [
    r"\b(?:found|identified)\s+[1-9]\d*\b",
    r"\b\d+\s+(?:trials?|records?|papers?|documents?|studies|publications?)\b",
    r"\befficacy\b",
    r"\bsignificant (?:improvement|reduction)\b",
    r"\badverse events?:\s*\[.+\]",
    r"\bsimilar compounds?:\s*\[.+\]",
]


def _is_upstream_no_evidence(prompt: str) -> bool:
    if not prompt:
        return False

    prompt_lower = prompt.lower()

    for pat in _FAILURE_PATTERNS:
        if re.search(pat, prompt_lower):
            return False

    section_pattern = (
        r"(?:---\s*[A-Za-z0-9_\s]+?\s*Findings\s*---|(?:\bTrial(?: Data)? Analyst|\bLiterature Research|\bAdverse Event(?: Triage)?|\bCompound Similarity)\s*:)"
    )
    splits = re.split(section_pattern, prompt, flags=re.IGNORECASE)
    specialist_sections = [s.strip() for s in splits[1:] if s.strip()]

    if specialist_sections:
        for sec in specialist_sections:
            sec_lower = sec.lower()
            has_no_ev = any(re.search(pat, sec_lower) for pat in _NO_EVIDENCE_PATTERNS)
            if not has_no_ev:
                return False
            has_pos = any(re.search(pat, sec_lower) for pat in _POSITIVE_PATTERNS)
            if has_pos:
                return False
        return True
    else:
        has_no_ev = any(re.search(pat, prompt_lower) for pat in _NO_EVIDENCE_PATTERNS)
        has_pos = any(re.search(pat, prompt_lower) for pat in _POSITIVE_PATTERNS)
        return has_no_ev and not has_pos


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
                lims = []
                matches = re.findall(r"Limitations?:\s*(.*)", prompt, re.IGNORECASE)
                for m in matches:
                    m = m.strip()
                    if m.startswith("[") and m.endswith("]"):
                        try:
                            parsed_list = ast.literal_eval(m)
                            if isinstance(parsed_list, list):
                                lims.extend(parsed_list)
                        except Exception:
                            lims.append(m)
                    else:
                        lims.append(m)

                if last_raw_content:
                    report_text = last_raw_content.strip()
                    if not lims:
                        lims = ["Upstream specialists reported no results or execution failed."]
                elif _is_upstream_no_evidence(prompt):
                    if not lims:
                        lims = ["Upstream specialists reported no results or execution failed."]
                    report_text = (
                        "No citable evidence was found. "
                        "Both upstream specialists reported no results for the requested query."
                    )
                else:
                    report_text = (
                        "Report synthesis could not be completed. "
                        "The Report Writer exceeded its maximum iteration limit before producing valid output."
                    )
                    failure_limitation = (
                        "Report Writer exceeded maximum iterations before producing valid output."
                    )
                    if failure_limitation not in lims:
                        lims.append(failure_limitation)

                return ReportWriterOutput(
                    report_text=report_text,
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
