from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session
from pharmasense.llm.contracts import LLMProvider
from pharmasense.tools.compound_similarity import compound_similarity_tool
from pharmasense.agents.base import BaseAgent

class CandidateSummary(BaseModel):
    compound_id: str
    score: float

class CompoundSimilarityAgentOutput(BaseModel):
    top_candidates: List[CandidateSummary] = Field(default_factory=list, description="List of top similar candidates and their scores.")
    explanation: str = Field(..., description="Explanation of the similarity.")
    coverage: float = Field(..., description="The coverage score of the comparison.")
    score: float = Field(default=0.0, description="The calculated attribute similarity score.")

    @model_validator(mode="before")
    @classmethod
    def populate_score_or_candidates(cls, data):
        if isinstance(data, dict):
            if "top_candidates" in data and data["top_candidates"] and "score" not in data:
                c0 = data["top_candidates"][0]
                if isinstance(c0, dict) and "score" in c0:
                    data["score"] = float(c0["score"])
                elif hasattr(c0, "score"):
                    data["score"] = float(c0.score)
            if "score" in data and "top_candidates" not in data:
                data["top_candidates"] = []
        return data

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
                                "score": 0.0,
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
                            "score": 0.0,
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
                    score=0.0,
                    explanation="No valid comparison could be made due to missing data or attributes.",
                    coverage=0.0
                ), getattr(self, "executed_tools", [])
            raise
        finally:
            self.llm = original_llm

def create_compound_similarity_agent(session: Session, llm: LLMProvider) -> BaseAgent:
    instruction_path = Path("agent_specs/compound_similarity/instructions.md")
    return CompoundSimilarityAgent(
        session=session,
        llm=llm,
        system_instruction=instruction_path.read_text(encoding="utf-8"),
        tools={
            "compound_similarity_tool": compound_similarity_tool
        },
        output_model=CompoundSimilarityAgentOutput,
        max_iterations=3
    )
