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

    # Same Supabase PostgreSQL as the backend (cameras, zones, violations tables)
    database_url: str = ""
    # Same Fernet key as backend/.env — used to decrypt camera passwords
    camera_secret_key: str = ""

    # MediaMTX RTSP address. The AI publishes IP/webcam video here and reads BROWSER cameras from here.
    mediamtx_rtsp_url: str = "rtsp://localhost:8554"
    publish_video: bool = True  # false: only analyse, don't send video to MediaMTX
    publish_fps: int = Field(15, ge=1, le=30)
    # Re-read the camera list from the database this often (seconds). New/removed/rotated cameras apply within this time.
    camera_refresh_seconds: float = Field(10, ge=2, le=300)

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
        if not self.database_url.startswith(("postgresql://", "postgres://")) or "USER:PASSWORD@HOST" in self.database_url:
            problems.append("DATABASE_URL")
        if self.camera_secret_key in _PLACEHOLDERS:
            problems.append("CAMERA_SECRET_KEY")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
