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

    # YOLO model (.pt or .onnx). Relative paths start from the ai-service folder.
    model_path: str = ""
    # Model class name -> our class name, e.g. "hardhat:helmet,no-hardhat:no_helmet". Empty = model already uses our names.
    class_mapping: str = ""
    conf_threshold: float = Field(0.4, ge=0.05, le=0.95)
    imgsz: int = Field(640, ge=256, le=1920)
    detect_fps: float = Field(3, ge=0.5, le=15)  # AI runs this many times per second per camera

    # Violation rules
    violation_confirm_seconds: float = Field(2.0, ge=0, le=60)  # must be seen this long before it is saved
    violation_cooldown_seconds: float = Field(60, ge=5, le=3600)  # same person + same type: save again only after this

    # Supabase Storage for snapshot pictures (same as backend/.env)
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "violation-snapshots"

    @property
    def resolved_model_path(self) -> Path:
        path = Path(self.model_path)
        return path if path.is_absolute() else (SERVICE_ROOT / path).resolve()

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
        if not self.model_path or not self.resolved_model_path.is_file():
            problems.append("MODEL_PATH (file not found)")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
