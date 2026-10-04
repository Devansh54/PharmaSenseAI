"""Central configuration for PharmaSenseAI."""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional

from pharmasense.llm.retry import RetryPolicy
from pharmasense.llm.usage import DEFAULT_PRICING

import importlib.metadata

try:
    APP_VERSION = importlib.metadata.version("pharmasenseai")
except importlib.metadata.PackageNotFoundError:
    APP_VERSION = "0.1.0-dev"

# --- Base Paths ---
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "pharmasense_synthetic_data_csv"
REPORTS_DIR = REPO_ROOT / "reports"
PROVENANCE_DIR = REPO_ROOT / "provenance"
GOLDEN_SET_PATH = REPO_ROOT / "evals" / "golden_set.json"

CSV_FILES = {
    "compounds": DATA_DIR / "compounds.csv",
    "clinical_trials": DATA_DIR / "clinical_trials.csv",
    "trial_sites": DATA_DIR / "trial_sites.csv",
    "lab_results": DATA_DIR / "lab_results.csv",
    "adverse_events": DATA_DIR / "adverse_events.csv",
    "research_documents": DATA_DIR / "research_documents.csv",
    "agent_interaction_logs": DATA_DIR / "agent_interaction_logs.csv",
}

# --- Database ---
DATABASE_URL = os.environ.get(
    "PHARMASENSE_DATABASE_URL",
    "postgresql+psycopg2://pharmasense:pharmasense@localhost:5432/pharmasense",
)

# --- LLM Gateway ---
LLM_PROVIDER_NAME = os.environ.get("LLM_PROVIDER", "openai")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", os.environ.get("PHARMASENSE_LLM_MODEL", "gpt-4o-mini"))
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("PHARMASENSE_LLM_TIMEOUT_SECONDS", "30"))
DEFAULT_MAX_RETRIES = int(os.environ.get("PHARMASENSE_LLM_MAX_RETRIES", "2"))

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_BASE_URL_ENV = "OPENAI_BASE_URL"
OPENAI_ORG_ENV = "OPENAI_ORG_ID"

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GROQ_API_KEY_ENV = "GROQ_API_KEY"

@dataclass(frozen=True)
class GatewayConfig:
    """Runtime configuration for `LLMGateway`."""
    model: str = DEFAULT_MODEL
    request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    retry_policy: RetryPolicy = field(
        default_factory=lambda: RetryPolicy(max_retries=DEFAULT_MAX_RETRIES)
    )
    pricing: Dict[str, Dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_PRICING))

@dataclass(frozen=True)
class OpenAIAdapterConfig:
    """Configuration specific to the OpenAI SDK adapter."""
    model: str = DEFAULT_MODEL
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_API_KEY_ENV))
    base_url: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_BASE_URL_ENV))
    organization: Optional[str] = field(default_factory=lambda: os.environ.get(OPENAI_ORG_ENV))
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key)

@dataclass(frozen=True)
class GeminiAdapterConfig:
    """Configuration specific to the Gemini SDK adapter."""
    model: str = DEFAULT_MODEL
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get(GEMINI_API_KEY_ENV))
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key)

@dataclass(frozen=True)
class GroqAdapterConfig:
    """Configuration specific to the Groq SDK adapter."""
    model: str = DEFAULT_MODEL
    api_key: Optional[str] = field(default_factory=lambda: os.environ.get(GROQ_API_KEY_ENV))
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        return bool(self.api_key)

# --- RAG Foundation ---
CHUNK_TARGET_TOKENS = int(os.environ.get("PHARMASENSE_CHUNK_TARGET_TOKENS", "400"))
CHUNK_OVERLAP_TOKENS = int(os.environ.get("PHARMASENSE_CHUNK_OVERLAP_TOKENS", "50"))

EMBEDDING_MODEL_NAME = os.environ.get("PHARMASENSE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("PHARMASENSE_EMBEDDING_DIM", "384"))
INDEX_VERSION = os.environ.get("PHARMASENSE_INDEX_VERSION", "phase3-v1")
DEFAULT_TOP_K = int(os.environ.get("PHARMASENSE_RETRIEVAL_TOP_K", "5"))

__all__ = [
    "DATABASE_URL",
    "REPO_ROOT",
    "DATA_DIR",
    "REPORTS_DIR",
    "PROVENANCE_DIR",
    "GOLDEN_SET_PATH",
    "CSV_FILES",
    "CHUNK_TARGET_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "INDEX_VERSION",
    "DEFAULT_TOP_K",
]
