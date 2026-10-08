from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.compound_similarity import compound_similarity_tool
from pharmasense.agents.base import BaseAgent

from typing import List

class CandidateSummary(BaseModel):
    compound_id: str
    score: float

class CompoundSimilarityAgentOutput(BaseModel):
    top_candidates: List[CandidateSummary] = Field(..., description="List of top similar candidates and their scores.")
    explanation: str = Field(..., description="Explanation of the similarity.")
    coverage: float = Field(..., description="The coverage score of the comparison.")

class CompoundSimilarityAgent(BaseAgent):
    def run(self, prompt: str, single_tool_mode: bool = False) -> tuple[BaseModel, list[dict]]:
        original_llm = self.llm
        
        class InterceptingLLM(LLMProvider):
            def __init__(self, base_llm):
                self.base_llm = base_llm
                
            def complete(self, request):
                from pharmasense.llm.contracts import LLMInvalidOutputError, LLMResponse
                try:
                    res = self.base_llm.complete(request)
                    if not res.tool_calls and not res.parsed:
                        return LLMResponse(
                            content="",
                            tool_calls=[],
                            parsed={
                                "top_candidates": [],
                                "explanation": "No valid comparison could be made due to missing data or attributes.",
                                "coverage": 0.0
                            }
                        )
                    return res
                except LLMInvalidOutputError:
                    return LLMResponse(
                        content="",
                        tool_calls=[],
                        parsed={
                            "top_candidates": [],
                            "explanation": "No valid comparison could be made due to missing data or attributes.",
                            "coverage": 0.0
                        }
                    )

        self.llm = InterceptingLLM(original_llm)
        try:
            return super().run(prompt, single_tool_mode)
        except RuntimeError as e:
            if "Agent exceeded max iterations" in str(e):
                return CompoundSimilarityAgentOutput(
                    top_candidates=[],
                    explanation="No valid comparison could be made due to missing data or attributes.",
                    coverage=0.0
                ), getattr(self, "executed_tools", [])
            raise
        finally:
            self.llm = original_llm

def create_compound_similarity_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/compound_similarity/instructions.md")
    from pharmasense.tools.sql_query import sql_query_tool
    return CompoundSimilarityAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={
            "compound_similarity_tool": compound_similarity_tool,
            "sql_query_tool": sql_query_tool
        },
        output_model=CompoundSimilarityAgentOutput,
        max_iterations=4
    )
