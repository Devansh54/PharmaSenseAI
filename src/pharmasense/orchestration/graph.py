from typing import Any
from langgraph.graph import StateGraph, END, START
from sqlalchemy.orm import Session

from pharmasense.llm.contracts import LLMProvider
from pharmasense.orchestration.state import WorkflowState
from pharmasense.orchestration.planner import PlannerNode
from pharmasense.orchestration.finalizer import FinalizerNode
from pharmasense.validation.requests import validate_input_request
from pharmasense.validation.evidence import validate_evidence
from pharmasense.validation.outputs import validate_output
import json

from pharmasense.agents.trial import create_trial_data_analyst
from pharmasense.agents.literature import create_literature_research_agent
from pharmasense.agents.adverse_event import create_ae_triage_agent
from pharmasense.agents.similarity import create_compound_similarity_agent
from pharmasense.agents.report import create_report_writer_agent

SPECIALIST_NODE_MAP = {
    "Trial Data Analyst": "trial_agent",
    "Literature Research": "literature_agent",
    "Adverse Event Triage": "ae_triage_agent",
    "Compound Similarity": "similarity_agent",
}

class SpecialistRunner:
    def __init__(self, agent_factory, session: Session, llm: LLMProvider, name: str):
        self.agent_factory = agent_factory
        self.session = session
        self.llm = llm
        self.name = name

    def __call__(self, state: WorkflowState) -> dict:
        plan = state.get("plan")
        if not plan:
            return {"errors": [f"Missing plan in {self.name}"]}

        task_desc = plan.task_descriptions.get(self.name, state.get("user_prompt", ""))

        # Thread isolation for database sessions: parallel specialist nodes execute
        # on different threads in LangGraph and must not share a single psycopg2 connection.
        bind = getattr(self.session, "bind", None)
        if bind is None and hasattr(self.session, "get_bind"):
            try:
                bind = self.session.get_bind()
            except Exception:
                bind = None

        use_isolated = bind is not None
        worker_session = Session(bind) if use_isolated else self.session
        agent = None

        try:
            # Instantiate agent lazily to ensure session is bound
            import inspect
            sig = inspect.signature(self.agent_factory)
            if "task_desc" in sig.parameters:
                agent = self.agent_factory(worker_session, self.llm, task_desc=task_desc)
            else:
                agent = self.agent_factory(worker_session, self.llm)

            single_tool_mode = plan.workflow_type == "single"
            result, executed_tools = agent.run(task_desc, single_tool_mode=single_tool_mode)
            if use_isolated:
                try:
                    worker_session.commit()
                except Exception:
                    worker_session.rollback()
            return {
                "specialist_results": {self.name: result.model_dump()},
                "actual_tools": executed_tools
            }
        except Exception as e:
            if use_isolated:
                worker_session.rollback()
            return {
                "errors": [f"{self.name} failed: {str(e)}"],
                "actual_tools": getattr(agent, "executed_tools", []) if agent else []
            }
        finally:
            if use_isolated:
                worker_session.close()

class ReportWriterRunner:
    def __init__(self, session: Session, llm: LLMProvider):
        self.session = session
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict:
        plan = state.get("plan")
        specialist_results = state.get("specialist_results", {})

        # Fast-path pass-through for single workflows
        if plan and plan.workflow_type == "single":
            if specialist_results:
                first_result = next(iter(specialist_results.values()))
                # Extract the main answer or serialize
                content = (
                    first_result.get("summary") or
                    first_result.get("findings") or
                    first_result.get("explanation") or
                    str(first_result)
                )
                return {"final_report": {"report_content": content}}
            return {"final_report": {"report_content": "No results."}}

        findings_str = ""
        for name, res in specialist_results.items():
            findings_str += f"--- {name} Findings ---\n"
            if isinstance(res, dict):
                for k, v in res.items():
                    if v == [] or v == "" or v is None:
                        continue
                    findings_str += f"{k.capitalize()}: {v}\n"
            else:
                findings_str += f"{res}\n"
            findings_str += "\n"

        task_desc = f"Synthesize the following findings into a final report:\n\n{findings_str}"

        feedback = state.get("validation_feedback")
        if feedback:
            task_desc += f"\n\nPREVIOUS VALIDATION FAILED. You must fix the report based on this feedback:\n{feedback}"

        agent = create_report_writer_agent(self.session, self.llm)
        try:
            result, _ = agent.run(task_desc)
            return {"final_report": result.model_dump()}
        except Exception as e:
            return {"errors": [f"Report Writer failed: {str(e)}"]}

class InputGuardrailNode:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict:
        is_valid, reason = validate_input_request(state["user_prompt"], self.llm)
        if not is_valid:
            return {
                "errors": [f"Guardrail blocked request: {reason}"],
                "final_report": {"report_content": reason}
            }
        return {}

class OutputGuardrailNode:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict:
        report_data = state.get("final_report")
        if not report_data:
            return {}

        report_text = report_data.get("report_content", "")
        if not report_text:
            return {}

        valid_out, out_reason = validate_output(report_text)
        if not valid_out:
            return {"errors": [f"Output validation failed: {out_reason}"]}

        evidence_payload = {
            "specialist_results": state.get("specialist_results", {}),
            "actual_tools": state.get("actual_tools", [])
        }

        # Deterministic fast path for S1 validation
        is_supported = True
        ev_reason = ""

        actual_tools = state.get("actual_tools", [])
        trial_tool = next((t for t in actual_tools if t.get("tool_name") == "sql_query_tool" and t.get("arguments", {}).get("query_id") == "trial_enrollment_stats"), None)
        if trial_tool and state.get("plan") and state["plan"].workflow_type == "single":
            results = trial_tool.get("result", {}).get("results", [])
            below_60 = [r for r in results if r.get("is_below_threshold") is True]
            for trial in below_60:
                if trial["trial_id"] not in report_text:
                    is_supported = False
                    ev_reason = f"Deterministic validation failed: The report omitted the below-threshold trial {trial['trial_id']}."
                    break

            if is_supported:
                import re
                clauses = re.split(r'[.\n;]+|\bbut\b|\bwhile\b|\bwhereas\b', report_text.lower())
                for clause in clauses:
                    if any(h in clause for h in ["exceeds", "meets", "at or above", "above 60%", "above the threshold", "above threshold"]):
                        for trial in below_60:
                            if trial["trial_id"].lower() in clause:
                                is_supported = False
                                ev_reason = f"Deterministic validation failed: Contradictory claim for below-threshold trial {trial['trial_id']}."
                                break
                    if not is_supported:
                        break
        else:
            # Fallback to LLM validation
            context_str = json.dumps(evidence_payload)
            is_supported, ev_reason = validate_evidence(report_text, context_str, self.llm)

        if not is_supported:
            if state.get("evidence_repaired"):
                return {
                    "final_report": {"report_content": "I am unable to provide a response because the generated claims could not be fully verified against the source evidence."},
                    "errors": ["Evidence validation failed after repair attempt."]
                }
            else:
                return {
                    "evidence_repaired": True,
                    "validation_feedback": f"Unsupported claims detected: {ev_reason}. Please rewrite the report ensuring all claims are strictly supported by the provided findings."
                }

        return {"validation_feedback": None}

def route_after_planner(state: WorkflowState):
    if state.get("errors"):
        return "finalizer"

    plan = state["plan"]
    if not plan:
        return "finalizer"

    destinations = []
    for spec in plan.selected_specialists:
        node_name = SPECIALIST_NODE_MAP.get(spec)
        if node_name:
            destinations.append(node_name)

    if not destinations:
        return "finalizer"

    return destinations

def route_after_specialist(state: WorkflowState):
    if state.get("errors"):
        return "finalizer"

    return "report_writer"

def route_after_input_guardrail(state: WorkflowState):
    if state.get("errors"):
        return "finalizer"
    return "planner"

def route_after_output_guardrail(state: WorkflowState):
    if state.get("errors"):
        return "finalizer"
    if state.get("validation_feedback"):
        return "report_writer"
    return "finalizer"

from pharmasense.observability.telemetry import TelemetryManager
from pharmasense.observability.context import current_trace_id, current_node_name
import datetime

class TelemetryNodeWrapper:
    def __init__(self, node_func, node_name: str, node_type: str, telemetry_manager: TelemetryManager):
        self.node_func = node_func
        self.node_name = node_name
        self.node_type = node_type
        self.telemetry_manager = telemetry_manager

    def __call__(self, state: WorkflowState) -> dict:
        trace_id = state.get("request_id", "")
        # Set context vars for LLM tracing
        t_id_token = current_trace_id.set(trace_id)
        n_name_token = current_node_name.set(self.node_name)

        start_time = datetime.datetime.utcnow()
        try:
            result = self.node_func(state)
            status = "SUCCESS"
            if result and isinstance(result, dict) and result.get("errors"):
                status = "ERROR"
            return result
        except Exception as e:
            status = "ERROR"
            raise
        finally:
            end_time = datetime.datetime.utcnow()
            if self.telemetry_manager:
                self.telemetry_manager.log_event(
                    trace_id=trace_id,
                    event_type=self.node_type,
                    node_name=self.node_name,
                    start_time=start_time,
                    end_time=end_time,
                    status=status
                )
            current_trace_id.reset(t_id_token)
            current_node_name.reset(n_name_token)

def build_orchestration_graph(session: Session, llm: LLMProvider, telemetry_manager: TelemetryManager = None):
    builder = StateGraph(WorkflowState)

    builder.add_node("input_guardrail", TelemetryNodeWrapper(InputGuardrailNode(llm), "Input Guardrail", "GUARDRAIL", telemetry_manager))
    builder.add_node("planner", TelemetryNodeWrapper(PlannerNode(llm), "Planner", "PLANNER", telemetry_manager))
    builder.add_node("trial_agent", TelemetryNodeWrapper(SpecialistRunner(create_trial_data_analyst, session, llm, "Trial Data Analyst"), "Trial Data Analyst", "SPECIALIST", telemetry_manager))
    builder.add_node("literature_agent", TelemetryNodeWrapper(SpecialistRunner(create_literature_research_agent, session, llm, "Literature Research"), "Literature Research", "SPECIALIST", telemetry_manager))
    builder.add_node("ae_triage_agent", TelemetryNodeWrapper(SpecialistRunner(create_ae_triage_agent, session, llm, "Adverse Event Triage"), "Adverse Event Triage", "SPECIALIST", telemetry_manager))
    builder.add_node("similarity_agent", TelemetryNodeWrapper(SpecialistRunner(create_compound_similarity_agent, session, llm, "Compound Similarity"), "Compound Similarity", "SPECIALIST", telemetry_manager))

    builder.add_node("report_writer", TelemetryNodeWrapper(ReportWriterRunner(session, llm), "Report Writer", "SPECIALIST", telemetry_manager))
    builder.add_node("output_guardrail", TelemetryNodeWrapper(OutputGuardrailNode(llm), "Output Guardrail", "GUARDRAIL", telemetry_manager))
    builder.add_node("finalizer", TelemetryNodeWrapper(FinalizerNode(), "Finalizer", "FINALIZER", telemetry_manager))

    builder.add_edge(START, "input_guardrail")
    builder.add_conditional_edges("input_guardrail", route_after_input_guardrail, ["planner", "finalizer"])

    builder.add_conditional_edges("planner", route_after_planner, [
        "trial_agent", "literature_agent", "ae_triage_agent", "similarity_agent", "finalizer"
    ])

    for node_name in SPECIALIST_NODE_MAP.values():
        builder.add_conditional_edges(node_name, route_after_specialist, ["report_writer", "finalizer"])

    builder.add_edge("report_writer", "output_guardrail")
    builder.add_conditional_edges("output_guardrail", route_after_output_guardrail, ["report_writer", "finalizer"])
    builder.add_edge("finalizer", END)

    return builder.compile()
