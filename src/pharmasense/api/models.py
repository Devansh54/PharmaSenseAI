from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class AnalysisRequest(BaseModel):
    user_prompt: str
    request_id: Optional[str] = None
    session_id: Optional[str] = None

class CitationOut(BaseModel):
    claim: str
    citations: List[str]
    invalid_chunk_ids: List[str] = []

class AnalysisResponse(BaseModel):
    status: str
    findings: str
    citations: List[CitationOut]
    limitations: List[str]
    branch_outcomes: Dict[str, Any]
    escalation_reference: Optional[str] = None
    timing_sec: Optional[float] = None
    total_tokens: Optional[int] = None
    error_message: Optional[str] = None

class EvidenceOut(BaseModel):
    evidence_id: str
    content: str
    metadata: Dict[str, Any]

class ReviewDecisionIn(BaseModel):
    reviewer_id: str
    decision: str
    comments: Optional[str] = None

class ReviewTaskOut(BaseModel):
    task_id: str
    event_id: str
    status: str
    reason: str
    created_at: str

class ReviewDecisionOut(BaseModel):
    decision_id: str
    task_id: str
    reviewer_id: str
    decision: str
    comments: Optional[str]
    created_at: str
