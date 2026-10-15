"""CAMERA_SECRET_KEY солих: DB дахь камерын нууц үгийг шинэ түлхүүрээр дахин шифрлэнэ (нэг transaction).

Хуучин түлхүүр = одоогийн CAMERA_SECRET_KEY (backend/.env). Шинэ түлхүүрийг NEW_CAMERA_SECRET_KEY env-ээс авна,
байхгүй бол нуугдмалаар асууна (shell history-д үлдэхгүй). Түлхүүрийг хэзээ ч хэвлэхгүй.
Дараалал: ai-service зогсоох -> энэ скрипт -> Railway, ai-service/.env-ийн CAMERA_SECRET_KEY-г шинээр солих -> асаах (SECURITY.md).

cd backend && python -m scripts.rotate_camera_key --dry-run   # бүх нууц үг тайлагдаж байгааг шалгана, өөрчлөхгүй
cd backend && python -m scripts.rotate_camera_key
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Hashable

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select, update

from app.config import get_settings
from app.database.database import new_session
from app.database.models import Camera


def rotate_tokens(tokens: dict[Hashable, str], old_key: str, new_key: str) -> dict[Hashable, str]:
    """{id: token} -> {id: шинэ түлхүүрээр шифрлэсэн token}.

    Аль нэг нь хуучин (эсвэл аль хэдийн шинэ) түлхүүрээр тайлагдахгүй бол ValueError — хэсэгчлэн солихгүй.
    """
    rotator = MultiFernet([Fernet(new_key.encode("ascii")), Fernet(old_key.encode("ascii"))])
    rotated, bad = {}, 0
    for key, token in tokens.items():
        try:
            rotated[key] = rotator.rotate(token.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError):
            bad += 1
    if bad:
        raise ValueError(f"{bad} камерын нууц үг одоогийн CAMERA_SECRET_KEY-ээр тайлагдсангүй")
    return rotated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAMERA_SECRET_KEY солих (камерын нууц үгийг дахин шифрлэнэ)")
    parser.add_argument("--dry-run", action="store_true", help="шалгаад зогсоно, DB-д бичихгүй")
    args = parser.parse_args(argv)

    old_key = get_settings().camera_secret_key
    new_key = os.environ.get("NEW_CAMERA_SECRET_KEY", "").strip() or getpass.getpass("Шинэ CAMERA_SECRET_KEY: ").strip()
    try:
        Fernet(old_key.encode("ascii"))
        Fernet(new_key.encode("ascii"))
    except ValueError:
        print("Түлхүүр Fernet формат биш (backend/.env.example-ийн 'Үүсгэх' командыг ашиглана).")
        return 2
    if new_key == old_key:
        print("Шинэ түлхүүр одоогийнхтой ижил байна.")
        return 2

    with new_session() as db:
        rows = db.execute(
            select(Camera.id, Camera.password_encrypted)
            .where(Camera.password_encrypted.is_not(None), Camera.password_encrypted != "")
            .with_for_update()
        ).all()
        try:
            rotated = rotate_tokens(dict(rows), old_key, new_key)
        except ValueError as exc:
            print(f"{exc}. Юу ч өөрчлөгдсөнгүй.")
            return 1
        if args.dry_run:
            print(f"{len(rotated)} камерын нууц үгийг шинэ түлхүүрээр солих боломжтой (dry-run, DB өөрчлөгдсөнгүй).")
            return 0
        for camera_id, token in rotated.items():
            db.execute(update(Camera).where(Camera.id == camera_id).values(password_encrypted=token))
        db.commit()
    print(f"{len(rotated)} камерын нууц үг дахин шифрлэгдлээ. Одоо Railway, ai-service/.env-ийн CAMERA_SECRET_KEY-г шинэ утгаар солино.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
