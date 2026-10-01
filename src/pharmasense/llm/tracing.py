"""Minimal request/LLM tracing hooks.

Phase 2 only needs a lightweight seam to observe gateway calls (model,
latency, tokens, cost, tool calls, errors). Later phases can swap
`Tracer` for a real observability backend without changing gateway
code, as long as they honor this interface.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class TraceEvent:
    """A single traced gateway call, from start() to end()."""

    request_id: str
    model: str
    started_at: float
    ended_at: Optional[float] = None
    latency_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_cost: Optional[float] = None
    tool_call_count: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Tracer(Protocol):
    def start(self, model: str, metadata: Optional[Dict[str, Any]] = None) -> TraceEvent:
        ...

    def end(self, event: TraceEvent, **fields: Any) -> None:
        ...


def _log_event(event: TraceEvent) -> None:
    logger.info(
        "llm_call request_id=%s model=%s latency_ms=%s prompt_tokens=%s "
        "completion_tokens=%s total_cost=%s tool_calls=%s error=%s",
        event.request_id,
        event.model,
        f"{event.latency_ms:.1f}" if event.latency_ms is not None else None,
        event.prompt_tokens,
        event.completion_tokens,
        event.total_cost,
        event.tool_call_count,
        event.error,
    )


class NullTracer:
    """Logs each completed call but retains nothing in memory.

    Suitable default for production use until a later phase wires up
    a persistent observability backend.
    """

    def start(self, model: str, metadata: Optional[Dict[str, Any]] = None) -> TraceEvent:
        return TraceEvent(
            request_id=str(uuid.uuid4()),
            model=model,
            started_at=time.monotonic(),
            metadata=metadata or {},
        )

    def end(self, event: TraceEvent, **fields: Any) -> None:
        event.ended_at = time.monotonic()
        event.latency_ms = (event.ended_at - event.started_at) * 1000.0
        for key, value in fields.items():
            setattr(event, key, value)
        _log_event(event)


class InMemoryTracer(NullTracer):
    """Tracer that additionally retains completed events in memory.

    Useful for tests and for local debugging of the gateway's
    observability hook.
    """

    def __init__(self) -> None:
        self.events: List[TraceEvent] = []

    def end(self, event: TraceEvent, **fields: Any) -> None:
        super().end(event, **fields)
        self.events.append(event)
