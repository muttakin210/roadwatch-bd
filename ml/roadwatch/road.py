"""Road understanding: drivable mask, kerb lines, divider (PLAN §5.4).

MVP assumption: the camera looks roughly *along* the road, so kerbs are left/right per image row.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .track import Track


def _interp_polyline(pts: list[tuple[float, float]], h: int) -> np.ndarray:
    """x per row from a polyline of (x, y) points; NaN outside its y-range."""
    p = np.asarray(sorted(pts, key=lambda q: q[1]), float)
    rows = np.arange(h, dtype=float)
    x = np.interp(rows, p[:, 1], p[:, 0])
    x[(rows < p[0, 1]) | (rows > p[-1, 1])] = np.nan
    return x


def _smooth_nan(x: np.ndarray, k: int) -> np.ndarray:
    out = x.copy()
    for i in range(len(x)):
        w = x[max(0, i - k): i + k + 1]
        w = w[~np.isnan(w)]
        if len(w) and not np.isnan(x[i]):
            out[i] = np.median(w)
    return out


@dataclass
class RoadModel:
    width: int
    height: int
    left_kerb: np.ndarray            # (H,) x of the left road edge per row; NaN where no road
    right_kerb: np.ndarray           # (H,)
    divider: np.ndarray | None = None
    mask: np.ndarray | None = None   # (H, W) bool
    source: str = "unknown"

    def __post_init__(self):
        if self.mask is None:
            cols = np.arange(self.width)[None, :]
            l, r = self.left_kerb[:, None], self.right_kerb[:, None]
            self.mask = (cols >= l) & (cols <= r)  # NaN compares False

    # ---- constructors ---------------------------------------------------
    @classmethod
    def from_edges(cls, w: int, h: int, left: list, right: list, divider: list | None = None,
                   source: str = "user_taps") -> "RoadModel":
        return cls(w, h, _interp_polyline(left, h), _interp_polyline(right, h),
                   _interp_polyline(divider, h) if divider else None, source=source)

    @classmethod
    def from_heatmap(cls, tracks: list[Track], w: int, h: int, seg_mask: np.ndarray | None = None,
                     cell: int = 4, step: int = 3) -> "RoadModel":
        """Where vehicles actually drove: accumulate box bottom edges; outer edge per row = kerb."""
        gh, gw = h // cell + 1, w // cell + 1
        heat = np.zeros((gh, gw), np.int32)
        for tr in tracks:
            if tr.cls == "person":
                continue
            seen = np.zeros_like(heat, bool)
            for b in tr.boxes[::step]:
                y = int(np.clip(b[3], 0, h - 1)) // cell
                x1, x2 = int(np.clip(b[0], 0, w - 1)) // cell, int(np.clip(b[2], 0, w - 1)) // cell
                seen[y, x1:x2 + 1] = True
            heat += seen  # count tracks, not frames, per cell
        n_veh = sum(1 for t in tracks if t.cls != "person")
        occ = heat >= max(2, int(0.02 * n_veh))
        # close small holes vertically (rows with no traffic between busy rows)
        try:
            import cv2
            occ = cv2.morphologyEx(occ.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 5), np.uint8)).astype(bool)
        except ImportError:
            pass
        full = np.repeat(np.repeat(occ, cell, 0), cell, 1)[:h, :w]
        if seg_mask is not None:
            full &= seg_mask.astype(bool)
        left = np.full(h, np.nan); right = np.full(h, np.nan)
        for y in range(h):
            xs = np.where(full[y])[0]
            if len(xs) > 3:
                left[y], right[y] = xs[0], xs[-1]
        left, right = _smooth_nan(left, 15), _smooth_nan(right, 15)
        return cls(w, h, left, right, None, mask=full, source="heatmap" + ("+seg" if seg_mask is not None else ""))

    # ---- queries ---------------------------------------------------------
    def _row(self, y: float) -> int:
        return int(np.clip(round(y), 0, self.height - 1))

    def road_width(self, y: float) -> float:
        r = self._row(y)
        return float(self.right_kerb[r] - self.left_kerb[r])

    def on_road(self, x: float, y: float) -> bool:
        return bool(self.mask[self._row(y), int(np.clip(x, 0, self.width - 1))])

    def side_of_divider(self, x: float, y: float) -> int | None:
        """-1 left of divider, +1 right, None if no divider at that row."""
        if self.divider is None:
            return None
        d = self.divider[self._row(y)]
        return None if np.isnan(d) else (-1 if x < d else 1)

    def kerb_gap_px(self, box: np.ndarray, heading_deg: float) -> float:
        """Gap between the vehicle's kerb-side edge and the kerb.

        Bangladesh drives on the left, so the kerb side is the vehicle's left.
        In image coordinates (y down) the left normal of heading d=(dx,dy) is (dy, -dx).
        """
        r = self._row(box[3])
        lk, rk = self.left_kerb[r], self.right_kerb[r]
        if np.isnan(lk) or np.isnan(rk):
            return float("nan")
        gap_l = max(0.0, box[0] - lk)
        gap_r = max(0.0, rk - box[2])
        if np.isnan(heading_deg):
            return float(min(gap_l, gap_r))
        dx, dy = np.cos(np.radians(heading_deg)), np.sin(np.radians(heading_deg))
        left_normal_x = dy
        if abs(left_normal_x) < 0.3:  # vehicle moving across the image: kerb side unclear
            return float(min(gap_l, gap_r))
        return float(gap_l if left_normal_x < 0 else gap_r)
