"""Set, show or remove the restricted area of a camera (saved in the DB, the AI picks it up within ~10 s).

    python -m scripts.set_area --list
    python -m scripts.set_area "Gate camera" "0.6,0.5 0.95,0.5 0.95,0.95 0.6,0.95"
    python -m scripts.set_area "Gate camera" "0.6,0.5 0.95,0.5 0.95,0.95" --add     # a second area
    python -m scripts.set_area "Gate camera" --clear

Points = parts of the picture width/height (0..1), at least 3, on the picture the AI sees (after rotation,
before mirroring). Test the points first on a photo:  python -m scripts.demo photo.jpg --area "..."
Uses DATABASE_URL from .env.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.detection.areas import SETTING_KEY, clean_polygons, parse_points

UPSERT_SQL = """
INSERT INTO app_settings (key, value, updated_at) VALUES (%s, %s::jsonb, now())
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
"""


def find_camera(db, name_or_id: str) -> tuple[str, str] | None:
    rows = db.fetch("SELECT id::text, name FROM cameras WHERE id::text = %s OR lower(name) = lower(%s)", (name_or_id, name_or_id))
    return (rows[0][0], rows[0][1]) if rows else None


def load(db) -> dict:
    rows = db.fetch("SELECT value FROM app_settings WHERE key = %s", (SETTING_KEY,))
    value = rows[0][0] if rows else {}
    return value if isinstance(value, dict) else {}


def update(areas: dict, camera_id: str, polygon=None, add: bool = False, clear: bool = False) -> dict:
    areas = dict(areas)
    if clear:
        areas.pop(camera_id, None)
    else:
        old = clean_polygons(areas.get(camera_id)) if add else []
        areas[camera_id] = [[list(p) for p in poly] for poly in [*old, polygon]]
    return areas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restricted area per camera")
    parser.add_argument("camera", nargs="?", help="camera name or id")
    parser.add_argument("points", nargs="?", help='e.g. "0.6,0.5 0.95,0.5 0.95,0.95 0.6,0.95"')
    parser.add_argument("--add", action="store_true", help="keep the old areas and add this one")
    parser.add_argument("--clear", action="store_true", help="remove all areas of the camera")
    parser.add_argument("--list", action="store_true", help="show all cameras with areas")
    args = parser.parse_args(argv)

    from app.config import get_settings
    from app.db import Database

    db = Database(get_settings().database_url)
    try:
        areas = load(db)
        if args.list or not args.camera:
            names = dict(db.fetch("SELECT id::text, name FROM cameras"))
            if not areas:
                print("No restricted areas.")
            for cam_id, polys in areas.items():
                for poly in clean_polygons(polys):
                    print(f"{names.get(cam_id, cam_id)}: " + " ".join(f"{x:g},{y:g}" for x, y in poly))
            return 0
        camera = find_camera(db, args.camera)
        if camera is None:
            print(f"Camera not found: {args.camera}", file=sys.stderr)
            return 1
        cam_id, name = camera
        if args.clear:
            new = update(areas, cam_id, clear=True)
        else:
            if not args.points:
                print("Give the points, or use --clear", file=sys.stderr)
                return 1
            try:
                new = update(areas, cam_id, parse_points(args.points), add=args.add)
            except ValueError as exc:
                print(exc, file=sys.stderr)
                return 1
        db.execute(UPSERT_SQL, (SETTING_KEY, json.dumps(new)))
        count = len(clean_polygons(new.get(cam_id)))
        print(f"{name}: {count} restricted area(s). The AI uses it within ~10 s.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
