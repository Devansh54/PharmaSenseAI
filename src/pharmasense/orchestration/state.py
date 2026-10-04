from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field

class Plan(BaseModel):
    workflow_type: Literal["single", "sequential", "parallel"] = Field(
        ..., description="The required workflow pattern."
    )
    selected_specialists: List[str] = Field(
        ..., description="Must only contain approved agents: 'Trial Data Analyst', 'Literature Research', 'Adverse Event Triage', 'Compound Similarity'"
    )
    task_descriptions: Dict[str, str] = Field(
        ..., description="Maps selected specialist names to their specific instructions."
    )
    resolved_entities: Dict[str, str] = Field(
        default_factory=dict, description="Extracted IDs or terms (e.g., compound names)."
    )

def update_results(left: dict, right: dict) -> dict:
    if left is None:
        left = {}
    res = left.copy()
    if right:
        res.update(right)
    return res

def append_errors(left: list, right: list) -> list:
    if left is None:
        left = []
    if not right:
        return left
    return left + right

def append_tools(left: list, right: list) -> list:
    if left is None:
        left = []
    if not right:
        return left
    return left + right

class WorkflowState(TypedDict):
    request_id: str
    user_prompt: str
    plan: Optional[Plan]
    specialist_results: Annotated[Dict[str, Any], update_results]
    final_report: Optional[dict]
    errors: Annotated[List[str], append_errors]
    validation_feedback: Optional[str]
    evidence_repaired: bool
    actual_tools: Annotated[List[dict], append_tools]
