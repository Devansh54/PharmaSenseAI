import json
import logging
import uuid
import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from pharmasense.db.models import RuntimeTrace, RuntimeEvent
from pharmasense.config import APP_VERSION, DEFAULT_PRICING

logger = logging.getLogger("pharmasense.telemetry")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


class TelemetryManager:
    """Manages telemetry traces and events."""
    
    def __init__(self, session: Session):
        self.session = session
        
    def start_trace(self, trace_id: Optional[str] = None, dataset_version: str = "1.0.0", workflow_version: str = "1.0.0") -> str:
        """Starts a new trace and returns the trace_id."""
        trace_id = trace_id or str(uuid.uuid4())
        trace = RuntimeTrace(
            trace_id=trace_id,
            start_time=datetime.datetime.utcnow(),
            status="RUNNING",
            app_version=APP_VERSION if hasattr(APP_VERSION, 'upper') else "1.0.0",
            workflow_version=workflow_version,
            dataset_version=dataset_version,
            created_at=datetime.datetime.utcnow(),
            total_tokens=0,
            total_cost=0.0
        )
        self.session.add(trace)
        self.session.commit()
        logger.info(f"Trace started: {trace_id}")
        return trace_id
        
    def log_event(self, trace_id: str, event_type: str, node_name: str, 
                  start_time: datetime.datetime, end_time: datetime.datetime, 
                  status: str, metadata: Optional[Dict[str, Any]] = None,
                  prompt_tokens: int = 0, completion_tokens: int = 0, total_cost: float = 0.0) -> str:
        """Logs a single event tied to a trace. PII MUST BE REDACTED from metadata before passing."""
        
        event_id = str(uuid.uuid4())
        latency = (end_time - start_time).total_seconds()
        
        # Ensure metadata contains no raw user prompts or report content
        clean_metadata = None
        if metadata:
            # Force strip raw user_prompt or report_content if passed accidentally
            if "user_prompt" in metadata:
                metadata["user_prompt"] = "[REDACTED]"
            if "report_content" in metadata:
                metadata["report_content"] = "[REDACTED]"
            clean_metadata = json.dumps(metadata)
            
        event = RuntimeEvent(
            event_id=event_id,
            trace_id=trace_id,
            event_type=event_type,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            latency_sec=latency,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_cost=total_cost,
            status=status,
            event_metadata=clean_metadata,
            created_at=datetime.datetime.utcnow()
        )
        self.session.add(event)
        
        # Accumulate trace totals
        trace = self.session.query(RuntimeTrace).filter_by(trace_id=trace_id).first()
        if trace:
            trace.total_tokens += (prompt_tokens + completion_tokens)
            if trace.total_cost is None:
                trace.total_cost = 0.0
            trace.total_cost += total_cost
            if "escalate" in node_name.lower() or (metadata and "escalat" in metadata.get("tool", "")):
                trace.escalated = True
                
        self.session.commit()
        return event_id
        
    def end_trace(self, trace_id: str, status: str, end_time: datetime.datetime, error_code: Optional[str] = None):
        """Ends the trace."""
        trace = self.session.query(RuntimeTrace).filter_by(trace_id=trace_id).first()
        if trace:
            trace.end_time = end_time
            trace.latency_sec = (end_time - trace.start_time).total_seconds()
            trace.status = status
            if error_code:
                trace.error_code = error_code
            self.session.commit()
            logger.info(f"Trace ended: {trace_id} | Status: {status} | Latency: {trace.latency_sec:.2f}s | Tokens: {trace.total_tokens} | Cost: ${trace.total_cost:.4f}")

from pharmasense.llm.tracing import Tracer, TraceEvent
from pharmasense.observability.context import current_trace_id, current_node_name
import time

class TelemetryTracer(Tracer):
    """Tracer that writes LLM events to TelemetryManager."""
    def __init__(self, telemetry_manager: TelemetryManager):
        self.telemetry_manager = telemetry_manager

    def start(self, model: str, metadata: Optional[Dict[str, Any]] = None) -> TraceEvent:
        trace_id = current_trace_id.get()
        if not trace_id:
            trace_id = str(uuid.uuid4())
        return TraceEvent(
            request_id=trace_id,
            model=model,
            started_at=time.time(),
            metadata=metadata or {}
        )

    def end(self, event: TraceEvent, **fields: Any) -> None:
        event.ended_at = time.time()
        for k, v in fields.items():
            setattr(event, k, v)
        
        status = "ERROR" if event.error else "SUCCESS"
        node_name = current_node_name.get() or "LLMGateway"
        
        # Inject tool calls into metadata for escalation tracking
        if fields.get("tool_names"):
            event.metadata["tool"] = fields["tool_names"][0]
            event.metadata["tool_names"] = fields["tool_names"]
            
        # Log to DB
        self.telemetry_manager.log_event(
            trace_id=event.request_id,
            event_type="LLM",
            node_name=node_name,
            start_time=datetime.datetime.fromtimestamp(event.started_at),
            end_time=datetime.datetime.fromtimestamp(event.ended_at),
            status=status,
            metadata=event.metadata,
            prompt_tokens=event.prompt_tokens or 0,
            completion_tokens=event.completion_tokens or 0,
            total_cost=event.total_cost or 0.0
        )
