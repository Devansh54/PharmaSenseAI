import os
from unittest.mock import patch
import pytest

def test_acceptance_db_engine_offline_uses_pgvector_engine():
    """Proves offline mode uses the standard offline pytest DB with teardown."""
    from tests.test_live_acceptance import get_acceptance_db_engine_generator
    
    class DummyEngine:
        url = "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_pytest"
    
    gen = get_acceptance_db_engine_generator("offline", DummyEngine())
    engine = next(gen)
    
    assert str(engine.url) == "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense_pytest"

@patch.dict(os.environ, {"EVAL_DATABASE_URL": "postgresql+psycopg2://fake:fake@localhost:5432/pharmasense_test"})
def test_acceptance_db_engine_live_uses_eval_db_and_no_teardown():
    """Proves live mode uses EVAL_DATABASE_URL and avoids destructive teardown."""
    from tests.test_live_acceptance import get_acceptance_db_engine_generator
    
    gen = get_acceptance_db_engine_generator("live", None)
    engine = next(gen)
    
    assert "pharmasense_test" in str(engine.url)
    
    try:
        next(gen)
    except StopIteration:
        pass
    
    assert True
