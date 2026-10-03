from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.sql_query import sql_query_tool
from pharmasense.agents.base import BaseAgent

class TrialDataAnalystOutput(BaseModel):
    summary: str = Field(..., description="The summary of the trial/site/lab data findings.")
    limitations: list[str] = Field(default_factory=list, description="Any data limitations encountered.")

def create_trial_data_analyst(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/trial_data_analyst/instructions.md")
    return BaseAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"sql_query_tool": sql_query_tool},
        output_model=TrialDataAnalystOutput,
    )
