"""Tracks: kinematics (Kalman RTS smoothing), stopped state, stitching, trackers (PLAN §5.5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from .types import Detection, TYPICAL_LENGTH_M


def angle_diff(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray | float:
    """Absolute smallest difference between two angles in degrees (0..180)."""
    d = (np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0
    return np.abs(d)


def circ_mean_deg(angles: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float]:
    """Circular mean (deg) and resultant length R (0..1)."""
    a = np.radians(np.asarray(angles, float))
    w = np.ones_like(a) if weights is None else np.asarray(weights, float)
    if a.size == 0 or w.sum() == 0:
        return float("nan"), 0.0
    c, s = (w * np.cos(a)).sum() / w.sum(), (w * np.sin(a)).sum() / w.sum()
    return float(np.degrees(np.arctan2(s, c))), float(np.hypot(c, s))


def circ_median_deg(angles: np.ndarray) -> float:
    """Circular median: the sample minimising the sum of angular distances."""
    a = np.asarray(angles, float)
    if a.size == 0:
        return float("nan")
    cost = angle_diff(a[:, None], a[None, :]).sum(axis=1)
    return float(a[int(np.argmin(cost))])


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (start, end) index pairs of True runs."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.diff(m.astype(int))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0] - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _rts_cv(t: np.ndarray, z: np.ndarray, q: float, r: float) -> tuple[np.ndarray, np.ndarray]:
    """Constant-velocity Kalman filter + RTS smoother on one axis (irregular dt). Returns pos, vel."""
    # Scalar 2x2 algebra: much faster than tiny numpy matrices in a Python loop.
    n = len(t)
    t = [float(v) for v in t]; z = [float(v) for v in z]
    R, q2 = r * r, q * q
    fx = [0.0] * n; fv = [0.0] * n                        # filtered state
    fa = [0.0] * n; fb = [0.0] * n; fd = [0.0] * n         # filtered cov [[a,b],[b,d]]
    px = [0.0] * n; pv = [0.0] * n
    pa = [0.0] * n; pb = [0.0] * n; pd = [0.0] * n         # predicted
    dts = [0.0] * n
    for k in range(n):
        if k == 0:
            x_, v_, a_, b_, d_ = z[0], 0.0, R, 0.0, 1e4
        else:
            dt = max(t[k] - t[k - 1], 1e-3); dts[k] = dt
            x_ = fx[k - 1] + dt * fv[k - 1]; v_ = fv[k - 1]
            A, B, D = fa[k - 1], fb[k - 1], fd[k - 1]
            a_ = A + 2 * dt * B + dt * dt * D + q2 * dt ** 4 / 4
            b_ = B + dt * D + q2 * dt ** 3 / 2
            d_ = D + q2 * dt * dt
        px[k], pv[k], pa[k], pb[k], pd[k] = x_, v_, a_, b_, d_
        S = a_ + R
        k0, k1 = a_ / S, b_ / S
        inn = z[k] - x_
        fx[k], fv[k] = x_ + k0 * inn, v_ + k1 * inn
        fa[k], fb[k], fd[k] = a_ - k0 * a_, b_ - k0 * b_, d_ - k1 * b_
    sx, sv = fx[:], fv[:]
    sa, sb, sd = fa[:], fb[:], fd[:]
    for k in range(n - 2, -1, -1):
        dt = dts[k + 1]
        A, B, D = fa[k], fb[k], fd[k]
        # P F^T
        m00, m01 = A + dt * B, B
        m10, m11 = B + dt * D, D
        a_, b_, d_ = pa[k + 1], pb[k + 1], pd[k + 1]
        det = a_ * d_ - b_ * b_
        i00, i01, i11 = d_ / det, -b_ / det, a_ / det
        c00 = m00 * i00 + m01 * i01; c01 = m00 * i01 + m01 * i11
        c10 = m10 * i00 + m11 * i01; c11 = m10 * i01 + m11 * i11
        ex, ev = sx[k + 1] - px[k + 1], sv[k + 1] - pv[k + 1]
        sx[k] = fx[k] + c00 * ex + c01 * ev
        sv[k] = fv[k] + c10 * ex + c11 * ev
        ea, eb, ed = sa[k + 1] - a_, sb[k + 1] - b_, sd[k + 1] - d_
        sa[k] = A + c00 * (c00 * ea + c01 * eb) + c01 * (c00 * eb + c01 * ed)
        sb[k] = B + c00 * (c10 * ea + c11 * eb) + c01 * (c10 * eb + c11 * ed)
        sd[k] = D + c10 * (c10 * ea + c11 * eb) + c11 * (c10 * eb + c11 * ed)
    return np.array(sx), np.array(sv)


@dataclass
class Track:
    id: int
    cls: str
    t: np.ndarray        # (N,) seconds
    boxes: np.ndarray    # (N, 4) x1,y1,x2,y2
    conf: np.ndarray | None = None
    source_ids: list[int] = field(default_factory=list)
    # derived by compute_kinematics()
    gp: np.ndarray | None = None          # smoothed ground point (bottom-middle), (N, 2)
    vel: np.ndarray | None = None         # px/s, (N, 2)
    scale_px: np.ndarray | None = None    # vehicle length in px (rolling max of box long side)
    speed_mps: np.ndarray | None = None
    heading: np.ndarray | None = None     # degrees, atan2(vy, vx) in image coords; NaN when ~still
    stopped: np.ndarray | None = None

    def __post_init__(self):
        self.t = np.asarray(self.t, float)
        self.boxes = np.asarray(self.boxes, float).reshape(-1, 4)
        if not self.source_ids:
            self.source_ids = [self.id]

    # ---- basic geometry -------------------------------------------------
    def __len__(self) -> int:
        return len(self.t)

    @property
    def start(self) -> float:
        return float(self.t[0])

    @property
    def end(self) -> float:
        return float(self.t[-1])

    @property
    def raw_gp(self) -> np.ndarray:
        b = self.boxes
        return np.stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]], axis=1)

    @property
    def centers(self) -> np.ndarray:
        b = self.boxes
        return np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2], axis=1)

    @property
    def wh(self) -> np.ndarray:
        b = self.boxes
        return np.stack([b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]], axis=1)

    def index_range(self, t0: float, t1: float) -> np.ndarray:
        return np.where((self.t >= t0) & (self.t <= t1))[0]

    # ---- kinematics -----------------------------------------------------
    def compute_kinematics(self, cfg) -> "Track":
        k = cfg.kinematics
        g = self.raw_gp
        if len(self) >= 3:
            x, vx = _rts_cv(self.t, g[:, 0], k.kalman_accel_px_s2, k.kalman_meas_px)
            y, vy = _rts_cv(self.t, g[:, 1], k.kalman_accel_px_s2, k.kalman_meas_px)
        else:
            x, y = g[:, 0], g[:, 1]
            vx = vy = np.zeros(len(self))
        self.gp = np.stack([x, y], 1)
        self.vel = np.stack([vx, vy], 1)

        long_side = self.wh.max(axis=1)
        half = max(1, int(round(k.scale_window_s * cfg.analysis_fps / 2)))
        self.scale_px = np.array([long_side[max(0, i - half): i + half + 1].max() for i in range(len(self))])
        self.scale_px = np.maximum(self.scale_px, 1.0)

        px_speed = np.hypot(vx, vy)
        self.speed_mps = px_speed / self.scale_px * TYPICAL_LENGTH_M.get(self.cls, 4.0)
        self.heading = np.where(self.speed_mps > 0.3, np.degrees(np.arctan2(vy, vx)), np.nan)
        self.stopped = self._stopped_state(cfg)
        return self

    def _stopped_state(self, cfg) -> np.ndarray:
        k = cfg.kinematics
        s = self.speed_mps
        st = np.zeros(len(s), bool)
        cur = False
        for i, v in enumerate(s):
            cur = (v < k.stop_exit_mps) if cur else (v < k.stop_enter_mps)
            st[i] = cur
        for a, b in runs(st):  # drop stops shorter than stop_min_s
            if self.t[b] - self.t[a] < k.stop_min_s:
                st[a:b + 1] = False
        return st

    def stopped_segments(self, min_s: float) -> list[tuple[int, int]]:
        return [(a, b) for a, b in runs(self.stopped) if self.t[b] - self.t[a] >= min_s]

    def moving_segments(self, cfg, min_s: float, min_lengths: float) -> list[tuple[int, int]]:
        mov = (~self.stopped) & (self.speed_mps >= cfg.kinematics.move_min_mps)
        out = []
        for a, b in runs(mov):
            if self.t[b] - self.t[a] < min_s:
                continue
            path = np.hypot(*np.diff(self.gp[a:b + 1], axis=0).T).sum()
            if path >= min_lengths * float(np.median(self.scale_px[a:b + 1])):
                out.append((a, b))
        return out

    def approach_heading(self, i: int, look_s: float = 3.0) -> float:
        """Heading just before index i (e.g. before a stop); NaN if never moving."""
        idx = np.where((self.t >= self.t[i] - look_s) & (self.t <= self.t[i]) & ~np.isnan(self.heading))[0]
        if len(idx) == 0:
            idx = np.where(~np.isnan(self.heading))[0]
            if len(idx) == 0:
                return float("nan")
            # nearest moving samples to i
            idx = idx[np.argsort(np.abs(idx - i))[:15]]
        return circ_mean_deg(self.heading[idx], self.speed_mps[idx])[0]


# ---------------------------------------------------------------------------
# Stitching
# ---------------------------------------------------------------------------
def _end_velocity(tr: Track, from_end: bool, look_s: float = 1.0) -> np.ndarray:
    g = tr.raw_gp
    if from_end:
        idx = np.where(tr.t >= tr.end - look_s)[0]
    else:
        idx = np.where(tr.t <= tr.start + look_s)[0]
    if len(idx) < 2:
        return np.zeros(2)
    dt = tr.t[idx[-1]] - tr.t[idx[0]]
    return (g[idx[-1]] - g[idx[0]]) / max(dt, 1e-3)


def stitch_tracks(tracks: list[Track], cfg) -> list[Track]:
    """Join a track that ends to one that starts (same class, short gap, near predicted position)."""
    s = cfg.stitching
    by_start = sorted(tracks, key=lambda t: t.start)
    cands = []
    for a in tracks:
        va = _end_velocity(a, True)
        la = float(a.wh[-5:].max()) if len(a) else 1.0
        for b in by_start:
            if b is a or b.cls != a.cls:
                continue
            gap = b.start - a.end
            if gap <= 0 or gap > s.max_gap_s:
                continue
            pred = a.raw_gp[-1] + va * gap
            dist = float(np.hypot(*(b.raw_gp[0] - pred)))
            thr = max(s.max_dist_lengths * la, s.min_dist_px)
            if dist <= thr:
                cands.append((dist / thr + gap / s.max_gap_s, a.id, b.id))
    cands.sort()
    nxt: dict[int, int] = {}
    has_prev: set[int] = set()
    for _, ai, bi in cands:
        if ai in nxt or bi in has_prev:
            continue
        nxt[ai] = bi
        has_prev.add(bi)
    byid = {t.id: t for t in tracks}
    out = []
    for t in tracks:
        if t.id in has_prev:
            continue
        chain = [t]
        while chain[-1].id in nxt:
            chain.append(byid[nxt[chain[-1].id]])
        if len(chain) == 1:
            out.append(t)
            continue
        out.append(Track(
            id=chain[0].id, cls=chain[0].cls,
            t=np.concatenate([c.t for c in chain]),
            boxes=np.concatenate([c.boxes for c in chain]),
            conf=None if any(c.conf is None for c in chain) else np.concatenate([c.conf for c in chain]),
            source_ids=[i for c in chain for i in c.source_ids],
        ))
    return out


# ---------------------------------------------------------------------------
# Trackers
# ---------------------------------------------------------------------------
def _iou(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    x1 = np.maximum(a[:, None, 0], b[None, :, 0]); y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2]); y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area = lambda z: (z[:, 2] - z[:, 0]) * (z[:, 3] - z[:, 1])
    return inter / (area(a)[:, None] + area(b)[None, :] - inter + 1e-9)


class SimpleIoUTracker:
    """Dependency-free greedy IoU tracker. Development fallback only; use ByteTrack for real runs."""

    def __init__(self, iou_thr: float = 0.3, max_age: int = 15):
        self.iou_thr, self.max_age = iou_thr, max_age
        self.active: list[dict] = []
        self.next_id = 1

    def update(self, dets: list[Detection]) -> list[tuple[int, Detection]]:
        out = []
        boxes = np.array([d.box for d in dets]).reshape(-1, 4)
        used_det = set()
        if self.active and len(dets):
            ious = _iou(np.array([a["box"] for a in self.active]), boxes)
            for ai, di in sorted(np.ndindex(ious.shape), key=lambda p: -ious[p]):
                if ious[ai, di] < self.iou_thr:
                    break
                a = self.active[ai]
                if a.get("_used") or di in used_det or a["cls"] != dets[di].cls:
                    continue
                a["_used"] = True; used_det.add(di)
                a["box"], a["age"] = dets[di].box, 0
                out.append((a["id"], dets[di]))
        for a in self.active:
            if not a.pop("_used", False):
                a["age"] += 1
        self.active = [a for a in self.active if a["age"] <= self.max_age]
        for di, d in enumerate(dets):
            if di not in used_det:
                self.active.append({"id": self.next_id, "box": d.box, "cls": d.cls, "age": 0})
                out.append((self.next_id, d))
                self.next_id += 1
        return out


class ByteTrackAdapter:
    """ByteTrack (Apache-2.0 `trackers` package; older `supervision` versions shipped it as sv.ByteTrack)."""

    def __init__(self, fps: int = 15):
        import supervision as sv  # lazy
        self.sv = sv
        try:
            from trackers import ByteTrackTracker  # supervision >= 0.27 moved ByteTrack here
            # lost_track_buffer is counted in 30-fps frames: 60 = ~2 s
            self.bt = ByteTrackTracker(lost_track_buffer=60, frame_rate=fps, minimum_consecutive_frames=1)
            self._update = self.bt.update
        except ImportError:
            if not hasattr(sv, "ByteTrack"):
                raise ImportError("ByteTrack not found: pip install trackers") from None
            self.bt = sv.ByteTrack(frame_rate=fps, lost_track_buffer=int(fps * 2))
            self._update = self.bt.update_with_detections

    def update(self, dets: list[Detection]) -> list[tuple[int, Detection]]:
        if not dets:
            self._update(self.sv.Detections.empty())
            return []
        from .types import CLASS_ID, CLASSES
        sd = self.sv.Detections(
            xyxy=np.array([d.box for d in dets], float),
            confidence=np.array([d.conf for d in dets], float),
            class_id=np.array([CLASS_ID[d.cls] for d in dets], int),
        )
        tr = self._update(sd)
        f, t = dets[0].frame, dets[0].t
        return [(int(tid), Detection(f, t, box, CLASSES[int(c)], float(cf)))
                for box, c, cf, tid in zip(tr.xyxy, tr.class_id, tr.confidence, tr.tracker_id)
                if tid is not None and int(tid) >= 0]


def make_tracker(name: str = "auto", fps: int = 15):
    if name in ("auto", "bytetrack"):
        try:
            return ByteTrackAdapter(fps)
        except ImportError:
            if name == "bytetrack":
                raise
            import logging
            logging.getLogger("roadwatch").warning("ByteTrack unavailable (pip install trackers); using IoU tracker")
    return SimpleIoUTracker()


def build_tracks(assoc: Iterable[tuple[int, Detection]], min_len: int = 3) -> list[Track]:
    """Group (track_id, detection) pairs into Track objects. Class = majority vote."""
    groups: dict[int, list[Detection]] = {}
    for tid, d in assoc:
        groups.setdefault(tid, []).append(d)
    out = []
    for tid, ds in groups.items():
        if len(ds) < min_len:
            continue
        ds.sort(key=lambda d: d.t)
        clss = [d.cls for d in ds]
        cls = max(set(clss), key=clss.count)
        out.append(Track(tid, cls, [d.t for d in ds], [d.box for d in ds], np.array([d.conf for d in ds])))
    return out
