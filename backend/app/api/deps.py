"""Нэвтрэлт ба эрхийн шалгалт."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import constant_time_equals, decode_access_token, decode_ws_token
from app.database.database import get_db
from app.database.models import User, UserRole

COOKIE_NAME = "access_token"


def user_from_token(db: Session, token: str | None, *, ws: bool = False) -> User | None:
    if not token:
        return None
    user_id = decode_ws_token(token) if ws else decode_access_token(token)
    if not user_id:
        return None
    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError:
        return None
    return user if user and user.is_active else None  # эрх (role)-ийг токеноос биш DB-ээс авна


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_token(db, request.cookies.get(COOKIE_NAME))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def effective_role(user: User) -> UserRole:
    """DEMO_USER_ROLE=ADMIN үед demo хэрэглэгч админ эрхтэй (DB-д HUB_EMPLOYEE хэвээр)."""
    return UserRole.ADMIN if get_settings().is_demo_admin(user.email) else user.role


def require_roles(*roles: UserRole):
    def checker(user: User = Depends(get_current_user)) -> User:
        if effective_role(user) not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


require_admin = require_roles(UserRole.ADMIN)
require_staff = require_roles(UserRole.ADMIN, UserRole.HUB_EMPLOYEE)  # violation acknowledge/resolve


def require_camera_manager(user: User = Depends(get_current_user)) -> User:
    """ADMIN эсвэл demo хэрэглэгч (demo нь зөвхөн өөрийн нэмсэн камерыг өөрчилнө — cameras.py)."""
    if effective_role(user) is UserRole.ADMIN or get_settings().is_demo_email(user.email):
        return user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")


def verify_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    """ai-service -> backend дотоод дуудлага."""
    expected = get_settings().internal_api_key
    if not x_internal_key or not expected or not constant_time_equals(x_internal_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid internal key")
