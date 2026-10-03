from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.compound_similarity import compound_similarity_tool
from pharmasense.agents.base import BaseAgent

class CompoundSimilarityAgentOutput(BaseModel):
    score: float = Field(..., description="The calculated attribute similarity score.")
    explanation: str = Field(..., description="Explanation of the similarity.")
    coverage: float = Field(..., description="The coverage score.")

def create_compound_similarity_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/compound_similarity/instructions.md")
    return BaseAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={"compound_similarity_tool": compound_similarity_tool},
        output_model=CompoundSimilarityAgentOutput,
    )
