import json
import re
from typing import List, Dict, Any, Optional
from pharmasense.llm.contracts import LLMRequest
from pharmasense.llm.openai_adapter import OpenAIAdapter

def compute_hit_at_k(actual_chunks: List[dict], expected_doc_ids: List[str]) -> Optional[int]:
    """Retrieval Quality: Hit@K"""
    if not expected_doc_ids:
        return 1 if not actual_chunks else 0

    actual_doc_ids = {c.get("doc_id") for c in actual_chunks}
    for doc_id in expected_doc_ids:
        if doc_id in actual_doc_ids:
            return 1
    return 0

def check_routing(expected_workflow: str, expected_specialists: List[str], actual_plan: dict) -> Optional[int]:
    """Routing: Deterministic exact match"""
    if expected_workflow == "N/A":
        return None

    if not actual_plan:
        return 0

    w_match = actual_plan.get("workflow_type") == expected_workflow
    s_match = set(actual_plan.get("selected_specialists", [])) == set(expected_specialists)
    return 1 if (w_match and s_match) else 0

def check_tool_selection(expected_tools: List[str], actual_tools: List[str]) -> Optional[int]:
    """Tool Selection: Deterministic exact match"""
    if expected_tools == ["N/A"] or (not expected_tools and not actual_tools):
        # We need a way to say N/A if it's a guardrail case that shouldn't call tools
        return None if expected_tools == ["N/A"] else 1

    return 1 if set(expected_tools) == set(actual_tools) else 0

def check_sql_correctness(actual_tools_called: List[dict]) -> Optional[int]:
    """SQL Correctness: Deterministic check if SQL query executed successfully"""
    sql_calls = [c for c in actual_tools_called if c.get("tool_name") == "sql_query"]
    if not sql_calls:
        return None

    for call in sql_calls:
        result = call.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            return 0
        if isinstance(result, str) and "error" in result.lower() and "syntax" in result.lower():
            return 0
    return 1

def check_escalation(expected_escalation: bool, actual_tools_called: List[dict], is_failed: bool = False) -> Optional[int]:
    """Escalation: Deterministic boolean check"""
    escalation_calls = [c for c in actual_tools_called if c.get("tool_name") == "escalate_to_human"]
    escalated_successfully = False

    for call in escalation_calls:
        result = call.get("result", {})
        if isinstance(result, dict) and result.get("error"):
            continue
        if isinstance(result, str) and "error" in result.lower():
            continue
        escalated_successfully = True

    if expected_escalation:
        return 1 if (escalated_successfully and not is_failed) else 0
    else:
        if escalated_successfully:
            return 0
        if is_failed:
            return None # N/A: Can't evaluate escalation choice if it crashed
        return 1

def check_citation_correctness(final_report: str, citations_resolved: List[dict]) -> Optional[int]:
    """Citation Correctness: Verifies [1] format exists and maps validly"""
    if not final_report or not citations_resolved:
        return None

    citations = re.findall(r'\[(\d+)\]', final_report)
    if not citations:
        return 0

    valid_ids = {str(c.get("citation_number", i+1)) for i, c in enumerate(citations_resolved)}

    for cit in citations:
        if cit not in valid_ids:
            return 0
    return 1

def check_deterministic_assertions(expected_assertions: List[str], actual_output: str, is_structured: bool = False) -> int:
    """
    Deterministic assertion checks.
    For structured data, we expect the value to be present exactly.
    For text, we use case-insensitive substring matching.
    """
    if not expected_assertions:
        return 1

    if not actual_output:
        return 0

    output_lower = str(actual_output).lower()

    for assertion in expected_assertions:
        # If it's a number, we do a word-boundary regex search to prevent false substring matches
        if re.match(r'^\d+$', str(assertion)):
            if not re.search(r'\b' + re.escape(str(assertion)) + r'\b', output_lower):
                return 0
        else:
            if str(assertion).lower() not in output_lower:
                return 0
    return 1

import hashlib
import os
from pathlib import Path

class LLMJudge:
    def __init__(self, llm_adapter):
        self.llm = llm_adapter
        self.cache_path = Path("evals/.cache/judge_cache.json")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self._load_cache()

        rubrics_path = Path("evals/rubrics.json")
        if rubrics_path.exists():
            with open(rubrics_path, "r") as f:
                content = f.read()
                self.rubrics = json.loads(content)
                self.rubric_version = hashlib.sha256(content.encode()).hexdigest()[:8]
        else:
            self.rubrics = {}
            self.rubric_version = "missing"

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_path, "w") as f:
            json.dump(self.cache, f, indent=2)

    def _get_cache_key(self, metric_name: str, answer: str) -> str:
        report_hash = hashlib.sha256(answer.encode()).hexdigest()
        provider = getattr(self.llm, "_config", type(self.llm).__name__)
        model = getattr(provider, "model", "default")
        provider_name = type(self.llm).__name__

        key_str = f"{report_hash}_{provider_name}_{model}_{metric_name}_{self.rubric_version}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _evaluate(self, metric_name: str, system_prompt: str, user_prompt: str, answer: str) -> Optional[int]:
        cache_key = self._get_cache_key(metric_name, answer)
        if cache_key in self.cache:
            return self.cache[cache_key]

        rubric = self.rubrics[metric_name]

        req = LLMRequest(
            messages=[
                Message(role="system", content=system_prompt + f"\n\nRubric:\n{rubric['rubric']}"),
                Message(role="user", content=user_prompt)
            ],
            temperature=0.0,
            response_schema=rubric["schema"]
        )

        try:
            resp = self.llm.complete(req)
            if resp.parsed and "score" in resp.parsed:
                score = resp.parsed["score"]
                self.cache[cache_key] = score
                self._save_cache()
                return score
        except Exception as e:
            print(f"Judge failed: {e}")
        return None

    def evaluate_faithfulness(self, query: str, context: str, answer: str) -> Optional[int]:
        """LLM Judge: Faithfulness"""
        if not answer or answer == "N/A":
            return None

        sys_prompt = "You are an objective judge evaluating the faithfulness of a generated answer. Determine if the answer is fully supported by the provided context."
        usr_prompt = f"Query: {query}\n\nContext:\n{context}\n\nAnswer:\n{answer}"
        return self._evaluate("faithfulness", sys_prompt, usr_prompt, answer)

    def evaluate_relevance(self, query: str, answer: str) -> Optional[int]:
        """LLM Judge: Relevance"""
        if not answer or answer == "N/A":
            return None

        sys_prompt = "You are an objective judge evaluating the relevance of a generated answer. Determine if the answer directly addresses the user's query."
        usr_prompt = f"Query: {query}\n\nAnswer:\n{answer}"
        return self._evaluate("relevance", sys_prompt, usr_prompt, answer)
