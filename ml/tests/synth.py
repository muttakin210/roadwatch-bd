"""Synthetic tracks for rule unit tests (PLAN §7). No video, no GPU.

Scene: 1280x720 footbridge view looking along a divided road. Bangladesh drives on the left,
so the left carriageway (x 200-640) moves UP the image (away), the right one (640-1080) DOWN.
"""
from __future__ import annotations

import itertools

import numpy as np

from roadwatch.config import load_config
from roadwatch.road import RoadModel
from roadwatch.track import Track
from roadwatch.types import TYPICAL_LENGTH_M

W, H, FPS = 1280, 720, 15
LEFT_KERB, RIGHT_KERB, DIVIDER = 200, 1080, 640
LANES_UP = [300, 420, 540]      # left carriageway, moving up
LANES_DOWN = [740, 860, 980]    # right carriageway, moving down
SIZE = {"car": (40, 60), "bus": (70, 150), "motorcycle": (25, 40), "rickshaw": (35, 50),
        "person": (20, 40), "leguna": (45, 75), "cng_autorickshaw": (35, 50)}

_ids = itertools.count(1)
_rng = np.random.default_rng(0)


def cfg(**over):
    return load_config(overrides=over or None)


def road(divider: bool = True) -> RoadModel:
    return RoadModel.from_edges(W, H, [(LEFT_KERB, 0), (LEFT_KERB, H - 1)], [(RIGHT_KERB, 0), (RIGHT_KERB, H - 1)],
                                [(DIVIDER, 0), (DIVIDER, H - 1)] if divider else None)


def px_per_s(cls: str, mps: float) -> float:
    return mps / TYPICAL_LENGTH_M[cls] * max(SIZE[cls])


def track(cls: str, keyframes: list[tuple[float, float, float]], tid: int | None = None, noise: float = 0.7) -> Track:
    """keyframes: (t, x_center, y_bottom), linearly interpolated at FPS."""
    kf = np.array(keyframes, float)
    t = np.arange(kf[0, 0], kf[-1, 0] + 1e-9, 1 / FPS)
    x = np.interp(t, kf[:, 0], kf[:, 1]) + _rng.normal(0, noise, len(t))
    y = np.interp(t, kf[:, 0], kf[:, 2]) + _rng.normal(0, noise, len(t))
    w, h = SIZE[cls]
    boxes = np.stack([x - w / 2, y - h, x + w / 2, y], 1)
    return Track(tid or next(_ids), cls, t, boxes)


def drive(cls: str, x: float, t0: float, mps: float, up: bool, y_from=None, y_to=None, tid=None) -> Track:
    y_from = (H - 5 if up else 70) if y_from is None else y_from
    y_to = (70 if up else H - 5) if y_to is None else y_to
    dur = abs(y_to - y_from) / px_per_s(cls, mps)
    return track(cls, [(t0, x, y_from), (t0 + dur, x, y_to)], tid)


def background(duration: float, per_lane: int = 10, mps: float = 8.0, lanes_up=LANES_UP, lanes_down=LANES_DOWN):
    out = []
    span = max(duration - 8, 1)
    for li, x in enumerate(lanes_up):
        for k in range(per_lane):
            out.append(drive("car", x, (k + li / 3) * span / per_lane, mps, up=True))
    for li, x in enumerate(lanes_down):
        for k in range(per_lane):
            out.append(drive("car", x, (k + li / 3) * span / per_lane, mps, up=False))
    return out


def stop_and_go(cls: str, x: float, t0: float, y_stop: float, stop_s: float, mps: float = 6.0, up=True, tid=None):
    """Drive in, stop at y_stop for stop_s seconds, drive off."""
    v = px_per_s(cls, mps)
    y0, y1 = (H - 5, 70) if up else (70, H - 5)
    t_arr = t0 + abs(y_stop - y0) / v
    t_dep = t_arr + stop_s
    t_end = t_dep + abs(y1 - y_stop) / v
    return track(cls, [(t0, x, y0), (t_arr, x, y_stop), (t_dep, x, y_stop), (t_end, x, y1)], tid)


def prepare(tracks: list[Track], c) -> list[Track]:
    for t in tracks:
        t.compute_kinematics(c)
    return tracks
