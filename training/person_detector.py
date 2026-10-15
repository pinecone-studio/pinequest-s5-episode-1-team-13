"""Хүн олох 1-р шат: COCO-оор өмнө нь сургасан YOLO (манай сургалтгүй). Зөвхөн хүний анги л хэрэгтэй.

Нормчилгоогүй (x1, y1, x2, y2, итгэлцэл) пиксел координат буцаана.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class PersonDetector:
    def __init__(self, model_path: Path, confidence: float = 0.30, imgsz: int = 960, device: str = "") -> None:
        self._path, self._conf, self._imgsz, self._device = Path(model_path), confidence, imgsz, device or None
        self._model = None

    def load(self) -> None:
        if not self._path.is_file():
            raise FileNotFoundError(f"Хүн олох модель олдсонгүй: {self._path}")
        from ultralytics import YOLO

        self._model = YOLO(str(self._path))

    def detect(self, frame: np.ndarray) -> list[tuple[float, float, float, float, float]]:
        res = self._model.predict(frame, classes=[0], conf=self._conf, imgsz=self._imgsz, device=self._device, verbose=False)[0]
        if res.boxes is None or len(res.boxes) == 0:
            return []
        return [(float(x1), float(y1), float(x2), float(y2), float(c))
                for (x1, y1, x2, y2), c in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy())]
