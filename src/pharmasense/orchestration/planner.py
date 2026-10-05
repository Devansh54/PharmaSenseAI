import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message
from pharmasense.orchestration.state import Plan, WorkflowState

def try_deterministic_route(prompt: str) -> Plan | None:
    prompt_lower = prompt.lower()
    
    # Multi-agent "full picture"
    if "full picture" in prompt_lower or ("labs" in prompt_lower and "trials" in prompt_lower and "safety" in prompt_lower and "literature" in prompt_lower):
        return Plan(
            workflow_type="parallel",
            selected_specialists=[
                "Trial Data Analyst", 
                "Literature Research", 
                "Adverse Event Triage", 
                "Compound Similarity"
            ],
            task_descriptions={
                "Trial Data Analyst": prompt,
                "Literature Research": prompt,
                "Adverse Event Triage": prompt,
                "Compound Similarity": prompt
            },
            resolved_entities={}
        )

    # Determine single-domain matches
    matches = []
    if re.search(r'\b(trial|enrollment|clinical trial|phase ii)\b', prompt_lower):
        matches.append("Trial Data Analyst")
    if re.search(r'\b(research|document|literature|internal research|jak2)\b', prompt_lower):
        matches.append("Literature Research")
    if re.search(r'\b(adverse event|ae|safety|seriousness|triage|serious adverse event)\b', prompt_lower):
        matches.append("Adverse Event Triage")
    if re.search(r'\b(similar|similarity|related compounds)\b', prompt_lower):
        matches.append("Compound Similarity")

    # Fast path only for unambiguous single matches
    if len(matches) == 1:
        return Plan(
            workflow_type="single",
            selected_specialists=[matches[0]],
            task_descriptions={matches[0]: prompt},
            resolved_entities={}
        )
    
    return None

class PlannerNode:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def __call__(self, state: WorkflowState) -> dict:
        prompt_text = state.get('user_prompt', '')
        
        # Fast deterministic path
        det_plan = try_deterministic_route(prompt_text)
        if det_plan:
            return {"plan": det_plan}
            
        # Fallback to LLM
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
                Message(role="user", content=f"User Prompt: {prompt_text}")
            ],
            model="",
            response_schema=Plan.model_json_schema()
        )

        from pharmasense.llm.contracts import LLMGatewayError, LLMProviderError, LLMTimeoutError

        try:
            res = self.llm.complete(req)
        except (LLMProviderError, LLMTimeoutError):
            raise
        except LLMGatewayError as e:
            return {"errors": [f"Planner failed to parse schema: {str(e)}"]}

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
