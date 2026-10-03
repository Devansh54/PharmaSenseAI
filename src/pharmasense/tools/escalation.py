"""Escalation Notifier Tool.
Persists a human-review task and triggers optional delivery.
"""
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid
from datetime import datetime, timezone

from pharmasense.db.models import ReviewTask

class EscalationInput(BaseModel):
    event_id: str
    reason: str

class EscalationOutput(BaseModel):
    task_id: str
    persisted: bool
    delivery_status: str

def escalation_notifier_tool(session: Session, input_data: EscalationInput) -> EscalationOutput:
    """Persists a review task for an adverse event and stubs a delivery notification."""
    
    # Idempotency check: see if a pending task already exists for this event
    existing_task = session.query(ReviewTask).filter(
        ReviewTask.event_id == input_data.event_id,
        ReviewTask.status == "PENDING"
    ).first()
    
    if existing_task:
        return EscalationOutput(
            task_id=existing_task.task_id,
            persisted=True,
            delivery_status="Skipped (already pending)"
        )
        
    task_id = f"REV-{uuid.uuid4().hex[:8]}"
    new_task = ReviewTask(
        task_id=task_id,
        event_id=input_data.event_id,
        status="PENDING",
        reason=input_data.reason,
        created_at=datetime.now(timezone.utc)
    )
    
    session.add(new_task)
    session.flush()
    
    # Stub delivery
    delivery_msg = f"Mock Delivery: Alert sent to safety team for task {task_id}."
    
    return EscalationOutput(
        task_id=task_id,
        persisted=True,
        delivery_status=delivery_msg
    )
