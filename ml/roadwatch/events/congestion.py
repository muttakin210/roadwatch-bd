"""E1 — congestion level per window, jam intervals (PLAN §6.2)."""
from __future__ import annotations

import numpy as np

from ..road import RoadModel
from ..track import Track, runs
from ..types import Event, rp
from .scene_state import SceneTimeline


def occupancy(boxes: np.ndarray, road: RoadModel, footprint_frac: float) -> float:
    """Union of ground footprints, row by row, each row divided by the road width at that row."""
    if len(boxes) == 0:
        return 0.0
    cover = np.zeros_like(road.mask)
    H, W = road.height, road.width
    for x1, y1, x2, y2 in boxes:
        fy1 = int(np.clip(y2 - footprint_frac * (y2 - y1), 0, H - 1))
        fy2 = int(np.clip(y2, 0, H - 1))
        cover[fy1:fy2 + 1, int(np.clip(x1, 0, W - 1)):int(np.clip(x2, 0, W - 1)) + 1] = True
    cover &= road.mask
    road_px = road.mask.sum(axis=1)
    rows = np.where((road_px > 0) & cover.any(axis=1))[0]
    all_rows = np.where(road_px > 0)[0]
    if len(all_rows) == 0:
        return 0.0
    # rows the road spans in the region where vehicles appear at all (avoid empty sky/far rows)
    per_row = cover[all_rows].sum(axis=1) / road_px[all_rows]
    lo, hi = (rows.min(), rows.max()) if len(rows) else (all_rows.min(), all_rows.max())
    sel = (all_rows >= lo) & (all_rows <= hi)
    return float(per_row[sel].mean()) if sel.any() else 0.0


def level(occ: float, speed: float, cfg) -> str:
    c = cfg.congestion
    if occ < c.free_occ or speed >= c.speed_high_mps:
        return "free"
    if occ < c.heavy_occ or speed > c.speed_low_mps:
        return "moderate"
    return "heavy"  # "jam" is set later, only for intervals that pass the jam rule


def congestion(tracks: list[Track], road: RoadModel, scene: SceneTimeline, duration: float, cfg):
    c, w = cfg.congestion, cfg.window_s
    n = len(scene.states)
    occ = np.zeros(n); spd = np.full(n, np.nan); stopped = np.zeros(n)
    veh = [t for t in tracks if t.cls != "person"]
    for k in range(n):
        t0, t1 = k * w, (k + 1) * w
        tm = (t0 + t1) / 2
        boxes, speeds, st = [], [], []
        for tr in veh:
            idx = tr.index_range(t0, t1)
            if len(idx) == 0:
                continue
            j = idx[np.argmin(np.abs(tr.t[idx] - tm))]
            boxes.append(tr.boxes[j])
            speeds.append(float(np.median(tr.speed_mps[idx])))
            st.append(float(tr.stopped[idx].mean()) >= 0.5)
        occ[k] = occupancy(np.array(boxes).reshape(-1, 4), road, c.footprint_frac)
        if speeds:
            spd[k] = float(np.median(speeds))
            stopped[k] = float(np.mean(st))

    levels, score = [], []
    for k in range(n):
        sp = 0.0 if np.isnan(spd[k]) else spd[k]
        lv = level(occ[k], sp if not np.isnan(spd[k]) else 99.0, cfg)
        levels.append(lv)
        score.append(int(round(100 * np.clip(0.6 * min(occ[k] / 0.5, 1) + 0.4 * stopped[k], 0, 1))))

    jam_like = (occ >= c.jam_occ) & (stopped >= c.jam_stopped_ratio) & \
               np.array([s in ("jam", "unknown") for s in scene.states])
    events = []
    for a, b in runs(jam_like):
        t0, t1 = a * w, min((b + 1) * w, duration)
        if t1 - t0 < c.jam_min_s:
            continue
        states = scene.states[a:b + 1]
        unknown = states.count("unknown") > len(states) / 2
        raw = 0.5 + 0.3 * min(float(occ[a:b + 1].mean()) / 0.7, 1) + 0.2 * float(stopped[a:b + 1].mean())
        if unknown:
            raw -= c.unknown_state_penalty
        for k in range(a, b + 1):
            levels[k] = "jam"
        occ_pct, stop_pct = f"{occ[a:b + 1].mean() * 100:.0f}", f"{stopped[a:b + 1].mean() * 100:.0f}"
        parts = [rp("jam_main", s=f"{t1 - t0:.0f}", occ=occ_pct, stopped=stop_pct)]
        if unknown:
            parts.append(rp("jam_signal"))
        events.append(Event(
            type="congestion_jam", start=t0, end=t1, raw_score=float(np.clip(raw, 0, 1)),
            severity="medium",
            reason=(f"{t1 - t0:.0f} s with ~{occ_pct}% of the road covered and {stop_pct}% of vehicles stopped"
                    + (" · clip too short to rule out a signal" if unknown else "")),
            details={"reason_parts": parts, "occupancy": round(float(occ[a:b + 1].mean()), 3),
                     "stopped_ratio": round(float(stopped[a:b + 1].mean()), 3),
                     "scene_state": "unknown" if unknown else "jam"},
        ))
    timeline = [[round(k * w, 1), score[k]] for k in range(n)]
    summary = {
        "timeline": timeline, "levels": levels,
        "jams": [[e.start, e.end] for e in events],
        "signal_queues": scene.intervals("signal_queue"),
        "avg": int(round(float(np.mean(score)))) if score else 0,
        "occupancy": occ.round(3).tolist(),
    }
    return events, summary
