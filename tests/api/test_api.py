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
                "citations": ["CHUNK-1", "CHUNK-2"]
            }
        },
        "errors": []
    }
    with patch("pharmasense.api.main.build_orchestration_graph", return_value=MockGraph(state)):
        response = client.post("/v1/analyses", json={"user_prompt": "Hello"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["claim"] == "Evidence retrieved by specialists"
        assert data["citations"][0]["citations"] == ["CHUNK-1", "CHUNK-2"]
