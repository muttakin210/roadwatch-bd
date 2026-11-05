"""E2 — bus stopping mid-road (PLAN §6.3).

All must hold: class bus (optionally leguna subtype); stopped >= min_stop_s; kerb gap > ~0.5
bus-width; stopped by choice — judged by traffic AHEAD of the bus (moving or empty) and not
inside a signal queue. A jam BEHIND the bus does not cancel E2.
"""
from __future__ import annotations

import numpy as np

from ..road import RoadModel
from ..track import Track
from ..types import Event, rp
from .scene_state import SceneTimeline


def _frame(bus: Track, i: int, heading: float):
    """Box centre, unit heading, vehicle length/width in px (oriented by heading)."""
    w, h = bus.wh[i]
    u = np.array([np.cos(np.radians(heading)), np.sin(np.radians(heading))])
    length, width = (h, w) if abs(u[1]) >= abs(u[0]) else (w, h)
    return bus.centers[i], u, float(length), float(width)


def _region_members(tracks, bus, t_samples, heading, along_lo, along_hi, lateral, need_stopped):
    """Track ids found in a heading-aligned region around the bus at the sampled times."""
    hits: dict[int, int] = {}
    for tr in tracks:
        if tr.id == bus.id or tr.cls == "person":
            continue
        for ts in t_samples:
            j = np.where(np.abs(tr.t - ts) <= 0.5 / 1.0)[0]
            bi = np.where(np.abs(bus.t - ts) <= 0.5)[0]
            if len(j) == 0 or len(bi) == 0:
                continue
            j, bi = j[np.argmin(np.abs(tr.t[j] - ts))], bi[np.argmin(np.abs(bus.t[bi] - ts))]
            c, u, L, Wd = _frame(bus, bi, heading)
            d = tr.centers[j] - c
            a, lat = float(d @ u), float(abs(d[0] * u[1] - d[1] * u[0]))
            if along_lo * L <= a <= along_hi * L and lat <= lateral * Wd:
                if need_stopped is None or bool(tr.stopped[j]) == need_stopped:
                    hits[tr.id] = hits.get(tr.id, 0) + 1
    return hits


def detect_bus_stops(tracks: list[Track], road: RoadModel, scene: SceneTimeline, flow, hints, cfg) -> list[Event]:
    b = cfg.bus_stop
    classes = set(b.classes) | ({"leguna"} if b.leguna_subtype else set())
    events = []
    for bus in tracks:
        if bus.cls not in classes:
            continue
        for i0, i1 in bus.stopped_segments(b.min_stop_s):
            t0, t1 = float(bus.t[i0]), float(bus.t[i1])
            heading = bus.approach_heading(i0)
            heading_src = "track"
            if np.isnan(heading):
                cd = flow.expected_cell(flow.cell_of(*bus.gp[i0]))
                heading, heading_src = (cd.dir, "flow") if cd.trusted else (float("nan"), "none")
            mid = (i0 + i1) // 2

            # 3. in a running lane
            gap_px = road.kerb_gap_px(bus.boxes[mid], heading)
            bus_w = _frame(bus, mid, heading if not np.isnan(heading) else 90.0)[3]
            gap_bw = gap_px / max(bus_w, 1.0)
            if np.isnan(gap_bw) or gap_bw <= b.kerb_gap_bus_widths:
                continue

            # 4. stopped by choice: not in a signal queue, lane AHEAD moving or empty
            if scene.state_over(t0, t1) == "signal_queue":
                continue
            ts = np.linspace(t0 + 0.25 * (t1 - t0), t1 - 0.25 * (t1 - t0), 5)
            if not np.isnan(heading):
                ahead_stopped = _region_members(tracks, bus, ts, heading, 0.5, 0.5 + b.ahead_lengths,
                                                b.lateral_widths, need_stopped=True)
                if any(n >= len(ts) / 2 for n in ahead_stopped.values()):
                    continue  # stuck behind stopped traffic, not stopped by choice
                held = _region_members(tracks, bus, np.linspace(t0, t1, 8), heading,
                                       -(0.5 + b.behind_lengths), -0.5, b.lateral_widths, need_stopped=True)
            else:
                held = {}

            # extra evidence
            c = bus.centers[mid]; L = float(bus.wh[mid].max())
            people = 0
            for p in tracks:
                if p.cls != "person":
                    continue
                idx = p.index_range(t0, t1)
                if len(idx) and np.min(np.hypot(*(p.centers[idx] - c).T)) <= b.people_radius_lengths * L:
                    people += 1
            moved_off = i1 < len(bus) - 1 and bus.t[-1] - t1 >= 1.0 and not bus.stopped[-1]
            dur = t1 - t0
            raw = (0.35 + 0.25 * min(dur / 20, 1) + 0.15 * min(gap_bw / 1.5, 1) + 0.1 * (people > 0)
                   + 0.1 * min(len(held) / 5, 1) + 0.05 * moved_off - (0.15 if heading_src == "none" else 0))

            lane_w = gap_bw  # distances in bus-widths (≈ lane-widths) unless calibrated
            sev = "medium" if hints.near_bus_stop else ("high" if hints.near_bus_stop is False else "medium")
            reason = f"stopped {dur:.1f} s · ~{lane_w:.1f} bus-widths from the kerb · {len(held)} vehicles held up behind"
            parts = [rp("bus_main", s=f"{dur:.1f}", gap=f"{lane_w:.1f}", held=str(len(held)))]
            if people:
                reason += f" · {people} people near the bus"
                parts.append(rp("bus_people", n=str(people)))
            if hints.near_bus_stop:
                reason += " · at a stop, but blocking a lane"
                parts.append(rp("bus_at_stop"))
            events.append(Event(
                type="bus_midroad_stop", subtype="leguna" if bus.cls == "leguna" else None,
                vehicle_class=bus.cls, track=bus.id, start=t0, end=t1,
                raw_score=float(np.clip(raw, 0, 1)), severity=sev, reason=reason,
                details={"reason_parts": parts, "kerb_gap_bus_widths": round(gap_bw, 2), "vehicles_blocked": len(held),
                         "passengers_seen": people > 0, "moved_off": bool(moved_off),
                         "heading_source": heading_src, "scene_state": scene.state_over(t0, t1)},
            ))
    return events
