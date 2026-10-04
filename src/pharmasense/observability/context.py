import contextvars

current_trace_id = contextvars.ContextVar("current_trace_id", default=None)
current_node_name = contextvars.ContextVar("current_node_name", default=None)
