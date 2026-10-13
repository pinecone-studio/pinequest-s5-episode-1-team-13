"""Сургалтын өгөгдөл (цуглуулсан зураг + шошго) ба модель сургалтын процессийг удирдана.

Хавтасны бүтэц (`TRAINING_DIR`, анхдагч `../training`):
    datasets/raw/<нэр>.jpg           ai-service-ийн цуглуулсан frame
    datasets/labels_auto/<нэр>.txt   цуглуулах үеийн AI-ийн санал (шошгоны эхлэл, шалгах шаардлагатай)
    datasets/labels/<нэр>.txt        ХҮНИЙ баталсан шошго (YOLO формат). Файл байгаа = шошглогдсон
                                     (хоосон файл = "энд юу ч байхгүй" гэж батласан зураг)
    runs/state.json, runs/train.log  сургалтын төлөв ба лог
    models/                          суурь жин (base-n.pt ...) ба сургасан модель (.onnx)

Бүх файлын нэр шалгагдана (path traversal байхгүй). Backend зөвхөн энэ хавтас дотор уншиж/бичиж/устгана.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# ai-service/camera ... -ийн canonical class-тай ижил дараалал (YOLO class id = индекс)
CLASSES = ("person", "helmet", "no_helmet", "work_uniform", "no_work_uniform")
# Хүн (person) шошглолтод харагдахгүй: хэрэглэгч зөвхөн каск/хувцсыг шошглоно. Хүний хайрцгийг AI саналаас хадгална,
# байхгүй бол сургалтын өмнө COCO моделоор автоматаар нэмнэ (training/dataset_split.py).
HIDDEN_CLASSES = ("person",)
IMAGE_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.jpg$")
MAX_BOXES = 100
MIN_LABELED_TO_TRAIN = 30
BASE_WEIGHTS = ("n", "s")
IMGSZ_CHOICES = (512, 640, 960, 1280)
EPOCHS_RANGE = (5, 300)


class TrainingError(ValueError):
    """Хэрэглэгчид харуулах боломжтой (нууц мэдээлэлгүй) алдаа."""


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "datasets" / "raw"

    @property
    def labels(self) -> Path:
        return self.root / "datasets" / "labels"

    @property
    def auto(self) -> Path:
        return self.root / "datasets" / "labels_auto"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def state_file(self) -> Path:
        return self.runs / "state.json"

    @property
    def log_file(self) -> Path:
        return self.runs / "train.log"


def valid_name(name: str) -> str:
    if not IMAGE_RE.match(name or ""):
        raise TrainingError("Зургийн нэр буруу байна")
    return name


def _stem(name: str) -> str:
    return valid_name(name)[:-4]


# ------------------------------------------------------------------ зураг, шошго
def counts(root: Path) -> dict:
    p = Paths(root)
    total = labeled = size = 0
    if p.raw.is_dir():
        with os.scandir(p.raw) as it:
            for entry in it:
                if entry.is_file() and IMAGE_RE.match(entry.name):
                    total += 1
                    size += entry.stat().st_size
                    if (p.labels / f"{entry.name[:-4]}.txt").is_file():
                        labeled += 1
    return {"image_count": total, "labeled_count": labeled, "size_bytes": size}


def list_images(root: Path, filter_: str, offset: int, limit: int) -> tuple[int, list[dict]]:
    """Шинэ зураг эхэндээ. filter_: all | unlabeled | labeled."""
    p = Paths(root)
    entries: list[tuple[float, str, bool]] = []
    if p.raw.is_dir():
        with os.scandir(p.raw) as it:
            for entry in it:
                if entry.is_file() and IMAGE_RE.match(entry.name):
                    labeled = (p.labels / f"{entry.name[:-4]}.txt").is_file()
                    if filter_ == "labeled" and not labeled:
                        continue
                    if filter_ == "unlabeled" and labeled:
                        continue
                    entries.append((entry.stat().st_mtime, entry.name, labeled))
    entries.sort(reverse=True)
    page = entries[offset : offset + limit]
    return len(entries), [{"name": n, "labeled": lab} for _, n, lab in page]


def image_path(root: Path, name: str) -> Path:
    path = Paths(root).raw / valid_name(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def _parse_yolo(text: str) -> list[dict]:
    boxes = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            cid = int(parts[0])
            cx, cy, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            continue
        if not 0 <= cid < len(CLASSES):
            continue
        boxes.append(
            {
                "class_name": CLASSES[cid],
                "x1": round(max(0.0, cx - w / 2), 5),
                "y1": round(max(0.0, cy - h / 2), 5),
                "x2": round(min(1.0, cx + w / 2), 5),
                "y2": round(min(1.0, cy + h / 2), 5),
            }
        )
    return boxes


def _read_all(root: Path, name: str) -> tuple[list[dict], str]:
    p = Paths(root)
    stem = _stem(name)
    manual = p.labels / f"{stem}.txt"
    if manual.is_file():
        return _parse_yolo(manual.read_text()), "manual"
    auto = p.auto / f"{stem}.txt"
    if auto.is_file():
        return _parse_yolo(auto.read_text()), "auto"
    return [], "none"


def read_boxes(root: Path, name: str) -> tuple[list[dict], str]:
    """(харагдах хайрцгууд, source): source = manual (хүн баталсан) | auto (AI санал) | none. Хүнийг оруулахгүй."""
    boxes, source = _read_all(root, name)
    return [b for b in boxes if b["class_name"] not in HIDDEN_CLASSES], source


def write_boxes(root: Path, name: str, boxes: list[dict]) -> None:
    p = Paths(root)
    stem = _stem(name)
    image_path(root, name)  # зураг байх ёстой
    if len(boxes) > MAX_BOXES:
        raise TrainingError(f"Нэг зурагт хамгийн ихдээ {MAX_BOXES} хайрцаг")
    lines = []
    hidden, _ = _read_all(root, name)  # нуугдсан ангилал (хүн)-ыг хадгалж үлдээнэ
    boxes = [b for b in boxes if b.get("class_name") not in HIDDEN_CLASSES] + [b for b in hidden if b["class_name"] in HIDDEN_CLASSES]
    for b in boxes:
        cls = b.get("class_name")
        if cls not in CLASSES:
            raise TrainingError("Тодорхойгүй ангилал")
        x1, y1, x2, y2 = (float(b[k]) for k in ("x1", "y1", "x2", "y2"))
        x1, y1, x2, y2 = min(max(x1, 0.0), 1.0), min(max(y1, 0.0), 1.0), min(max(x2, 0.0), 1.0), min(max(y2, 0.0), 1.0)
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise TrainingError("Хайрцгийн координат буруу байна")
        if (x2 - x1) < 0.005 or (y2 - y1) < 0.005:
            raise TrainingError("Хайрцаг хэтэрхий жижиг байна")
        lines.append(f"{CLASSES.index(cls)} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
    p.labels.mkdir(parents=True, exist_ok=True)
    target = p.labels / f"{stem}.txt"
    tmp = target.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""))
    tmp.replace(target)


def delete_image(root: Path, name: str) -> None:
    p = Paths(root)
    stem = _stem(name)
    for path in (p.raw / f"{stem}.jpg", p.labels / f"{stem}.txt", p.auto / f"{stem}.txt"):
        path.unlink(missing_ok=True)


def delete_all(root: Path) -> int:
    """Цуглуулсан бүх зураг + шошгыг устгана. Устгасан зургийн тоог буцаана."""
    p = Paths(root)
    removed = 0
    for directory, pattern in (
        (p.raw, IMAGE_RE),
        (p.labels, re.compile(r"^[A-Za-z0-9_\-]{1,120}\.(txt|tmp)$")),
        (p.auto, re.compile(r"^[A-Za-z0-9_\-]{1,120}\.txt$")),
    ):
        if not directory.is_dir():
            continue
        with os.scandir(directory) as it:
            for entry in list(it):
                if entry.is_file() and pattern.match(entry.name):
                    os.unlink(entry.path)
                    if directory == p.raw:
                        removed += 1
    return removed


# ------------------------------------------------------------------ сургалтын процесс
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_state(root: Path, state: dict) -> None:
    p = Paths(root)
    p.runs.mkdir(parents=True, exist_ok=True)
    tmp = p.state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False))
    tmp.replace(p.state_file)


def _log_tail(root: Path, max_bytes: int = 6000) -> str:
    path = Paths(root).log_file
    if not path.is_file():
        return ""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - max_bytes))
        data = f.read().decode("utf-8", errors="replace")
    return data.replace("\r", "\n")


_EPOCH_RE = re.compile(r"^\s*(\d+)/(\d+)\s", re.MULTILINE)


def _progress(tail: str, epochs: int) -> int | None:
    last = None
    for m in _EPOCH_RE.finditer(tail):
        if int(m.group(2)) == epochs:
            last = int(m.group(1))
    return last


def read_state(root: Path) -> dict:
    p = Paths(root)
    state: dict = {"state": "idle"}
    if p.state_file.is_file():
        try:
            state = json.loads(p.state_file.read_text())
        except (OSError, ValueError):
            state = {"state": "idle"}
    if state.get("state") == "running" and not _pid_alive(state.get("pid")):
        # train.py өөрөө "done/failed" гэж бичиж амжаагүй үед процесс үхсэн гэсэн үг
        state = {**state, "state": "failed", "finished_at": _now(), "message": "Сургалтын процесс гэнэт зогссон (логийг харна уу)"}
        _write_state(root, state)
    tail = _log_tail(root)
    out = {k: state.get(k) for k in ("state", "started_at", "finished_at", "epochs", "base", "imgsz", "message", "metrics", "model_file")}
    out["log_tail"] = "\n".join(tail.splitlines()[-25:])
    out["epoch"] = _progress(tail, int(state.get("epochs") or 0)) if state.get("state") == "running" else None
    return out


def _models_available(root: Path) -> dict[str, bool]:
    return {b: (Paths(root).models / f"base-{b}.pt").is_file() for b in BASE_WEIGHTS}


def start_training(root: Path, *, epochs: int, base: str, python: Path, script: Path, imgsz: int = 512) -> None:
    p = Paths(root)
    if not EPOCHS_RANGE[0] <= epochs <= EPOCHS_RANGE[1]:
        raise TrainingError(f"Epoch {EPOCHS_RANGE[0]}–{EPOCHS_RANGE[1]} хооронд байна")
    if imgsz not in IMGSZ_CHOICES:
        raise TrainingError("Нягтрал 512, 640, 960 эсвэл 1280 байна")
    if base not in BASE_WEIGHTS:
        raise TrainingError("Суурь моделийн хэмжээ буруу байна")
    if read_state(root)["state"] == "running":
        raise TrainingError("Сургалт аль хэдийн явагдаж байна")
    weights = p.models / f"base-{base}.pt"
    if not weights.is_file():
        raise TrainingError(f"Суурь жин олдсонгүй: training/models/{weights.name}")
    if not python.is_file() or not script.is_file():
        raise TrainingError("ai-service/.venv эсвэл training/train.py олдсонгүй")
    labeled = counts(root)["labeled_count"]
    if labeled < MIN_LABELED_TO_TRAIN:
        raise TrainingError(f"Сургахад дор хаяж {MIN_LABELED_TO_TRAIN} шошглосон зураг хэрэгтэй (одоо {labeled})")

    p.runs.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
    env.update({"YOLO_AUTOINSTALL": "False", "PYTHONUNBUFFERED": "1"})  # сургалт дундаа юм татаж суулгахгүй
    with open(p.log_file, "wb") as log:  # child процесс өөрийн fd-тэй тул энд хаахад болно
        proc = subprocess.Popen(
            [
                str(python),
                str(script),
                "--epochs",
                str(epochs),
                "--base",
                str(weights),
                "--imgsz",
                str(imgsz),
                "--batch",
                str(8 if imgsz <= 640 else 4),
            ],
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    _write_state(root, {"state": "running", "pid": proc.pid, "started_at": _now(), "epochs": epochs, "base": base, "imgsz": imgsz})


def stop_training(root: Path) -> bool:
    state = read_state(root)
    if state["state"] != "running":
        return False
    raw = json.loads(Paths(root).state_file.read_text())
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(raw["pid"]), signal.SIGTERM)
    _write_state(root, {**raw, "state": "stopped", "finished_at": _now(), "message": "Сургалтыг гараар зогсоолоо"})
    return True


def training_info(root: Path) -> dict:
    return {
        "models_available": _models_available(root),
        "min_labeled": MIN_LABELED_TO_TRAIN,
        "epochs_min": EPOCHS_RANGE[0],
        "epochs_max": EPOCHS_RANGE[1],
        "classes": [c for c in CLASSES if c not in HIDDEN_CLASSES],
    }


def python_and_script(root: Path) -> tuple[Path, Path]:
    return root.parent / "ai-service" / ".venv" / "bin" / "python", root / "train.py"
