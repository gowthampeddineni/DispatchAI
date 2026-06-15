"""Central configuration. Secrets and model names come from env / .env only."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Put .env into os.environ too: the OpenAI / LangSmith SDKs read it from there
# (that's how LangSmith auto-traces everything with zero span code).
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="DISPATCHAI_",
        extra="ignore",
    )

    # --- LLM tiering (route by task complexity, not agent identity) ---
    small_model: str = "gpt-4o-mini"   # routing / extraction / position formation
    large_model: str = "gpt-4o"        # planning / conflict resolution / synthesis
    llm_mode: str = "auto"             # auto | live | rules

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8000

    # --- data ---
    db: str = "data/dispatchai.db"

    @property
    def db_path(self) -> Path:
        p = Path(self.db)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def openai_api_key(self) -> str:
        return os.environ.get("OPENAI_API_KEY", "")

    @property
    def llm_enabled(self) -> bool:
        """LLM path is used when forced live, or in auto mode with a key present."""
        if self.llm_mode == "rules":
            return False
        if self.llm_mode == "live":
            return True
        return bool(self.openai_api_key)

    def model_for(self, task: str) -> str:
        """Single configurable task -> model mapping (cost/latency tuning point)."""
        routing = {
            "classification": self.small_model,
            "extraction": self.small_model,
            "agent_position": self.small_model,
            "summary": self.small_model,
            "planning": self.large_model,
            "synthesis": self.large_model,
            "fix_suggestion": self.large_model,
            "chat": self.large_model,          # copilot Q&A reasons across systems
        }
        return routing.get(task, self.small_model)


settings = Settings()
