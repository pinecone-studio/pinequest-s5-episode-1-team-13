from __future__ import annotations

from pydantic import BaseModel


class DashboardStats(BaseModel):
    cameras_total: int
    cameras_online: int
    violations_total: int
    violations_open: int
    violations_today: int
    by_type: dict[str, int]
    by_zone: dict[str, int]
    ai_status: str  # ONLINE | OFFLINE (AI service-ийн сүүлийн heartbeat-ээс)
