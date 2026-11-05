"""Shared data types and the unified class list (PLAN §4.4)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

CLASSES = [
    "person",            # 0
    "bicycle",           # 1
    "rickshaw",          # 2
    "rickshaw_van",      # 3
    "motorcycle",        # 4
    "easybike",          # 5
    "cng_autorickshaw",  # 6
    "leguna",            # 7  (leguna / human hauler)
    "car",               # 8
    "microbus",          # 9  (microbus / SUV / jeep)
    "bus",               # 10 (city, minibus, double-decker)
    "truck",             # 11
    "pickup",            # 12 (pickup / covered van)
    "ambulance",         # 13 (ambulance / emergency)
    "other",             # 14
]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}
VEHICLES = set(CLASSES) - {"person"}

# Typical vehicle length in metres, used for the "approx. m/s" speed (PLAN §5.5).
TYPICAL_LENGTH_M = {
    "person": 0.5, "bicycle": 1.8, "rickshaw": 2.5, "rickshaw_van": 2.8,
    "motorcycle": 2.0, "easybike": 2.8, "cng_autorickshaw": 2.7, "leguna": 3.8,
    "car": 4.5, "microbus": 4.8, "bus": 11.0, "truck": 9.0, "pickup": 5.0,
    "ambulance": 5.5, "other": 4.0,
}

# Slow / non-motorised classes: wrong-way is very common, reported separately (PLAN §6.4).
SLOW_CLASSES = {"bicycle", "rickshaw", "rickshaw_van", "easybike"}


@dataclass
class Detection:
    frame: int
    t: float
    box: np.ndarray  # x1, y1, x2, y2 (pixels)
    cls: str
    conf: float


@dataclass
class Hints:
    """User-supplied hints (PLAN §8.1 upload page, §8.3 road_hints)."""
    arrows: list[tuple[float, float, float, float]] = field(default_factory=list)  # x1,y1 -> x2,y2
    road_edges: dict[str, list[tuple[float, float]]] | None = None  # {"left": [...], "right": [...], "divider": [...]}
    camera_along_road: bool | None = None   # needed for the left-hand-traffic rule
    oneway: bool | None = None              # OSM oneway=yes (Phase 2) or user-supplied
    near_bus_stop: bool | None = None       # OSM highway=bus_stop within radius (severity)
    camera_type: str = "footbridge"

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Hints":
        d = dict(d or {})
        h = cls()
        for k, v in d.items():
            if hasattr(h, k):
                setattr(h, k, v)
        h.arrows = [tuple(a) for a in (h.arrows or [])]
        return h


def rp(key: str, **args: str) -> dict[str, str]:
    """One translatable piece of an event's reason, e.g. rp("ww_main", s="3.2", deg="160").
    Stored in details["reason_parts"]; the web app renders them in the user's language and
    falls back to the English `reason` string when they are missing."""
    return {"k": key, **{k: str(v) for k, v in args.items()}}


def note(key: str, en: str, **args: str) -> dict[str, str]:
    """A road-level note (not tied to one vehicle): translatable key + args, plus the English text
    used by the CLI, the JSON `notes` list and as the web app's fallback."""
    return {"k": key, "en": en, **{k: str(v) for k, v in args.items()}}


@dataclass
class Event:
    type: str
    start: float
    end: float
    raw_score: float
    reason: str
    track: int | None = None
    vehicle_class: str | None = None
    subtype: str | None = None
    severity: str = "medium"
    confidence: float | None = None
    calibrated: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"] = round(self.start, 2)
        d["end"] = round(self.end, 2)
        d["raw_score"] = round(self.raw_score, 3)
        if self.confidence is not None:
            d["confidence"] = round(self.confidence, 3)
        return {k: v for k, v in d.items() if v is not None}
