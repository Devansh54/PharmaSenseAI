import os
import sys
import subprocess
from pathlib import Path

def run_env_py(env_vars):
    """Runs env.py in a subprocess and prints the resolved sqlalchemy.url"""
    # We mock alembic.context so it doesn't actually try to connect to the DB
    code = """
import os
import sys
from unittest.mock import MagicMock
from alembic.config import Config

class MockContext:
    def __init__(self):
        self.config = Config()
    def is_offline_mode(self): return True
    def configure(self, *args, **kwargs): pass
    def begin_transaction(self): return MagicMock()
    def run_migrations(self): pass

mock_ctx = MockContext()
if 'EXPLICIT_URL' in os.environ:
    mock_ctx.config.set_main_option("sqlalchemy.url", os.environ['EXPLICIT_URL'])

class FakeAlembic:
    context = mock_ctx

sys.modules['alembic'] = FakeAlembic
sys.modules['alembic.context'] = mock_ctx

# prevent fileConfig from trying to read alembic.ini if not in cwd
import logging.config
logging.config.fileConfig = MagicMock()

import migrations.env as env
print("URL_RESULT=" + str(env.config.get_main_option('sqlalchemy.url')))
"""
    env = os.environ.copy()
    env.update(env_vars)
    # Ensure PYTHONPATH includes the project root
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    
    res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Subprocess failed:\n{res.stderr}")
    
    for line in res.stdout.splitlines():
        if line.startswith("URL_RESULT="):
            return line.split("URL_RESULT=")[1]
    return None

def test_migration_env_resolves_eval_db_when_supplied():
    """Test that migrations/env.py uses EVAL_DATABASE_URL if provided."""
    env = {
        "EVAL_DATABASE_URL": "postgresql+psycopg2://fake:fake@localhost:5432/eval_db",
        "PHARMASENSE_DATABASE_URL": "postgresql+psycopg2://fake:fake@localhost:5432/dev_db"
    }
    url = run_env_py(env)
    assert url == "postgresql+psycopg2://fake:fake@localhost:5432/eval_db"

def test_migration_env_resolves_dev_db_when_eval_not_supplied():
    """Test that normal migration uses PHARMASENSE_DATABASE_URL (or DATABASE_URL)."""
    env = {
        "PHARMASENSE_DATABASE_URL": "postgresql+psycopg2://fake:fake@localhost:5432/dev_db"
    }
    # Ensure EVAL_DATABASE_URL is not set
    if "EVAL_DATABASE_URL" in os.environ:
        env["EVAL_DATABASE_URL"] = ""
    
    url = run_env_py(env)
    assert url == "postgresql+psycopg2://fake:fake@localhost:5432/dev_db"

def test_migration_env_respects_existing_sqlalchemy_url():
    """Test that if a config is passed with sqlalchemy.url already set, env.py doesn't overwrite it."""
    env = {
        "PHARMASENSE_DATABASE_URL": "postgresql+psycopg2://fake:fake@localhost:5432/dev_db",
        "EXPLICIT_URL": "postgresql+psycopg2://fake:fake@localhost:5432/explicit_db"
    }
    url = run_env_py(env)
    assert url == "postgresql+psycopg2://fake:fake@localhost:5432/explicit_db"
