"""Flow field: expected direction of traffic per road cell (PLAN §5.6, §6.4).

Priority for the expected direction: user arrow > OSM one-way (handled in wrong_way) > learned
flow (leave-one-out) > left-hand-traffic rule.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .road import RoadModel
from .track import Track, angle_diff, circ_mean_deg, circ_median_deg
from .types import Hints, note


@dataclass
class CellDir:
    dir: float          # degrees, image coords
    trusted: bool
    source: str         # arrow | flow | lht | none
    agreement: float = 0.0
    n: int = 0


class FlowField:
    def __init__(self, tracks: list[Track], road: RoadModel, hints: Hints, cfg):
        self.cfg = cfg.flow
        self.road, self.hints = road, hints
        self.gx, self.gy = self.cfg.grid
        self.W, self.H = road.width, road.height
        # per cell: {track_id: mean heading of that track in that cell}
        self.cells: dict[tuple[int, int], dict[int, float]] = {}
        for tr in tracks:
            if tr.cls == "person":
                continue
            mov = (~tr.stopped) & ~np.isnan(tr.heading)
            if not mov.any():
                continue
            per: dict[tuple[int, int], list[int]] = {}
            for i in np.where(mov)[0]:
                per.setdefault(self.cell_of(*tr.gp[i]), []).append(i)
            for c, idx in per.items():
                if not self.road.on_road(*self.cell_center(c)) and not any(self.road.on_road(*tr.gp[i]) for i in idx):
                    continue
                self.cells.setdefault(c, {})[tr.id] = circ_mean_deg(tr.heading[idx], tr.speed_mps[idx])[0]
        self.warnings: list[dict[str, str]] = []  # note() dicts
        self._centre_ok = self._centre_line_usable(tracks)
        self._check_arrows()

    # ---- left-hand-traffic sides -----------------------------------------
    def _centre_side(self, x: float, y: float) -> int | None:
        """-1/+1 = left/right of the road's centre line (midway between the kerbs) at that row."""
        r = self.road._row(y)
        lk, rk = self.road.left_kerb[r], self.road.right_kerb[r]
        if np.isnan(lk) or np.isnan(rk) or rk - lk < 1:
            return None
        return -1 if x < (lk + rk) / 2 else 1

    def _centre_line_usable(self, tracks: list[Track]) -> bool:
        """Without a divider (the web app never sends one), the centre line stands in for it, but only when
        the clip itself shows two-way, left-hand traffic: the left half moving away and the right half coming
        towards the camera. A one-way road, or a camera facing the other way, never qualifies."""
        if not self.hints.camera_along_road or self.road.divider is not None or self.road.source == "full_frame":
            return False
        sides: dict[int, list[float]] = {-1: [], 1: []}
        for tr in tracks:
            if tr.cls == "person" or tr.heading is None:
                continue
            ok = ~np.isnan(tr.heading)
            if ok.sum() < 3:
                continue
            gx, gy = np.median(tr.gp[ok], axis=0)
            s = self._centre_side(gx, gy)
            if s is not None:
                sides[s].append(circ_mean_deg(tr.heading[ok], tr.speed_mps[ok])[0])
        if min(len(sides[-1]), len(sides[1])) < 3:
            return False
        left, right = circ_median_deg(np.array(sides[-1])), circ_median_deg(np.array(sides[1]))
        return bool(angle_diff(left, -90.0) <= 60 and angle_diff(right, 90.0) <= 60)

    def _lht_side(self, x: float, y: float) -> int | None:
        side = self.road.side_of_divider(x, y)
        if side is None and self._centre_ok:
            side = self._centre_side(x, y)
        return side

    # ---- geometry --------------------------------------------------------
    def cell_of(self, x: float, y: float) -> tuple[int, int]:
        return (int(np.clip(x / self.W * self.gx, 0, self.gx - 1)),
                int(np.clip(y / self.H * self.gy, 0, self.gy - 1)))

    def cell_center(self, c: tuple[int, int]) -> tuple[float, float]:
        return ((c[0] + 0.5) * self.W / self.gx, (c[1] + 0.5) * self.H / self.gy)

    # ---- sources ---------------------------------------------------------
    def learned(self, c: tuple[int, int], exclude: int | None = None) -> CellDir:
        hs = [h for tid, h in self.cells.get(c, {}).items() if tid != exclude]
        if not hs:
            return CellDir(float("nan"), False, "flow", 0.0, 0)
        d = circ_median_deg(np.array(hs))
        agree = float(np.mean(angle_diff(np.array(hs), d) <= self.cfg.agree_deg))
        trusted = len(hs) >= self.cfg.min_tracks and agree >= self.cfg.min_agreement
        return CellDir(d, trusted, "flow", agree, len(hs))

    def arrow(self, c: tuple[int, int]) -> CellDir | None:
        if not self.hints.arrows:
            return None
        cx, cy = self.cell_center(c)
        side = self.road.side_of_divider(cx, cy)
        best, best_d = None, np.inf
        for x1, y1, x2, y2 in self.hints.arrows:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if side is not None:
                aside = self.road.side_of_divider(mx, my)
                if aside is not None and aside != side:
                    continue
            p, a, b = np.array([cx, cy]), np.array([x1, y1]), np.array([x2, y2])
            ab = b - a
            u = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
            d = np.hypot(*(p - (a + u * ab)))
            if d < best_d:
                best, best_d = (x1, y1, x2, y2), d
        if best is None:
            return None
        if self.road.divider is None and best_d > self.cfg.arrow_radius_frac * self.W:
            return None
        x1, y1, x2, y2 = best
        return CellDir(float(np.degrees(np.arctan2(y2 - y1, x2 - x1))), True, "arrow", 1.0, 0)

    def lht(self, c: tuple[int, int]) -> CellDir | None:
        """Left-hand traffic: with the camera facing along the road and a visible divider,
        the left side of the image moves away (up), the right side comes towards (down)."""
        if not self.hints.camera_along_road:
            return None
        side = self._lht_side(*self.cell_center(c))
        if side is None:
            return None
        return CellDir(-90.0 if side < 0 else 90.0, True, "lht", 1.0, 0)

    def expected_cell(self, c: tuple[int, int], exclude: int | None = None) -> CellDir:
        a = self.arrow(c)
        if a is not None:
            return a
        f = self.learned(c, exclude)
        if f.trusted:
            l = self.lht(c)
            if l is not None and angle_diff(f.dir, l.dir) > 90:
                # learned flow and the LHT rule disagree: don't judge here
                return CellDir(f.dir, False, "conflict", f.agreement, f.n)
            return f
        if f.n >= 2 and f.agreement < self.cfg.min_agreement:
            return CellDir(f.dir, False, "ambiguous", f.agreement, f.n)  # junction / U-turn zone
        l = self.lht(c)
        return l if l is not None else CellDir(float("nan"), False, "none", f.agreement, f.n)

    def _check_arrows(self) -> None:
        if not self.hints.arrows:
            return
        bad = 0
        for c in self.cells:
            a, f = self.arrow(c), self.learned(c)
            if a is not None and f.trusted and angle_diff(a.dir, f.dir) > 135:
                bad += 1
        if bad:
            self.warnings.append(note("arrow_disagrees", f"user arrow disagrees with observed traffic in {bad} road cells",
                                      n=str(bad)))

    def dominant_direction(self) -> float:
        hs = [h for d in self.cells.values() for h in d.values()]
        return circ_median_deg(np.array(hs)) if hs else float("nan")
