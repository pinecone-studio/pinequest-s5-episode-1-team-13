"""DEMO_USER_ROLE=ADMIN: demo хэрэглэгч админ эрхтэй, гэхдээ DB-д HUB_EMPLOYEE хэвээр, бусад хэрэглэгчид нөлөөлөхгүй."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import cameras
from app.api.deps import effective_role, require_admin, require_camera_manager
from app.config import get_settings
from app.database.models import UserRole
from app.schemas.auth import UserOut

DEMO = "demo-pytest@example.com"


def _user(email: str, role: UserRole = UserRole.HUB_EMPLOYEE):
    return SimpleNamespace(
        id=uuid.uuid4(), email=email, full_name=None, role=role, is_active=True, created_at=datetime.now(UTC), last_login_at=None
    )


@pytest.fixture
def demo(monkeypatch):
    def configure(role: str, enabled: bool = True):
        settings = get_settings()
        monkeypatch.setattr(settings, "demo_login_enabled", enabled)
        monkeypatch.setattr(settings, "demo_user_email", DEMO)
        monkeypatch.setattr(settings, "demo_user_role", role)

    return configure


def test_demo_is_admin_only_when_demo_user_role_is_admin(demo):
    demo("HUB_EMPLOYEE")
    assert effective_role(_user(DEMO)) is UserRole.HUB_EMPLOYEE
    with pytest.raises(HTTPException) as err:
        require_admin(_user(DEMO))
    assert err.value.status_code == 403
    assert UserOut.model_validate(_user(DEMO)).role is UserRole.HUB_EMPLOYEE

    demo("ADMIN")
    assert effective_role(_user(DEMO)) is UserRole.ADMIN
    assert require_admin(_user(DEMO)).email == DEMO
    assert require_camera_manager(_user(DEMO)).email == DEMO
    out = UserOut.model_validate(_user(DEMO))
    assert out.role is UserRole.ADMIN and out.is_demo  # frontend админы цэсийг харуулна


def test_demo_admin_needs_demo_login_enabled_and_never_touches_other_users(demo):
    demo("ADMIN", enabled=False)
    assert effective_role(_user(DEMO)) is UserRole.HUB_EMPLOYEE

    demo("ADMIN")
    employee = _user("someone@example.com")
    assert effective_role(employee) is UserRole.HUB_EMPLOYEE
    assert UserOut.model_validate(employee).role is UserRole.HUB_EMPLOYEE
    with pytest.raises(HTTPException):
        require_admin(employee)


def test_demo_admin_may_manage_any_camera_but_plain_demo_only_its_own(demo, monkeypatch):
    camera_id = uuid.uuid4()
    monkeypatch.setattr(cameras, "_get_or_404", lambda db, cid: SimpleNamespace(id=cid))
    monkeypatch.setattr(cameras, "_demo_camera_ids", lambda db: set())  # not added by demo

    demo("HUB_EMPLOYEE")
    with pytest.raises(HTTPException) as err:
        cameras._get_managed(None, camera_id, _user(DEMO))
    assert err.value.status_code == 403

    demo("ADMIN")
    assert cameras._get_managed(None, camera_id, _user(DEMO)).id == camera_id
