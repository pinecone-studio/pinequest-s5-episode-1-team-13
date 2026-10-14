"""Uploads snapshot pictures to the PRIVATE Supabase Storage bucket. The backend makes short-lived signed URLs from the path."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import uuid4

import httpx

logger = logging.getLogger("ai.storage")


def snapshot_path(camera_id: str, when: datetime | None = None) -> str:
    when = when or datetime.now(UTC)
    return f"{camera_id}/{when:%Y/%m/%d}/{uuid4().hex}.jpg"


class SnapshotStorage:
    def __init__(self, supabase_url: str, service_key: str, bucket: str, transport: httpx.BaseTransport | None = None) -> None:
        self._bucket = bucket
        self.enabled = supabase_url.startswith("https://") and "YOUR_" not in supabase_url + service_key and bool(service_key)
        self._client = httpx.Client(
            base_url=f"{supabase_url.rstrip('/')}/storage/v1",
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
            timeout=httpx.Timeout(15.0),
            transport=transport,
        )

    def upload(self, path: str, data: bytes) -> bool:
        if not self.enabled:
            return False
        try:
            response = self._client.post(
                f"/object/{quote(self._bucket)}/{quote(path)}",
                content=data,
                headers={"Content-Type": "image/jpeg", "x-upsert": "false"},
            )
        except httpx.HTTPError as exc:
            logger.error("STORAGE_UPLOAD_ERROR: %s", type(exc).__name__)
            return False
        if response.status_code >= 400:
            logger.error("STORAGE_UPLOAD_ERROR: HTTP %s", response.status_code)
            return False
        return True

    def close(self) -> None:
        self._client.close()
