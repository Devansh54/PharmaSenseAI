"""Shared pytest fixtures for Phase 1 tests."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase1.config import CSV_FILES
from phase1.schemas import LOAD_ORDER


@pytest.fixture(scope="session")
def csv_frames():
    return {
        name: pd.read_csv(CSV_FILES[name], dtype=str, keep_default_na=False)
        for name in LOAD_ORDER
    }
