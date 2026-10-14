"""AI service settings. All values come from ai-service/.env (never commit .env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parent.parent
_PLACEHOLDERS = {"", "CHANGE_ME"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(SERVICE_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    backend_url: str = "http://localhost:8000"
    internal_api_key: str = ""
    heartbeat_seconds: float = Field(10, ge=1, le=25)  # backend timeout is 30s
    log_level: str = "INFO"

    @property
    def backend_base(self) -> str:
        return self.backend_url.rstrip("/")

    def startup_problems(self) -> list[str]:
        """Settings that must be filled before the service can run."""
        problems = []
        if self.internal_api_key in _PLACEHOLDERS:
            problems.append("INTERNAL_API_KEY")
        if not self.backend_url.startswith(("http://", "https://")):
            problems.append("BACKEND_URL")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
