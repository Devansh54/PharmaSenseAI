from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.ae_classifier import ae_severity_classifier_tool
from pharmasense.tools.sql_query import sql_query_tool
from pharmasense.tools.escalation import escalation_notifier_tool
from pharmasense.agents.base import BaseAgent

class AETriageOutput(BaseModel):
    explanation: str = Field(..., description="Explanation of the adverse event status.")
    final_severity: str = Field(..., description="The calculated severity.")
    final_seriousness: Optional[str] = Field(..., description="The final seriousness, strictly matching the tool output. Null if unknown.")
    requires_review: bool = Field(..., description="Whether this event requires human review.")

class AETriageAgent(BaseAgent):
    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, list[dict]]:
        return super().run(prompt, single_tool_mode=False)

    def validate_finalization(self, output_obj: BaseModel, executed_tools: list[dict]) -> None:
        has_serious = getattr(output_obj, "final_seriousness", None) == "Serious"
        if not has_serious:
            for t in executed_tools:
                if t["tool_name"] == "sql_query_tool":
                    for row in t.get("result", {}).get("results", []):
                        if row.get("seriousness") == "Serious":
                            has_serious = True
                            break

        if has_serious:
            classifier_called = any(t["tool_name"] == "ae_severity_classifier_tool" for t in executed_tools)
            if not classifier_called:
                raise ValueError("Finalization rejected: Serious AE detected. You MUST call ae_severity_classifier_tool to verify seriousness.")

            escalation_called = any(t["tool_name"] == "escalation_notifier_tool" for t in executed_tools)
            if not escalation_called:
                raise ValueError("Finalization rejected: Serious AE detected. You MUST call escalation_notifier_tool to persist the human-review task.")

def create_ae_triage_agent(session: Session, llm: LLMProvider, task_desc: str = "") -> BaseAgent:
    instruction_path = Path("agent_specs/ae_triage/instructions.md")
    full_instruction = instruction_path.read_text(encoding="utf-8")
    if "## Examples" in full_instruction:
        full_instruction = full_instruction.split("## Examples")[0].strip()

    return AETriageAgent(
        session=session,
        llm=llm,
        system_instruction=full_instruction,
        tools={
            "sql_query_tool": sql_query_tool,
            "ae_severity_classifier_tool": ae_severity_classifier_tool,
            "escalation_notifier_tool": escalation_notifier_tool
        },
        output_model=AETriageOutput,
        max_iterations=6
    )
