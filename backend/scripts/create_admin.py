"""İlk ADMIN хэрэглэгч үүсгэх (нууц үгийг terminal дээр нуугдмалаар асууна — shell history-д үлдэхгүй).

cd backend && python -m scripts.create_admin            # имэйл, нэр, нууц үгийг асууна
cd backend && python -m scripts.create_admin you@company.com "Нэр"
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select

from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.database.database import new_session
from app.database.models import User, UserRole


def main() -> int:
    if len(sys.argv) >= 2:
        email, full_name = sys.argv[1].strip().lower(), " ".join(sys.argv[2:]) or None
    else:  # аргументгүй бол асууна
        email = input("Админы имэйл: ").strip().lower()
        full_name = input("Нэр (заавал биш): ").strip() or None
    if "@" not in email:
        print("Имэйл буруу байна.")
        return 2

    password = getpass.getpass(f"Нууц үг (>= {MIN_PASSWORD_LENGTH} тэмдэгт): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Нууц үг хамгийн багадаа {MIN_PASSWORD_LENGTH} тэмдэгттэй байх ёстой.")
        return 1
    if password != getpass.getpass("Нууц үг (давтах): "):
        print("Нууц үг таарсангүй.")
        return 1

    with new_session() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            user.password_hash, user.role, user.is_active = hash_password(password), UserRole.ADMIN, True
            action = "шинэчлэгдлээ"
        else:
            db.add(User(email=email, full_name=full_name, password_hash=hash_password(password), role=UserRole.ADMIN))
            action = "үүслээ"
        db.commit()
    print(f"ADMIN {email} {action}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
