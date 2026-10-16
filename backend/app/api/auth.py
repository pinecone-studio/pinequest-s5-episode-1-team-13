from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, get_current_user
from app.config import get_settings
from app.core.rate_limit import login_limiter
from app.core.security import WS_TOKEN_SECONDS, create_access_token, create_ws_token, hash_password, verify_password_constant_time
from app.database.database import get_db
from app.database.models import User, UserRole
from app.schemas.auth import LoginRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    key = f"{request.client.host if request.client else '-'}|{email}"
    locked = login_limiter.is_locked(key)
    if locked:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Хэт олон оролдлого. {locked} секундын дараа дахин оролдоно уу.")

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    ok = verify_password_constant_time(body.password.get_secret_value(), user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        login_limiter.fail(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")  # аль нь буруу гэдгийг хэлэхгүй

    login_limiter.success(key)
    _start_session(user, response, db)
    return user


@router.get("/demo")
def demo_status():
    return {"enabled": get_settings().demo_login_enabled}


@router.post("/demo", response_model=UserOut)
def demo_login(response: Response, db: Session = Depends(get_db)):
    """Нууц үггүй demo нэвтрэлт. Хэрэглэгч байхгүй бол HUB_EMPLOYEE-ээр үүсгэнэ (нууц үг нь санамсаргүй, ашиглагдахгүй)."""
    settings = get_settings()
    if not settings.demo_login_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")

    email = settings.demo_user_email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name="Demo", password_hash=hash_password(secrets.token_urlsafe(32)), role=UserRole.HUB_EMPLOYEE)
        db.add(user)
        db.flush()
    if user.role is not UserRole.HUB_EMPLOYEE or not user.is_active:  # бодит админы бүртгэлээр demo-гоор хэзээ ч нэвтрэхгүй (DEMO_USER_ROLE-оос үл хамаарна)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo нэвтрэлт идэвхгүй байна")

    _start_session(user, response, db)
    return user


def _start_session(user: User, response: Response, db: Session) -> None:
    user.last_login_at = datetime.now(UTC)
    db.commit()

    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(str(user.id)),
        max_age=settings.jwt_expire_minutes * 60,
        # Frontend (Vercel) ба backend (Railway) өөр домэйн тул HTTPS дээр SameSite=None шаардлагатай
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if settings.cookie_secure else "lax",
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    secure = get_settings().cookie_secure
    response.delete_cookie(COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="none" if secure else "lax")


@router.get("/ws-token")
def ws_token(user: User = Depends(get_current_user)):
    """WebSocket-д зориулсан богино хугацаатай токен (cookie backend-ийн домэйнд хүрэхгүй үед)."""
    return {"token": create_ws_token(str(user.id)), "expires_in": WS_TOKEN_SECONDS}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
