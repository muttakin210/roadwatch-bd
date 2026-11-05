"""Annotated output video: boxes, track trails, event highlights, congestion bar (PLAN §8.1)."""
from __future__ import annotations

import cv2
import numpy as np

from .track import Track
from .types import CLASSES, Event

EVENT_COLOURS = {"bus_midroad_stop": (0, 140, 255), "wrong_way": (0, 0, 255),
                 "congestion_jam": (0, 200, 255), "u_turn": (255, 200, 0)}
EVENT_LABEL = {"bus_midroad_stop": "possible mid-road bus stop", "wrong_way": "possible wrong-way",
               "congestion_jam": "possible jam", "u_turn": "U-turn"}


def _colour(cls: str) -> tuple[int, int, int]:
    i = CLASSES.index(cls) if cls in CLASSES else 14
    rng = np.random.default_rng(i * 7 + 3)
    return tuple(int(v) for v in rng.integers(80, 255, 3))


class Renderer:
    def __init__(self, path: str, fps: int, size: tuple[int, int], tracks: list[Track],
                 events: list[Event], congestion_timeline: list, window_s: float):
        self.vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        self.tracks = tracks
        self.events = [e for e in events if e.details.get("shown", True)]
        self.ev_by_track: dict[int, list[Event]] = {}
        for e in self.events:
            if e.track is not None:
                self.ev_by_track.setdefault(e.track, []).append(e)
        self.cong = [s for _, s in congestion_timeline]
        self.window_s = window_s

    def write(self, frame: np.ndarray, t: float) -> None:
        img = frame
        for tr in self.tracks:
            if not (tr.start <= t <= tr.end):
                continue
            i = int(np.searchsorted(tr.t, t))
            i = min(i, len(tr) - 1)
            if abs(tr.t[i] - t) > 0.2:
                continue
            x1, y1, x2, y2 = tr.boxes[i].astype(int)
            col = _colour(tr.cls)
            active = [e for e in self.ev_by_track.get(tr.id, []) if e.start <= t <= e.end]
            if active:
                col = EVENT_COLOURS.get(active[0].type, (0, 0, 255))
            cv2.rectangle(img, (x1, y1), (x2, y2), col, 3 if active else 1)
            j0 = max(0, i - 30)
            pts = tr.gp[j0:i + 1].astype(np.int32) if tr.gp is not None else tr.raw_gp[j0:i + 1].astype(np.int32)
            if len(pts) > 1:
                cv2.polylines(img, [pts], False, col, 2)
            label = f"{tr.cls} #{tr.id}"
            if active:
                label = f"{EVENT_LABEL.get(active[0].type, active[0].type)} ({active[0].confidence:.2f})"
            cv2.putText(img, label, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
        # congestion bar + scene-level events
        h, w = img.shape[:2]
        k = min(int(t // self.window_s), len(self.cong) - 1) if self.cong else -1
        if k >= 0:
            s = self.cong[k]
            cv2.rectangle(img, (10, h - 24), (10 + int(2 * s), h - 10), (0, int(255 - 2.5 * s), int(2.5 * s)), -1)
            cv2.putText(img, f"congestion {s}", (220, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        for e in self.events:
            if e.track is None and e.start <= t <= e.end:
                cv2.putText(img, EVENT_LABEL.get(e.type, e.type), (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            EVENT_COLOURS.get(e.type, (0, 0, 255)), 2)
        cv2.putText(img, "AI-detected, may be wrong", (w - 250, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (220, 220, 220), 1)
        self.vw.write(img)

    def close(self) -> None:
        self.vw.release()
