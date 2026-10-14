"""Our 5 classes. Order = YOLO class id. MUST match backend training_service.CLASSES."""

from __future__ import annotations

CLASSES = ("person", "helmet", "no_helmet", "work_uniform", "no_work_uniform")


def parse_mapping(text: str) -> dict[str, str]:
    """'hardhat:helmet, no-hardhat:no_helmet' -> {'hardhat': 'helmet', 'no-hardhat': 'no_helmet'} (names lowercased)."""
    mapping = {}
    for pair in text.split(","):
        if not pair.strip():
            continue
        src, sep, dst = pair.rpartition(":")
        src, dst = src.strip().lower(), dst.strip()
        if not sep or not src or dst not in CLASSES:
            raise ValueError(f"Bad CLASS_MAPPING entry: '{pair.strip()}' (target must be one of {', '.join(CLASSES)})")
        mapping[src] = dst
    return mapping


def resolve_names(model_names: dict[int, str], mapping: dict[str, str]) -> dict[int, str]:
    """Model class id -> our class name. Classes we don't use are left out (ignored)."""
    out = {}
    for idx, name in model_names.items():
        key = str(name).lower()
        target = mapping.get(key) if mapping else (key if key in CLASSES else None)
        if target:
            out[int(idx)] = target
    return out
