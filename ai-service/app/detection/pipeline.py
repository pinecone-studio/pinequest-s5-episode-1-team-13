"""Per-camera AI step: detect -> decide PPE -> send live boxes to the dashboard."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from app.backend_client import BackendClient
from app.cameras.quality import measure
from app.dataset.collector import DatasetCollector
from app.cameras.models import CameraInfo
from app.detection.motion import MotionGate
from app.detection.ppe import analyse
from app.detection.smoothing import PersonSmoother
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
        collector: DatasetCollector | None = None,
        motion: MotionGate | None = None,
        min_brightness: float = 0,
        min_sharpness: float = 0,
        no_conf: float = 0.0,
        smooth_window: int = 1,
    ) -> None:
        self._no_conf = no_conf
        self._smoother = PersonSmoother(smooth_window) if smooth_window > 1 else None
        self._motion = motion
        self._min_brightness, self._min_sharpness = min_brightness, min_sharpness
        self._last_problem: str | None = None
        self._client = client
        self._collector = collector
        self._rules, self._reporter = rules, reporter
        self._make_detector = make_detector
        self._detector = None
        self._interval = 1.0 / detect_fps
        self._last_run = float("-inf")  # first frame always runs
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
        if self._motion is not None and not self._motion.should_run(frame, now, people_last_time=not self._sent_empty):
            return None  # nothing moved and nobody was there: the dashboard already shows no boxes
        if self._detector is None:
            self._detector = self._make_detector()

        height, width = frame.shape[:2]
        detections = self._detector(frame)
        people = analyse(detections, helmet_required=camera.zone_type != "OFFICE", no_conf=self._no_conf)
        if self._smoother is not None:
            people = self._smoother.apply(people)  # majority of the last few results per person: no flicker
        if people or not self._sent_empty:
            self._client.detections(camera.id, [p.to_payload(width, height) for p in people])
        self._sent_empty = not people

        # Live boxes are always shown, but a dark or blurry frame is not trusted for saving anything
        problem = self.frame_problem(frame, camera.name) if (self._rules or self._collector) else None
        if problem is None:
            if self._rules is not None and self._reporter is not None:
                for vtype, person in self._rules.update(people, now):
                    self._reporter.submit(camera, frame, person, vtype)
            if self._collector is not None:
                self._collector.maybe_save(frame, camera.name, camera.id, detections, now)
        return people

    def frame_problem(self, frame: np.ndarray, camera_name: str) -> str | None:
        if not self._min_brightness and not self._min_sharpness:
            return None
        quality = measure(frame)
        problem = quality.problem(self._min_brightness, self._min_sharpness)
        if problem != self._last_problem:  # log only when it changes, not every frame
            if problem:
                logger.warning("%s: frame %s (brightness %.0f, sharpness %.0f) — not saving violations",
                               camera_name, problem, quality.brightness, quality.sharpness)  # fmt: skip
            else:
                logger.info("%s: picture quality OK again", camera_name)
            self._last_problem = problem
        return problem
