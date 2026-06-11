"""Tests run against the deterministic policy engine (no OpenAI key needed)."""
import os

os.environ["DISPATCHAI_LLM_MODE"] = "rules"  # before config import

import pytest

from config import settings
from data.seed_db import seed


@pytest.fixture(scope="session", autouse=True)
def seeded_db():
    seed(settings.db_path)
    yield
