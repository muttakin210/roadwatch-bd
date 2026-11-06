"""Privacy blur: faces + plates + safety net (PLAN §5.7). Everything shared is blurred.

- Faces: YuNet (OpenCV, permissive licence) if a model file is given.
- Plates: optional plate detector (callable frame -> boxes), trained on BD plate data.
- Safety net: for vehicles close to the camera, blur the plate band even if no plate was found;
  for large person boxes, blur the head region even if no face was found.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .types import Detection

log = logging.getLogger("roadwatch")


def _blur(frame: np.ndarray, x1, y1, x2, y2) -> None:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = int(max(0, x1)), int(max(0, y1)), int(min(w, x2)), int(min(h, y2))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = frame[y1:y2, x1:x2]
    k = max(3, (min(roi.shape[:2]) // 3) | 1)
    frame[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)
    # pixelate on top: Gaussian alone can leave large plates readable
    small = cv2.resize(frame[y1:y2, x1:x2], (max(1, (x2 - x1) // 8), max(1, (y2 - y1) // 8)))
    frame[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)


class Blurrer:
    def __init__(self, yunet_model: str | Path | None = None,
                 plate_detector: Callable[[np.ndarray], np.ndarray] | None = None,
                 near_frac: float = 0.08, person_frac: float = 0.05):
        self.person_frac = person_frac
        self.face = None
        if yunet_model and Path(yunet_model).exists():
            self.face = cv2.FaceDetectorYN.create(str(yunet_model), "", (320, 320), 0.6)
        else:
            # Never fail open quietly: say so, and fall back to blurring the head of EVERY person box.
            log.warning("face-detection model not found (%s): faces are only blurred via person boxes", yunet_model)
            self.person_frac = 0.0
        self.plate = plate_detector
        self.near_frac = near_frac

    @property
    def faces_enabled(self) -> bool:
        return self.face is not None

    def __call__(self, frame: np.ndarray, dets: list[Detection]) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]
        if self.face is not None:
            self.face.setInputSize((w, h))
            _, faces = self.face.detect(out)
            for f in faces if faces is not None else []:
                x, y, fw, fh = f[:4]
                _blur(out, x - 0.2 * fw, y - 0.2 * fh, x + 1.2 * fw, y + 1.2 * fh)
        if self.plate is not None:
            for x1, y1, x2, y2 in self.plate(frame):
                _blur(out, x1 - 4, y1 - 4, x2 + 4, y2 + 4)
        for d in dets:  # safety net
            x1, y1, x2, y2 = d.box
            bh, bw = y2 - y1, x2 - x1
            if d.cls == "person":
                # head = top ~22% of the box; at >=5% of frame height a face can be recognisable
                if bh > self.person_frac * h:
                    _blur(out, x1, y1, x2, y1 + 0.22 * bh)
            elif bh > self.near_frac * h:
                # plates sit low on the front/back; blur a central lower band
                _blur(out, x1 + 0.15 * bw, y1 + 0.62 * bh, x2 - 0.15 * bw, y1 + 0.95 * bh)
        return out
