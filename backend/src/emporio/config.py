"""Application settings, read once from the environment (.env)."""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ClassifierProvider = Literal["auto", "openai", "jev"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Providers
    openai_api_key: SecretStr | None = None
    typesafe_api_key: SecretStr | None = None
    classifier_provider: ClassifierProvider = "auto"
    agent_model: str = "gpt-6.1-terra"
    agent_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"
    agent_max_output_tokens: int = 1200
    agent_max_tool_rounds: int = 6
    classifier_model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 1.5
    # Extra LLM review of each reply. Measured: +~2 s per turn and no catches beyond the code checks.
    output_review: bool = False

    # Infrastructure
    database_url: str = "postgresql+psycopg://emporio:emporio@localhost:5432/emporio"
    data_dir: Path = Path("data/raw")

    # Business clock
    app_timezone: str = "America/Campo_Grande"
    app_reference_date: date | None = None

    # Conversation
    history_window: int = 12

    # Public demo protection
    rate_limit_per_ip: int = 20
    rate_limit_window_seconds: int = 600
    max_turns_per_conversation: int = 40
    rate_limit_global_per_day: int = 1000

    release_id: str = "local"
    log_level: str = "INFO"

    @field_validator("openai_api_key", "typesafe_api_key", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @field_validator("app_reference_date", mode="before")
    @classmethod
    def _empty_date_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @property
    def jev_enabled(self) -> bool:
        return self.classifier_provider != "openai" and self.typesafe_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
