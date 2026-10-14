"""Хүн бүрийн хайчилбарын геометр. Сургалт (training/crops.py) болон бодит шинжилгээ (TwoStageDetector) ЯГ ИЖИЛ дүрмийг ашиглана.

Яагаад: Dahua дээр хүн ~100–200 px өндөртэй тул бүтэн frame-ийг 640 болгоход 50–100 px болж каск, хувцас алдагддаг.
Хүнийг хайчилж 512 хүртэл томруулбал (Mac камерын ойрхон дүр зурагтай ижил хэмжээ) ойлгомжтой болно.
"""

from __future__ import annotations

MARGIN_X = 0.35  # хүний өргөний хувиар хоёр талдаа
MARGIN_Y = 0.15  # хүний өндрийн хувиар дээш/доош
SIDE = 512  # хайчилбарын урт тал энэ хэмжээнд хүртэл томрон (дээд талдаа MAX_UPSCALE)
MAX_UPSCALE = 4.0
MIN_PERSON_PX = 32  # үүнээс бага өндөртэй хүн дээр дүгнэлт хийхгүй (хэт жижиг)


def crop_region(x1: float, y1: float, x2: float, y2: float, width: int, height: int,
                margin_x: float = MARGIN_X, margin_y: float = MARGIN_Y) -> tuple[int, int, int, int]:
    """Хүний хайрцгийг (пиксел) margin-тай хайчлах мужид (frame дотор clip хийсэн) хөрвүүлнэ."""
    w, h = x2 - x1, y2 - y1
    return (
        max(0, int(x1 - margin_x * w)), max(0, int(y1 - margin_y * h)),
        min(width, int(x2 + margin_x * w) + 1), min(height, int(y2 + margin_y * h) + 1),
    )


def scale_for(crop_w: int, crop_h: int, side: int = SIDE, max_up: float = MAX_UPSCALE) -> float:
    """Хайчилбарыг урт талаар нь `side` болгох масштаб (багасгах нь 1.0-ээс бага байж болно)."""
    return min(side / max(1, max(crop_w, crop_h)), max_up)
