import pytest
import json
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

from pharmasense.api.main import app, get_db_session, build_gateway
from pharmasense.db.models import Base, ReviewTask, DocumentChunk
from pharmasense.llm.gateway import LLMGateway

# We can mock the Gateway and the Session
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)

def override_get_db_session():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_db_session] = override_get_db_session

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        # Add a review task
        t = ReviewTask(
            task_id="REV-1234",
            event_id="AE-001",
            status="PENDING",
            reason="Serious AE",
            created_at=datetime.now(timezone.utc)
        )
        session.add(t)
        
        # Add a chunk
        from pharmasense.config import EMBEDDING_DIM
        c = DocumentChunk(
            chunk_id="CHUNK-001",
            doc_id="DOC-001",
            chunk_index=0,
            chunk_count=1,
            chunk_text="Test evidence content",
            token_count=10,
            content_hash="abc",
            embedding=[0.0] * EMBEDDING_DIM,
            embedding_model="test",
            index_version="v1",
            created_at=datetime.now(timezone.utc)
        )
        session.add(c)
        session.commit()

class MockGateway:
    def complete(self, req):
        pass

def override_build_gateway():
    return MockGateway()

app.dependency_overrides[build_gateway] = override_build_gateway

def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health_ready():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_evidence():
    response = client.get("/v1/evidence/CHUNK-001")
    assert response.status_code == 200
    data = response.json()
    assert data["evidence_id"] == "CHUNK-001"
    assert data["content"] == "Test evidence content"

def test_get_evidence_not_found():
    response = client.get("/v1/evidence/NOT-FOUND")
    assert response.status_code == 404

def test_list_reviews():
    response = client.get("/v1/reviews")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_get_review():
    response = client.get("/v1/reviews/REV-1234")
    assert response.status_code == 200
    assert response.json()["task_id"] == "REV-1234"

def test_get_review_not_found():
    response = client.get("/v1/reviews/NOT-FOUND")
    assert response.status_code == 404

def test_post_review_decision():
    response = client.post("/v1/reviews/REV-1234/decisions", json={"reviewer_id": "user1", "decision": "acknowledged"})
    assert response.status_code == 201
    
    # Check status changed
    response = client.get("/v1/reviews/REV-1234")
    assert response.json()["status"].lower() == "acknowledged"

def test_post_review_decision_invalid_transition():
    # Go to RESOLVED
    client.post("/v1/reviews/REV-1234/decisions", json={"reviewer_id": "user1", "decision": "resolved"})
    
    # Try invalid transition PENDING again
    response = client.post("/v1/reviews/REV-1234/decisions", json={"reviewer_id": "user1", "decision": "pending"})
    assert response.status_code == 409

# Mocking the actual build_orchestration_graph for analysis tests to avoid running actual agents
from unittest.mock import patch

class MockGraph:
    def __init__(self, state):
        self.state = state
    def invoke(self, input_state):
        return self.state

def test_analysis_success():
    state = {
        "final_report": {
            "report_content": "Valid answer",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["findings"] == "Valid answer"

def test_analysis_no_evidence():
    state = {
        "final_report": {
            "report_content": "No actionable evidence",
            "citations_resolved": [],
            "limitations_noted": ["No_evidence_found = True"]
        },
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "no_evidence"

def test_analysis_partial_success():
    state = {
        "final_report": {
            "report_content": "Could not be fully verified",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "errors": ["Validation error"]
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "partial_success"

def test_status_required_behavior_success():
    state = {
        "final_report": {"report_content": "ok"},
        "specialist_results": {
            "A": {"findings": "ok"},
            "B": {"findings": "ok"}
        }
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

def test_status_required_behavior_no_evidence():
    state = {
        "final_report": {"report_content": "ok"},
        "specialist_results": {
            "A": {"no_evidence_found": True},
            "B": {"summary": "No data found"}
        }
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "no_evidence"

def test_status_required_behavior_partial_success():
    state = {
        "final_report": {"report_content": "ok"},
        "specialist_results": {
            "A": {"findings": "ok"},
            "B": {"limitations": ["Agent exceeded max iterations before producing valid output."]}
        }
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "partial_success"

def test_status_required_behavior_failed():
    state = {
        "final_report": {"report_content": "ok"},
        "specialist_results": {
            "A": {"limitations": ["Agent exceeded max iterations"]},
            "B": {"findings": "could not execute search"}
        }
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        assert response.json()["status"] == "failed"

def test_analysis_malformed():
    response = client.post("/v1/analyses", json={"wrong_field": "Hello"})
    assert response.status_code == 422

def test_build_gateway_configuration():
    from pharmasense.llm.budget import BudgetEnforcingGateway
    gateway = build_gateway()
    assert isinstance(gateway, BudgetEnforcingGateway)

def test_analysis_citations_fallback():
    state = {
        "final_report": {
            "report_content": "Valid answer",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "specialist_results": {
            "Literature Research": {
                "findings": "Some literature findings",
                "citations": []  # Simulate agent dropping citations
            }
        },
        "actual_tools": [
            {
                "tool_name": "vector_search_tool",
                "arguments": {"query": "test"},
                "result": {
                    "chunks": [
                        {"chunk_id": "CHUNK-1"},
                        {"chunk_id": "CHUNK-2"}
                    ],
                    "index_version": "v1"
                }
            }
        ],
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["claim"] == "Evidence retrieved by specialists"
        assert data["citations"][0]["citations"] == ["CHUNK-1", "CHUNK-2"]

def test_analysis_citations_fallback_no_evidence():
    state = {
        "final_report": {
            "report_content": "No actionable evidence",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "specialist_results": {
            "Literature Research": {
                "findings": "No literature findings",
                "citations": [],
                "no_evidence_found": True
            }
        },
        "actual_tools": [
            {
                "tool_name": "vector_search_tool",
                "arguments": {"query": "test"},
                "result": {
                    "chunks": [
                        {"chunk_id": "IRRELEVANT-1"},
                        {"chunk_id": "IRRELEVANT-2"}
                    ],
                    "index_version": "v1"
                }
            }
        ],
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_evidence"
        assert len(data["citations"]) == 0


def test_analysis_escalation_reference_populated():
    state = {
        "final_report": {
            "report_content": "Severe AE detected",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "specialist_results": {
            "Adverse Event Triage": {
                "summary": "Triage done"
            }
        },
        "actual_tools": [
            {
                "tool_name": "escalation_notifier_tool",
                "arguments": {"event_id": "EV-1", "reason": "Severe"},
                "result": {
                    "task_id": "REV-125dcef9",
                    "persisted": True,
                    "delivery_status": "Mock Delivery"
                }
            }
        ],
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Triage TRL-0034"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalation_reference"] == "REV-125dcef9"

def test_analysis_escalation_reference_null():
    state = {
        "final_report": {
            "report_content": "No severe AE detected",
            "citations_resolved": [],
            "limitations_noted": []
        },
        "specialist_results": {
            "Adverse Event Triage": {
                "summary": "Triage done"
            }
        },
        "actual_tools": [],
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Triage TRL-0034"})
        assert response.status_code == 200
        data = response.json()
        assert data["escalation_reference"] is None

def test_escalation_persistence_integration():
    from pharmasense.tools.escalation import escalation_notifier_tool, EscalationInput
    
    # We create a mock graph that actually uses the session to call the tool,
    # mimicking what happens in reality, to test if db.commit() in the API route works.
    class IntegrationMockGraph:
        def __init__(self, db_session):
            self.db_session = db_session
            
        def invoke(self, inputs):
            out = escalation_notifier_tool(self.db_session, EscalationInput(event_id="EV-INTEG", reason="Integ test"))
            return {
                "final_report": {"report_content": "Done", "citations_resolved": [], "limitations_noted": []},
                "specialist_results": {},
                "actual_tools": [{
                    "tool_name": "escalation_notifier_tool",
                    "arguments": {},
                    "result": out.model_dump()
                }],
                "errors": []
            }
            
    # Need to override build_orchestration_graph to receive the db session
    def mock_build_graph(db, gateway):
        return IntegrationMockGraph(db)
        
    with patch("pharmasense.api.main.build_orchestration_graph", side_effect=mock_build_graph):
        post_resp = client.post("/v1/analyses", json={"user_prompt": "Triage TRL-INTEG"})
        assert post_resp.status_code == 200
        ref_id = post_resp.json()["escalation_reference"]
        assert ref_id is not None
        
        # 1. persisted review task is returned by GET /v1/reviews
        list_resp = client.get("/v1/reviews")
        assert list_resp.status_code == 200
        tasks = list_resp.json()
        assert any(t["task_id"] == ref_id for t in tasks)
        
        # 2. same review task retrievable via GET /v1/reviews/{review_id}
        get_resp = client.get(f"/v1/reviews/{ref_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["task_id"] == ref_id
        
        # 3. missing review ID returns not-found
        miss_resp = client.get("/v1/reviews/MISSING-1234")
        assert miss_resp.status_code == 404

def test_api_uses_eval_db_for_ae_triage(monkeypatch):
    """Prove the API uses EVAL_DATABASE_URL when set and can see seeded TRL-0034 records."""
    from pharmasense.api.main import get_db_session
    from pharmasense.tools.sql_query import sql_query_tool, SqlQueryInput
    
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_test")
    
    session_gen = get_db_session()
    session = next(session_gen)
    
    try:
        req = SqlQueryInput(query_id="adverse_events_by_trial", parameters={"trial_id": "TRL-0034"})
        out = sql_query_tool(session, req)
        
        # Verify that the seeded records from the eval DB are found
        assert len(out.results) == 6
    finally:
        session.close()
