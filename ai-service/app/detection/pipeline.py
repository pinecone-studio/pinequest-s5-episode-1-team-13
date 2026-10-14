"""Per-camera AI step: detect -> decide PPE -> send live boxes to the dashboard."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from app.backend_client import BackendClient
from app.cameras.models import CameraInfo
from app.detection.ppe import analyse
from app.detection.types import Detection, PersonResult
from app.violations.reporter import ViolationReporter
from app.violations.rules import ViolationRules

logger = logging.getLogger("ai.pipeline")


class CameraAI:
    def __init__(
        self,
        client: BackendClient,
        make_detector: Callable[[], Callable[[np.ndarray], list[Detection]]],
        detect_fps: float,
        rules: ViolationRules | None = None,
        reporter: ViolationReporter | None = None,
    ) -> None:
        self._client = client
        self._rules, self._reporter = rules, reporter
        self._make_detector = make_detector
        self._detector = None
        self._interval = 1.0 / detect_fps
        self._last_run = 0.0
        self._sent_empty = True

    def process(self, frame: np.ndarray, camera: CameraInfo, now: float) -> list[PersonResult] | None:
        """Returns the people found, or None when the AI did not run on this frame."""
        if not camera.ai_enabled:
            if not self._sent_empty:  # clear the boxes on the dashboard once
                self._client.detections(camera.id, [])
                self._sent_empty = True
            return None
        if now - self._last_run < self._interval:
            return None
        self._last_run = now
        if self._detector is None:
            self._detector = self._make_detector()

        height, width = frame.shape[:2]
        people = analyse(self._detector(frame), helmet_required=camera.zone_type != "OFFICE")
        if people or not self._sent_empty:
            self._client.detections(camera.id, [p.to_payload(width, height) for p in people])
        self._sent_empty = not people

        if self._rules is not None and self._reporter is not None:
            for vtype, person in self._rules.update(people, now):
                self._reporter.submit(camera, frame, person, vtype)
        return people
