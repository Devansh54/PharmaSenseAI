from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message
from pharmasense.orchestration.state import Plan, WorkflowState

class PlannerNode:
    def __init__(self, llm: LLMProvider):
        self.llm = llm
        
    def __call__(self, state: WorkflowState) -> dict:
        prompt = """
You are the Router/Planner.
Given the user prompt, produce a plan.
Rules:
- The system supports 3 workflows: single, sequential, parallel.
- Sequential/Parallel workflows end with Report Writer. Do NOT include 'Report Writer' in selected_specialists, it is implied by the workflow type.
- Allowed specialists:
  - 'Trial Data Analyst'
  - 'Literature Research'
  - 'Adverse Event Triage'
  - 'Compound Similarity'
- Max 4 parallel investigative branches.
- Do NOT hallucinate other agents.
- Validate your workflow type against the chosen agents.
"""
        req = LLMRequest(
            messages=[
                Message(role="system", content=prompt.strip()),
                Message(role="user", content=f"User Prompt: {state['user_prompt']}")
            ],
            model="",
            response_schema=Plan.model_json_schema()
        )
        
        # Do not catch LLM exceptions silently; let them propagate so they aren't masked as fallbacks.
        res = self.llm.complete(req)
            
        if not res.parsed:
            return {"errors": ["Planner failed to return structured output"]}
        
        try:
            plan = Plan.model_validate(res.parsed)
        except Exception as e:
            return {"errors": [f"Validation Error: {str(e)}"]}
            
        allowed = {"Trial Data Analyst", "Literature Research", "Adverse Event Triage", "Compound Similarity"}
        for spec in plan.selected_specialists:
            if spec not in allowed:
                return {"errors": [f"Unauthorized specialist: {spec}"]}
                
        if len(plan.selected_specialists) > 4:
            return {"errors": ["Exceeded maximum of 4 investigative branches"]}
            
        if not plan.selected_specialists:
            return {"errors": ["No specialists selected"]}
            
        return {"plan": plan}
