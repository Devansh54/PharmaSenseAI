import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message
from pharmasense.orchestration.state import Plan, WorkflowState

def try_deterministic_route(prompt: str) -> Plan | None:
    prompt_lower = prompt.lower()

    # Specific map for high-confidence trial enrollment workflows (e.g., S1)
    if "enrollment" in prompt_lower and "below" in prompt_lower and "trials" in prompt_lower:
        return Plan(
            workflow_type="single",
            selected_specialists=["Trial Data Analyst"],
            task_descriptions={
                "Trial Data Analyst": (
                    f"User Prompt: {prompt}\n\n"
                    "INSTRUCTION: Use the `trial_enrollment_stats` query_id to retrieve all matching trials. "
                    "Pass the requested percentage threshold as `threshold_pct` (e.g. 60.0). "
                    "The SQL tool will calculate and return an `is_below_threshold` boolean for each trial. "
                    "You MUST rely exclusively on this boolean to filter the trials. Do NOT perform percentage threshold comparisons yourself."
                )
            },
            resolved_entities={}
        )

    # Multi-agent "full picture"
    if any(p in prompt_lower for p in ["full picture", "overall profile", "compound investigation"]):
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
    matches = set()

    # Safety is prioritized if explicit triage/AE terms exist
    if re.search(r'\b(adverse event|ae|safety|seriousness|serious event|toxicity|triage)\b', prompt_lower):
        matches.add("Adverse Event Triage")

    # Trial matches
    if re.search(r'\b(trials?|studies|study|enrollment|enrolment|recruitment|sites?|clinical studies|clinical trials?)\b', prompt_lower):
        matches.add("Trial Data Analyst")

    # Literature matches
    if re.search(r'\b(research|literature|document|papers|evidence|findings|internal research)\b', prompt_lower):
        matches.add("Literature Research")

    # Similarity matches
    if re.search(r'\b(similar|similarity|related compounds?)\b', prompt_lower):
        matches.add("Compound Similarity")

    # If it matches Adverse Event AND Trial (e.g. "adverse event for Trial TRL-0032"),
    # it's usually an AE triage task primarily. Let's refine conflicts:
    if "Adverse Event Triage" in matches and "Trial Data Analyst" in matches:
        if "triage" in prompt_lower or "adverse event" in prompt_lower:
            matches.remove("Trial Data Analyst")

    # Fast path only for unambiguous single matches
    if len(matches) == 1:
        selected = list(matches)[0]
        return Plan(
            workflow_type="single",
            selected_specialists=[selected],
            task_descriptions={selected: prompt},
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
