import time
import uuid
import asyncio
import datetime
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from pharmasense.api.models import (
    AnalysisRequest, AnalysisResponse, CitationOut,
    EvidenceOut, ReviewDecisionIn, ReviewTaskOut, ReviewDecisionOut
)
from pharmasense.db.models import DocumentChunk, ReviewTask, ReviewDecision
from pharmasense.config import DATABASE_URL, GroqAdapterConfig, GatewayConfig
import os
from pharmasense.llm.gateway import LLMGateway
from pharmasense.llm.groq_adapter import GroqAdapter
from pharmasense.llm.budget import BudgetEnforcingGateway
from fastapi.middleware.cors import CORSMiddleware
from pharmasense.orchestration.graph import build_orchestration_graph
from pharmasense.observability.telemetry import TelemetryManager

app = FastAPI(title="PharmaSense AI API")

DEFAULT_ALLOWED_ORIGINS = [
    "https://devansh54.github.io",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

_raw_allowed = os.environ.get("ALLOWED_ORIGINS")
_allowed_origins = (
    [origin.strip() for origin in _raw_allowed.split(",") if origin.strip()]
    if _raw_allowed
    else DEFAULT_ALLOWED_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency for DB Session
def get_db_session():
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    engine = create_engine(db_url)
    with Session(engine) as session:
        yield session

def build_gateway():
    model = os.environ.get("LLM_MODEL", os.environ.get("PHARMASENSE_LLM_MODEL", "qwen/qwen3.8-27b"))
    config = GroqAdapterConfig(model=model)
    adapter = GroqAdapter(config=config)
    gateway_config = GatewayConfig(model=model)
    return BudgetEnforcingGateway(inner=LLMGateway(adapter, config=gateway_config))

@app.post("/v1/analyses", response_model=AnalysisResponse)
async def create_analysis(
    req: AnalysisRequest, 
    db: Session = Depends(get_db_session),
    gateway = Depends(build_gateway)
):
    graph = build_orchestration_graph(db, gateway)
    
    request_id = req.request_id or str(uuid.uuid4())
    start_time = time.time()
    
    def run_graph():
        return graph.invoke({
            "request_id": request_id,
            "session_id": req.session_id or "api",
            "user_prompt": req.user_prompt
        })
    
    try:
        state = await asyncio.wait_for(asyncio.to_thread(run_graph), timeout=300.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis exceeded overall deadline")
    
    end_time = time.time()
    latency = end_time - start_time
    
    errors = state.get("errors", [])
    report = state.get("final_report", {})
    
    if not report and errors:
        raise HTTPException(status_code=422, detail="|".join(errors))
    if not report:
        raise HTTPException(status_code=500, detail="Orchestration returned no report")
        
    findings = report.get("report_content", report.get("report_text", "No report generated."))
    
    limitations = report.get("limitations_noted", report.get("limitations", []))
    
    status_str = "success"
    specialist_results = state.get("specialist_results", {})
    
    num_required = 0
    num_success = 0
    num_no_evidence = 0
    num_failed = 0
    
    plan = state.get("plan")
    if plan and hasattr(plan, "selected_specialists"):
        required_specialists = plan.selected_specialists
    elif specialist_results:
        required_specialists = list(specialist_results.keys())
    else:
        required_specialists = []
        
    for spec in required_specialists:
        num_required += 1
        res = specialist_results.get(spec)
        if not isinstance(res, dict):
            num_failed += 1
            continue
            
        import json
        dump = json.dumps(res)
        
        spec_limitations = res.get("limitations", [])
        tool_errors = [
            l for l in spec_limitations
            if any(term in str(l).lower() for term in ["error", "failed", "failure", "timeout", "exception", "exceeded max iterations", "could not execute"])
        ]
        
        # Check explicit execution failures
        if "Agent exceeded max iterations" in dump or "could not execute search" in dump or tool_errors:
            num_failed += 1
        # Check no evidence
        elif res.get("no_evidence_found") is True or "No data found" in str(res.get("summary", "")) or "No matching structured" in str(res.get("summary", "")) or "No results found" in str(res.get("summary", "")):
            num_no_evidence += 1
        else:
            num_success += 1

    if num_required > 0:
        if num_success > 0 and num_failed == 0:
            status_str = "success"
        elif num_success > 0 and num_failed > 0:
            status_str = "partial_success"
        elif num_success == 0 and num_failed == 0 and num_no_evidence > 0:
            status_str = "no_evidence"
        else:
            status_str = "failed"
    else:
        if errors:
            status_str = "partial_success"
        elif any("No_evidence_found = True" in l for l in limitations) or "no evidence was identified" in findings.lower() or "no actionable evidence" in findings.lower() or "no clinical trials" in findings.lower():
            status_str = "no_evidence"
        else:
            status_str = "success"
            
    if errors and status_str == "success":
        status_str = "partial_success"

    citations_data = report.get("citations_resolved", [])
    citations = [
        CitationOut(claim=c.get("claim", ""), citations=c.get("citations", []), invalid_chunk_ids=c.get("invalid_chunk_ids", []))
        for c in citations_data
    ]
    
    if not citations and status_str != "no_evidence":
        specialist_citations = []
        for name, res in specialist_results.items():
            if isinstance(res, dict) and "citations" in res and isinstance(res["citations"], list):
                specialist_citations.extend(res["citations"])
        
        lit_res = specialist_results.get("Literature Research", {})
        lit_no_evidence = isinstance(lit_res, dict) and lit_res.get("no_evidence_found") is True
        
        if not lit_no_evidence:
            for tool_run in state.get("actual_tools", []):
                if tool_run.get("tool_name") == "vector_search_tool":
                    tool_result = tool_run.get("result", {})
                    if isinstance(tool_result, dict) and "chunks" in tool_result:
                        for chunk in tool_result.get("chunks", []):
                            if "chunk_id" in chunk:
                                specialist_citations.append(chunk["chunk_id"])
        
        unique_citations = list(dict.fromkeys(specialist_citations))
        if unique_citations:
            citations.append(CitationOut(
                claim="Evidence retrieved by specialists",
                citations=unique_citations,
                invalid_chunk_ids=[]
            ))
        
    branch_outcomes = {
        name: res.get("summary") or res.get("findings") or res.get("explanation") or str(res)
        for name, res in state.get("specialist_results", {}).items()
    }
    
    escalation_reference = None
    for tool_run in state.get("actual_tools", []):
        if tool_run.get("tool_name") == "escalation_notifier_tool":
            tool_res = tool_run.get("result", {})
            if isinstance(tool_res, dict) and "task_id" in tool_res:
                escalation_reference = tool_res["task_id"]
                break
                
    db.commit()
    
    return AnalysisResponse(
        status=status_str,
        findings=findings,
        citations=citations,
        limitations=limitations,
        branch_outcomes=branch_outcomes,
        escalation_reference=escalation_reference,
        timing_sec=latency,
        total_tokens=None,
        error_message="|".join(errors) if errors else None
    )

@app.get("/v1/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: str, db: Session = Depends(get_db_session)):
    chunk = db.query(DocumentChunk).filter(DocumentChunk.chunk_id == evidence_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return EvidenceOut(
        evidence_id=chunk.chunk_id,
        content=chunk.chunk_text,
        metadata={
            "doc_id": chunk.doc_id,
            "compound_id": chunk.compound_id,
            "trial_id": chunk.trial_id,
            "doc_type": chunk.doc_type,
            "title": chunk.title
        }
    )

@app.get("/v1/reviews", response_model=list[ReviewTaskOut])
def list_reviews(db: Session = Depends(get_db_session)):
    tasks = db.query(ReviewTask).all()
    return [
        ReviewTaskOut(
            task_id=t.task_id,
            event_id=t.event_id,
            status=t.status,
            reason=t.reason,
            created_at=t.created_at.isoformat()
        ) for t in tasks
    ]

@app.get("/v1/reviews/{review_id}", response_model=ReviewTaskOut)
def get_review(review_id: str, db: Session = Depends(get_db_session)):
    t = db.query(ReviewTask).filter(ReviewTask.task_id == review_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewTaskOut(
        task_id=t.task_id,
        event_id=t.event_id,
        status=t.status,
        reason=t.reason,
        created_at=t.created_at.isoformat()
    )

@app.post("/v1/reviews/{review_id}/decisions", status_code=status.HTTP_201_CREATED)
def create_review_decision(review_id: str, dec_in: ReviewDecisionIn, db: Session = Depends(get_db_session)):
    t = db.query(ReviewTask).filter(ReviewTask.task_id == review_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Review not found")
        
    valid_transitions = {
        "pending": ["acknowledged", "resolved"],
        "acknowledged": ["resolved"]
    }
    
    decision_status = dec_in.decision.lower()
    
    if decision_status not in valid_transitions.get(t.status.lower(), []):
        raise HTTPException(status_code=409, detail=f"Invalid review transition from {t.status} to {decision_status}")
        
    t.status = decision_status.upper() if t.status.isupper() else decision_status
    db.commit()
    return {"status": "success"}

@app.get("/health/live")
def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db_session)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database unavailable")
