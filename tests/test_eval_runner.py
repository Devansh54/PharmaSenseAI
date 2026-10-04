import pytest
import os
import hashlib
from unittest.mock import patch, MagicMock

from evals.runner import EvaluationRunner
from pharmasense.llm.contracts import LLMProviderError

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql://test_user:test_pass@localhost:5432/pharmasense_eval_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://dev_user:dev_pass@localhost:5432/pharmasense_dev")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

def test_eval_database_url_used(mock_env):
    """EVAL_DATABASE_URL is used explicitly and DATABASE_URL is not overwritten."""
    runner = EvaluationRunner(is_offline=True)
    assert "pharmasense_eval_test" in str(runner.engine.url)
    assert os.environ["DATABASE_URL"] == "postgresql://dev_user:dev_pass@localhost:5432/pharmasense_dev"

def test_fingerprint_stability_and_invalidation(mock_env):
    """Evaluation fingerprint generation is stable and changes when configuration changes."""
    runner = EvaluationRunner(is_offline=True)
    runner.model_name = "test-model"
    runner.provider_name = "test-provider"
    
    fp1 = runner._get_fingerprint("case_001")
    fp2 = runner._get_fingerprint("case_001")
    assert fp1 == fp2  # Stable

    # Change config (mock)
    runner.model_name = "different-model"
    fp3 = runner._get_fingerprint("case_001")
    assert fp1 != fp3  # Changes when config changes

def test_cache_hit_skips_execution(mock_env, tmp_path, monkeypatch):
    """Completed cases are skipped on cache hit."""
    import json
    from evals import runner as runner_module
    
    cache_path = tmp_path / "run_cache.json"
    monkeypatch.setattr(runner_module, "RUN_CACHE_PATH", cache_path)
    
    runner = EvaluationRunner(is_offline=True)
    runner.model_name = "test-model"
    runner.provider_name = "test-provider"
    
    fp = runner._get_fingerprint("case_001")
    
    # Inject fake cache
    cache_data = {fp: {
        "case_id": "case_001",
        "latency": 0.5,
        "correctness": 1,
        "faithfulness": 1,
        "relevance": 1,
        "citation": 1,
        "routing": 1,
        "tools": 1,
        "sql": 1,
        "hit_at_k": 1,
        "escalation": 1
    }}
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
        
    runner.run_cache = runner._load_cache()
    
    # Set cases to only case_001
    runner.cases = [{"case_id": "case_001", "query": "test", "should_block": False, "category": "test", "expected_escalation": False, "expected_assertions": []}]
    
    with patch.object(runner.graph, "invoke") as mock_invoke:
        # Mock pre_flight to not abort
        with patch.object(runner, "pre_flight_quota_check"):
            runner.run()
            # Since cache hit, invoke should never be called
            mock_invoke.assert_not_called()

def test_judge_cache_hit_and_miss(mock_env, tmp_path, monkeypatch):
    """Judge cache hits when report + judge configuration are identical, misses when changes."""
    from evals.metrics import LLMJudge
    
    cache_path = tmp_path / "judge_cache.json"
    
    class FakeAdapter:
        pass
    adapter = FakeAdapter()
    setattr(adapter, "complete", MagicMock())
    
    # We patch the path
    with patch("evals.metrics.Path") as mock_path:
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = False
        mock_path.return_value = mock_path_obj
        
        judge = LLMJudge(adapter)
        judge.cache_path = cache_path
        
        key1 = judge._get_cache_key("relevance", "Test answer")
        key2 = judge._get_cache_key("relevance", "Test answer")
        assert key1 == key2
        
        key3 = judge._get_cache_key("faithfulness", "Test answer")
        assert key1 != key3 # Different metric config
        
        key4 = judge._get_cache_key("relevance", "Different answer")
        assert key1 != key4 # Different report

def test_bounded_429_retry_handling(mock_env, tmp_path, monkeypatch):
    """429 handling performs bounded retry/backoff without duplicating successful calls."""
    from evals import runner as runner_module
    cache_path = tmp_path / "run_cache.json"
    monkeypatch.setattr(runner_module, "RUN_CACHE_PATH", cache_path)
    
    runner = EvaluationRunner(is_offline=True)
    runner.model_name = "test-model"
    runner.provider_name = "test-provider"
    runner.cases = [{"case_id": "case_001", "query": "test", "should_block": False, "category": "test", "expected_escalation": False, "expected_assertions": []}]
    
    # Mock invoke to throw 429 twice, then succeed
    mock_invoke = MagicMock(side_effect=[
        LLMProviderError("429 Too Many Requests", transient=True),
        LLMProviderError("429 Too Many Requests", transient=True),
        {"final_report": {"report_content": "success"}}
    ])
    
    with patch.object(runner.graph, "invoke", mock_invoke):
        with patch.object(runner, "pre_flight_quota_check"):
            with patch("time.sleep") as mock_sleep:
                runner.run()
                assert mock_invoke.call_count == 3
                assert mock_sleep.call_count == 2
                
def test_preflight_quota_logic(mock_env, monkeypatch):
    """Pre-flight quota logic blocks an obviously unsafe run without making live API calls."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    runner = EvaluationRunner(is_offline=False)
    runner.provider_name = "gemini"
    # Make it 400 cases (2000 calls) -> Exceeds gemini's 1500 daily limit
    runner.cases = [{"case_id": f"c_{i}"} for i in range(400)]
    
    with pytest.raises(SystemExit):
        runner.pre_flight_quota_check()
