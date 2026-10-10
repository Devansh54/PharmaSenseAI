import re
from pharmasense.llm.contracts import LLMProvider, LLMRequest, Message
from pharmasense.orchestration.state import Plan, WorkflowState

def try_deterministic_route(prompt: str) -> Plan | None:
    prompt_lower = prompt.lower()

    # 1. Out-of-scope / Medical Advice
    if re.search(r'\b(medical advice|treatment|prescribe|prescription|medication should a patient take|drug should i prescribe|treatment should this patient take)\b', prompt_lower):
        # We can simulate an empty plan that the orchestrator will fail on, 
        # or we can raise an error/return a plan with no specialists. 
        # The planner raises an error if selected_specialists is empty.
        return Plan(
            workflow_type="single",
            selected_specialists=[],
            task_descriptions={},
            resolved_entities={}
        )

    # 2. Specific map for high-confidence trial enrollment workflows (e.g., S1)
    if re.search(r'\b(enrollment|enrolled)\b', prompt_lower) and re.search(r'\b(below|less than|behind)\b', prompt_lower) and re.search(r'\b(trials|studies)\b', prompt_lower):
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

    # 3.5. Trial + Research combined only (e.g. Q9)
    if re.search(r'\b(summarize.*(trial|clinical).*(research|evidence)|combine.*clinical.*literature)\b', prompt_lower) and not re.search(r'\b(full picture|overall profile|compound investigation)\b', prompt_lower):
        return Plan(
            workflow_type="parallel",
            selected_specialists=[
                "Trial Data Analyst",
                "Literature Research"
            ],
            task_descriptions={
                "Trial Data Analyst": f"User Prompt: {prompt}\n\nINSTRUCTION: You MUST use the `trials_by_compound` query_id first to retrieve all clinical trials associated with the requested compound. If the user also asks for associated sites, you may subsequently use `site_enrollment` for the identified trials.",
                "Literature Research": prompt
            },
            resolved_entities={}
        )

    # 3. Specific map for site-level details (e.g., Q3)
    if re.search(r'\b(site|sites|site-level|clinical sites?)\b', prompt_lower) and re.search(r'\b(trials|studies)\b', prompt_lower):
        return Plan(
            workflow_type="single",
            selected_specialists=["Trial Data Analyst"],
            task_descriptions={
                "Trial Data Analyst": (
                    f"User Prompt: {prompt}\n\n"
                    "INSTRUCTION: You MUST use the `sites_by_trial_attributes` query_id to answer this question. "
                    "Do NOT use any other query. "
                    "Extract the required parameters (e.g., trial_phase, therapeutic_area) from the prompt."
                )
            },
            resolved_entities={}
        )


    # 4. Multi-agent "full picture" (4-agent deep dive)
    if re.search(r'\b(full picture|overall profile|compound investigation)\b', prompt_lower) or (re.search(r'\b(summarize.*(trial|clinical).*(research|evidence)|combine.*clinical.*literature)\b', prompt_lower) and re.search(r'\b(full picture|overall profile|compound investigation)\b', prompt_lower)):
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
    if re.search(r'\b(adverse event|ae|safety|safety event|seriousness|serious event|toxicity|triage)\b', prompt_lower):
        matches.add("Adverse Event Triage")

    # Trial matches
    if re.search(r'\b(trials?|studies|study|enrollment|enrolment|recruitment|sites?|clinical studies|clinical trials?|lab|labs|laboratory|assay|results?)\b', prompt_lower):
        matches.add("Trial Data Analyst")

    # Literature matches
    if re.search(r'\b(research|literature|document|papers|evidence|findings|internal research)\b', prompt_lower):
        matches.add("Literature Research")

    # Similarity matches
    if re.search(r'\b(similar|similarity|related compounds?|comparable)\b', prompt_lower):
        matches.add("Compound Similarity")

    # If it matches Adverse Event AND Trial (e.g. "adverse event for Trial TRL-0032"),
    # it's usually an AE triage task primarily. Let's refine conflicts:
    if "Adverse Event Triage" in matches and "Trial Data Analyst" in matches:
        if "triage" in prompt_lower or "adverse event" in prompt_lower:
            matches.remove("Trial Data Analyst")

    # Fast path only for unambiguous single matches
    if len(matches) == 1:
        selected = list(matches)[0]
        # Compound Similarity and AE Triage require multiple sequential tools
        w_type = "sequential" if selected in ("Compound Similarity", "Adverse Event Triage") else "single"
        return Plan(
            workflow_type=w_type,
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
            if not det_plan.selected_specialists:
                return {
                    "errors": ["Out-of-scope request blocked."],
                    "final_report": {"report_content": "I cannot provide personalized medical advice or treatment recommendations."}
                }
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
