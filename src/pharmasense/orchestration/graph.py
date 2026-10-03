from typing import Any
from langgraph.graph import StateGraph, END, START
from sqlalchemy.orm import Session

from pharmasense.llm.contracts import LLMProvider
from pharmasense.orchestration.state import WorkflowState
from pharmasense.orchestration.planner import PlannerNode
from pharmasense.orchestration.finalizer import FinalizerNode

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
        
        # Instantiate agent lazily to ensure session is bound
        agent = self.agent_factory(self.session, self.llm)
        
        try:
            result = agent.run(task_desc)
            return {"specialist_results": {self.name: result.model_dump()}}
        except Exception as e:
            return {"errors": [f"{self.name} failed: {str(e)}"]}

class ReportWriterRunner:
    def __init__(self, session: Session, llm: LLMProvider):
        self.session = session
        self.llm = llm
        
    def __call__(self, state: WorkflowState) -> dict:
        findings_str = ""
        for name, res in state.get("specialist_results", {}).items():
            findings_str += f"--- {name} Findings ---\n{res}\n\n"
            
        task_desc = f"Synthesize the following findings into a final report:\n\n{findings_str}"
        
        agent = create_report_writer_agent(self.session, self.llm)
        try:
            result = agent.run(task_desc)
            return {"final_report": result.model_dump()}
        except Exception as e:
            return {"errors": [f"Report Writer failed: {str(e)}"]}

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
        
    plan = state["plan"]
    if plan and plan.workflow_type == "single":
        return "finalizer"
    return "report_writer"

def build_orchestration_graph(session: Session, llm: LLMProvider):
    builder = StateGraph(WorkflowState)
    
    builder.add_node("planner", PlannerNode(llm))
    builder.add_node("trial_agent", SpecialistRunner(create_trial_data_analyst, session, llm, "Trial Data Analyst"))
    builder.add_node("literature_agent", SpecialistRunner(create_literature_research_agent, session, llm, "Literature Research"))
    builder.add_node("ae_triage_agent", SpecialistRunner(create_ae_triage_agent, session, llm, "Adverse Event Triage"))
    builder.add_node("similarity_agent", SpecialistRunner(create_compound_similarity_agent, session, llm, "Compound Similarity"))
    
    builder.add_node("report_writer", ReportWriterRunner(session, llm))
    builder.add_node("finalizer", FinalizerNode())
    
    builder.add_edge(START, "planner")
    
    builder.add_conditional_edges("planner", route_after_planner, [
        "trial_agent", "literature_agent", "ae_triage_agent", "similarity_agent", "finalizer"
    ])
    
    for node_name in SPECIALIST_NODE_MAP.values():
        builder.add_conditional_edges(node_name, route_after_specialist, ["report_writer", "finalizer"])
        
    builder.add_edge("report_writer", "finalizer")
    builder.add_edge("finalizer", END)
    
    return builder.compile()
