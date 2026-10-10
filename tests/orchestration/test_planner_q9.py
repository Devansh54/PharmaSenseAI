from pharmasense.orchestration.planner import try_deterministic_route

def test_q9_deterministic_routing():
    prompt = "Summarize the available trial and research findings for DKU-1042."
    plan = try_deterministic_route(prompt)
    
    assert plan is not None
    assert plan.workflow_type == "parallel"
    assert sorted(plan.selected_specialists) == sorted(["Trial Data Analyst", "Literature Research"])
    assert "trials_by_compound" in plan.task_descriptions["Trial Data Analyst"]

def test_full_picture_routing():
    prompt = "Give me the full picture on compound X, summarizing trial and research evidence"
    plan = try_deterministic_route(prompt)
    
    assert plan is not None
    assert plan.workflow_type == "parallel"
    assert sorted(plan.selected_specialists) == sorted([
        "Trial Data Analyst", 
        "Literature Research", 
        "Adverse Event Triage", 
        "Compound Similarity"
    ])
