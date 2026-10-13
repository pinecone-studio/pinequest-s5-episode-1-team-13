"""Supabase Storage (PRIVATE bucket): богино хугацаатай signed URL үүсгэнэ.

SUPABASE_SERVICE_ROLE_KEY зөвхөн энд (сервер талд) ашиглагдана.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger("backend.storage")


@lru_cache
def _bucket():
    from supabase import create_client

    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key).storage.from_(s.supabase_storage_bucket)


def sign_paths(paths: Iterable[str | None]) -> dict[str, str]:
    """storage_path -> signed URL. Алдаа гарвал (STORAGE_UPLOAD_ERROR биш, унших алдаа) тухайн зургийг алгасна."""
    unique = sorted({p for p in paths if p})
    if not unique:
        return {}
    try:
        results = _bucket().create_signed_urls(unique, get_settings().signed_url_expire_seconds)
    except Exception as exc:
        logger.error("STORAGE_ERROR: signing failed (%s)", type(exc).__name__)
        return {}
    out: dict[str, str] = {}
    for item in results:
        url = item.get("signedURL") or item.get("signedUrl")
        path = item.get("path")
        if url and path and not item.get("error"):
            out[path] = url
    return out
