"""YOLO wrapper (ultralytics). One instance per camera, because the person tracker keeps state per video."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from app.detection.classes import parse_mapping, resolve_names
from app.detection.device import pick_device
from app.detection.onnx_cache import cached_onnx
from app.detection.tracker import PersonTracker
from app.detection.types import Detection

logger = logging.getLogger("ai.model")


class Detector:
    def __init__(
        self,
        model_path: Path,
        class_mapping: str,
        conf: float,
        imgsz: int,
        device: str = "auto",
        onnx_cache: Path | None = None,
    ) -> None:
        from ultralytics import YOLO  # heavy import, only when a camera actually needs the AI

        self.device = pick_device(device, model_path)
        if onnx_cache is not None and self.device == "cpu":  # CPU only: ONNX Runtime is ~1.7x faster there
            fast = cached_onnx(model_path, imgsz, onnx_cache)
            if fast is not None:
                model_path = fast
        self._model = YOLO(str(model_path), task="detect")
        self._names = resolve_names(dict(self._model.names), parse_mapping(class_mapping))
        self._conf, self._imgsz = conf, imgsz
        self._tracker = PersonTracker()
        if "person" not in self._names.values():
            logger.warning("Model has no 'person' class: nobody can be checked. Fix CLASS_MAPPING or the model.")
        logger.info("Model loaded: %s | device=%s | classes used: %s", model_path.name, self.device, sorted(set(self._names.values())))

    def __call__(self, frame: np.ndarray) -> list[Detection]:
        # predict, not track: ultralytics' tracker drops new helmet/vest boxes (see tracker.py)
        result = self._model.predict(frame, conf=self._conf, imgsz=self._imgsz, device=self.device, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            self._tracker.update([])
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        classes = boxes.cls.cpu().numpy().astype(int)
        found = []
        for box, conf, cls in zip(xyxy, confs, classes):
            name = self._names.get(int(cls))
            if name:
                found.append((name, float(conf), tuple(float(v) for v in box)))
        person_ids = iter(self._tracker.update([box for name, _, box in found if name == "person"]))
        return [Detection(name, conf, box, next(person_ids) if name == "person" else None) for name, conf, box in found]
