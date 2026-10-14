"""YOLO wrapper (ultralytics). One instance per camera, because the tracker (person ids) keeps state per video."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from app.detection.classes import parse_mapping, resolve_names
from app.detection.types import Detection

logger = logging.getLogger("ai.model")


class Detector:
    def __init__(self, model_path: Path, class_mapping: str, conf: float, imgsz: int) -> None:
        from ultralytics import YOLO  # heavy import, only when a camera actually needs the AI

        self._model = YOLO(str(model_path), task="detect")
        self._names = resolve_names(dict(self._model.names), parse_mapping(class_mapping))
        self._conf, self._imgsz = conf, imgsz
        if "person" not in self._names.values():
            logger.warning("Model has no 'person' class: nobody can be checked. Fix CLASS_MAPPING or the model.")
        logger.info("Model loaded: %s | classes used: %s", model_path.name, sorted(set(self._names.values())))

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        result = self._model.track(frame, persist=True, conf=self._conf, imgsz=self._imgsz, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else [None] * len(xyxy)
        out = []
        for box, conf, cls, tid in zip(xyxy, confs, classes, ids):
            name = self._names.get(int(cls))
            if name:
                out.append(Detection(name, float(conf), tuple(float(v) for v in box), int(tid) if tid is not None else None))
        return out
