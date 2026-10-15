"""Backend тохиргоо. Бүх нууц утга .env-ээс. Frontend-д ХЭЗЭЭ Ч очихгүй."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
_PLACEHOLDERS = {"", "CHANGE_ME"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    app_env: str = "development"  # production үед /docs унтарна

    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "violation-snapshots"
    signed_url_expire_seconds: int = Field(3600, ge=60, le=86400)

    camera_secret_key: str = ""
    jwt_secret: str = ""
    internal_api_key: str = ""
    jwt_expire_minutes: int = Field(480, ge=5)
    cookie_secure: bool = False

    # Browser-ийн холбогдох MediaMTX WebRTC (WHEP) хаяг. LAN/production дээр домэйнээр солино.
    mediamtx_public_url: str = "http://localhost:8889"
    stream_token_expire_seconds: int = Field(120, ge=30, le=900)
    # Browser-ийн WebRTC ICE серверүүд (таслалаар). Хоосон STUN = зөвхөн шууд/TURN холболт.
    webrtc_stun_urls: str = "stun:stun.l.google.com:19302"
    # TURN: шууд холбогдож чадахгүй (symmetric NAT, UDP хаалттай) үед видеог дамжуулна. Хоосон = TURN-гүй.
    turn_urls: str = ""
    # coturn use-auth-secret: static-auth-secret-ээс хэрэглэгч бүрт богино хугацаатай credential үүсгэнэ (нууц browser-т очихгүй)
    turn_secret: str = ""
    # TURN_SECRET байхгүй үед: үйлчилгээний өгсөн статик credential
    turn_username: str = ""
    turn_password: str = ""
    turn_credential_ttl_seconds: int = Field(86400, ge=300, le=172800)
    # false = backend камертай өөр сүлжээнд (cloud) — холболтын тестийг backend-ээс хийхгүй, AI service шалгана
    camera_probe_enabled: bool = True
    # Login хуудасны "Demo" товч: энэ имэйлтэй HUB_EMPLOYEE (админ биш) хэрэглэгчээр нууц үггүй нэвтэрнэ
    demo_login_enabled: bool = False
    demo_user_email: str = "demo@pinequest.app"

    # Snapshot зураг + зөрчлийн бүртгэлийг энэ хугацаанаас хойш автоматаар устгана (минут). 0 = хэзээ ч устгахгүй.
    snapshot_retention_minutes: int = Field(10080, ge=0)  # анхдагч 7 хоног

    # Сургалтын хавтас (өгөгдөл, шошго, модель). ai-service-ийн DATASET_DIR-тэй нэг байрлалд байх ёстой.
    training_dir: str = "../training"

    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_dir: str = "./logs"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    def is_demo_email(self, email: str) -> bool:
        return self.demo_login_enabled and email.lower() == self.demo_user_email.lower()

    @property
    def resolved_training_dir(self) -> Path:
        path = Path(self.training_dir)
        return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def resolved_log_dir(self) -> Path:
        path = Path(self.log_dir)
        return path if path.is_absolute() else (BACKEND_ROOT / path).resolve()

    def startup_problems(self) -> list[str]:
        """Аюулгүй ажиллахад заавал хэрэгтэй, бөглөгдөөгүй түлхүүрүүд."""
        problems = []
        if not self.database_url.startswith(("postgresql://", "postgres://")) or "USER:PASSWORD@HOST" in self.database_url:
            problems.append("DATABASE_URL")
        for name in ("camera_secret_key", "jwt_secret", "internal_api_key"):
            if getattr(self, name) in _PLACEHOLDERS:
                problems.append(name.upper())
        if len(self.jwt_secret) < 32 and self.jwt_secret not in _PLACEHOLDERS:
            problems.append("JWT_SECRET (>= 32 тэмдэгт)")
        if not self.supabase_url.startswith("https://") or "YOUR_PROJECT" in self.supabase_url:
            problems.append("SUPABASE_URL")
        if self.supabase_service_role_key in _PLACEHOLDERS | {"YOUR_SERVICE_ROLE_KEY"}:
            problems.append("SUPABASE_SERVICE_ROLE_KEY")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
