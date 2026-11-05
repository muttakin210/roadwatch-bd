"""Camera-motion check and stabilisation (PLAN §5.2).

Background points (ORB) outside vehicle boxes → frame-to-frame homography (RANSAC) →
static / shaky / moving. Shaky clips are warped to a reference frame.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MotionResult:
    cls: str                       # static | shaky | moving
    median_px: float               # median background motion per analysed frame
    steady_px: float               # magnitude of the mean (drift) component
    transforms: list[np.ndarray]   # per frame: 3x3 homography to the reference (first) frame
    reliable: bool = True          # False when too few background features were matched


def _bg_mask(shape, boxes: np.ndarray | None) -> np.ndarray:
    m = np.full(shape[:2], 255, np.uint8)
    if boxes is not None:
        for x1, y1, x2, y2 in boxes:
            px, py = 8 + 0.1 * (x2 - x1), 8 + 0.1 * (y2 - y1)  # pad: box edges move with the vehicle
            m[max(int(y1 - py), 0):max(int(y2 + py), 0), max(int(x1 - px), 0):max(int(x2 + px), 0)] = 0
    return m


class MotionEstimator:
    def __init__(self, n_features: int = 1500):
        self.orb = cv2.ORB_create(n_features)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.prev = None
        self.H_cum = np.eye(3)
        self.transforms: list[np.ndarray] = []
        self.shifts: list[np.ndarray] = []
        self.n_frames = 0
        self.frame_wh: tuple[int, int] | None = None

    def update(self, frame: np.ndarray, boxes: np.ndarray | None = None) -> np.ndarray:
        """Returns the homography mapping this frame onto the reference frame."""
        self.n_frames += 1
        self.frame_wh = (frame.shape[1], frame.shape[0])
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, _bg_mask(gray.shape, boxes))
        if self.prev is not None and des is not None and self.prev[1] is not None:
            pkp, pdes = self.prev
            matches = self.bf.match(des, pdes)
            if len(matches) >= 20:
                src = np.float32([kp[m.queryIdx].pt for m in matches])
                dst = np.float32([pkp[m.trainIdx].pt for m in matches])
                H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
                if H is not None and inl is not None and inl.sum() >= 15:
                    self.H_cum = self.H_cum @ H
                    # motion = mean displacement of a point grid under H (not raw match noise)
                    h, w = gray.shape
                    g = np.float32([[x, y] for x in (0.2 * w, 0.5 * w, 0.8 * w) for y in (0.2 * h, 0.5 * h, 0.8 * h)])
                    gw = cv2.perspectiveTransform(g.reshape(-1, 1, 2), H).reshape(-1, 2)
                    self.shifts.append((gw - g).mean(axis=0))
        self.prev = (kp, des)
        self.transforms.append(self.H_cum.copy())
        return self.H_cum

    def state(self) -> dict:
        """Raw measurements (picklable), so classification can be redone from a cache."""
        return {"shifts": self.shifts, "transforms": self.transforms, "n_frames": self.n_frames,
                "frame_wh": self.frame_wh}

    @classmethod
    def from_state(cls, st: dict) -> "MotionEstimator":
        m = cls.__new__(cls)
        m.shifts, m.transforms, m.n_frames, m.frame_wh = st["shifts"], st["transforms"], st["n_frames"], st["frame_wh"]
        return m

    def result(self, static_px: float = 1.0, moving_px: float = 4.0, drift_frac: float = 0.05) -> MotionResult:
        """static: barely moves · shaky: jitters around one view (can be warped back to it) ·
        moving: pans/tilts/travels away from the first view (can't be stabilised to one reference)."""
        if len(self.shifts) < 0.3 * max(self.n_frames - 1, 1):
            # not enough background texture to tell; analyse as static but say so
            return MotionResult("static", 0.0, 0.0, [np.eye(3)] * len(self.transforms), reliable=False)
        s = np.array(self.shifts)
        med = float(np.median(np.hypot(s[:, 0], s[:, 1])))
        steady = float(np.hypot(*s.mean(axis=0)))
        # how far the view wanders from the first frame: jitter stays near 0, a pan/tilt keeps growing
        max_drift = float(np.hypot(*np.cumsum(s, axis=0).T).max())
        diag = float(np.hypot(*self.frame_wh)) if self.frame_wh else 1.0
        if med < static_px and max_drift < drift_frac * diag:
            cls = "static"
        elif steady > moving_px or med > 3 * moving_px or max_drift > drift_frac * diag:
            cls = "moving"
        else:
            cls = "shaky"
        transforms = self.transforms if cls == "shaky" else [np.eye(3)] * len(self.transforms)
        return MotionResult(cls, med, steady, transforms)


def stabilise(frame: np.ndarray, H_to_ref: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    return cv2.warpPerspective(frame, H_to_ref, (w, h), borderMode=cv2.BORDER_REPLICATE)


def warp_boxes(boxes: np.ndarray, H: np.ndarray) -> np.ndarray:
    """Map boxes into the reference frame (axis-aligned bound of the warped corners)."""
    if len(boxes) == 0:
        return boxes
    pts = np.stack([boxes[:, [0, 1]], boxes[:, [2, 1]], boxes[:, [0, 3]], boxes[:, [2, 3]]], 1).reshape(-1, 1, 2)
    w = cv2.perspectiveTransform(pts.astype(np.float32), H).reshape(-1, 4, 2)
    return np.concatenate([w.min(1), w.max(1)], 1)
