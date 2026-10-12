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
from pharmasense.config import DATABASE_URL, GroqAdapterConfig, GatewayConfig, ANALYSIS_TIMEOUT_SECONDS
import os
from pharmasense.llm.contracts import LLMProviderError, LLMTimeoutError, LLMGatewayError
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


def _attach_cors_headers(request: Request, headers: dict) -> dict:
    origin = request.headers.get("origin")
    if origin and (origin in _allowed_origins or "*" in _allowed_origins):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Headers"] = "*"
        headers["Access-Control-Allow-Methods"] = "*"
    return headers


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    headers = _attach_cors_headers(request, dict(exc.headers or {}))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(Exception)
async def custom_unhandled_exception_handler(request: Request, exc: Exception):
    headers = _attach_cors_headers(request, {})
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers=headers,
    )


# Dependency for DB Session - reuse singleton engine to prevent connection pool churn
_engine = None


def get_engine():
    global _engine
    db_url = os.environ.get("EVAL_DATABASE_URL", DATABASE_URL)
    if _engine is None or str(_engine.url) != db_url:
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
            max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "5")),
        )
    return _engine


def get_db_session():
    with Session(get_engine()) as session:
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
    # 1. Input Guardrail Security Screening (always active in all modes)
    from pharmasense.validation.security import detect_injection
    if detect_injection(req.user_prompt):
        return AnalysisResponse(
            status="failed",
            findings="I cannot fulfill this request. Security screening detected prompt injection or unsafe instructions.",
            citations=[],
            limitations=["Request blocked by input guardrail security screening."],
            branch_outcomes={},
            escalation_reference=None,
            timing_sec=0.05,
            total_tokens=None,
            error_message="Guardrail blocked request: Prompt injection detected."
        )

    # 2. Opt-in Demo Recording Mode (PHARMASENSE_DEMO_MODE=true)
    from pharmasense.orchestration.demo_mode import handle_demo_analysis
    demo_response = handle_demo_analysis(req.user_prompt, db)
    if demo_response is not None:
        return demo_response

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
        state = await asyncio.wait_for(asyncio.to_thread(run_graph), timeout=ANALYSIS_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis exceeded overall deadline ({ANALYSIS_TIMEOUT_SECONDS}s)"
        )
    except LLMTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"LLM provider request timed out: {str(exc)}"
        )
    except LLMProviderError as exc:
        err_msg = str(exc)
        if "rate" in err_msg.lower() or "429" in err_msg or "quota" in err_msg.lower():
            raise HTTPException(
                status_code=429,
                detail=f"LLM provider rate limit exceeded: {err_msg}"
            )
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider unavailable: {err_msg}"
        )
    except Exception as exc:
        err_msg = str(exc)
        if "rate" in err_msg.lower() or "429" in err_msg or "quota" in err_msg.lower():
            raise HTTPException(
                status_code=429,
                detail=f"LLM provider rate limit exceeded: {err_msg}"
            )
        if "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
            raise HTTPException(
                status_code=504,
                detail=f"Analysis timed out: {err_msg}"
            )
        raise HTTPException(
            status_code=503,
            detail=f"Analysis execution failed: {err_msg}"
        )
    
    end_time = time.time()
    latency = end_time - start_time
    
    errors = state.get("errors", [])
    report = state.get("final_report", {})
    
    if not report and errors:
        err_str = "|".join(errors)
        err_lower = err_str.lower()
        if "rate" in err_lower or "429" in err_lower or "quota" in err_lower:
            raise HTTPException(
                status_code=429,
                detail=f"LLM provider rate limit exceeded: {err_str}"
            )
        if "timeout" in err_lower or "timed out" in err_lower:
            raise HTTPException(
                status_code=504,
                detail=f"Upstream provider timeout: {err_str}"
            )
        if any(term in err_lower for term in ["failed", "unavailable", "service", "error"]):
            raise HTTPException(
                status_code=503,
                detail=f"Specialist orchestration failed: {err_str}"
            )
        raise HTTPException(status_code=422, detail=err_str)
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
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
def health_ready(db: Session = Depends(get_db_session)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail="Database unavailable")
