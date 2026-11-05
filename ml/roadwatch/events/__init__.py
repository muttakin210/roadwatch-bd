"""Event engine — pass 2 of the pipeline (PLAN §6.8). Pure Python/NumPy, no GPU needed."""
from __future__ import annotations

from ..flow import FlowField
from ..road import RoadModel
from ..track import Track
from ..types import Hints
from .bus_stop import detect_bus_stops
from .calibrate import calibrate, load_calibrators
from .congestion import congestion
from .merge import merge, summarise
from .scene_state import scene_state
from .wrong_way import detect_wrong_way


def analyse(tracks: list[Track], road: RoadModel, duration: float, hints: Hints, cfg,
            calibrators: dict | None = None, camera_motion: str = "static") -> dict:
    """Judge every (stitched, kinematics-computed) track against the whole-clip picture."""
    scene = scene_state(tracks, duration, (road.width, road.height), cfg)
    flow = FlowField(tracks, road, hints, cfg)

    e1, cong = congestion(tracks, road, scene, duration, cfg)
    e2 = detect_bus_stops(tracks, road, scene, flow, hints, cfg)
    e3, notes = detect_wrong_way(tracks, road, flow, hints, cfg)

    events = merge(e1 + e2 + e3, cfg.merge.gap_s)
    if camera_motion == "moving":
        # Only congestion is fully supported from a moving platform (PLAN §5.2).
        for e in events:
            if e.type != "congestion_jam":
                e.raw_score *= 0.5
                e.details["limited"] = "moving camera"
    events = calibrate(events, calibrators or {}, cfg)

    return {
        "rules_version": cfg.version,
        "camera_motion": camera_motion,
        "congestion": cong,
        "scene": {"window_s": scene.window_s, "states": scene.states},
        "events": [e.to_dict() for e in events],
        "summary": summarise(events),
        "notes": [n["en"] for n in notes + flow.warnings],
        "note_parts": notes + flow.warnings,
        "_events": events,  # objects, for rendering; dropped before writing JSON
    }
