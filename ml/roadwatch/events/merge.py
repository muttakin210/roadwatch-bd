"""Event merging and distinct-vehicle summaries (PLAN §6.0)."""
from __future__ import annotations

from collections import Counter

from ..types import Event


def merge(events: list[Event], gap_s: float) -> list[Event]:
    """Same type on the same (stitched) track with a gap < gap_s become one event."""
    out: list[Event] = []
    keyed = sorted(events, key=lambda e: (e.type, e.track if e.track is not None else -1, e.start))
    for e in keyed:
        last = out[-1] if out else None
        if (last is not None and e.track is not None and last.type == e.type and last.track == e.track
                and e.start - last.end < gap_s):
            dur_l, dur_e = last.duration, e.duration
            last.end = max(last.end, e.end)
            last.raw_score = max(last.raw_score, e.raw_score)
            if dur_e > dur_l:
                last.reason, last.details = e.reason, e.details
            last.details = {**last.details, "merged": last.details.get("merged", 1) + 1}
        else:
            out.append(e)
    return sorted(out, key=lambda e: e.start)


def summarise(events: list[Event], shown_only: bool = True) -> dict:
    """Counts of distinct vehicles per event type (not raw events)."""
    out: dict = {}
    for typ in sorted({e.type for e in events}):
        evs = [e for e in events if e.type == typ and (not shown_only or e.details.get("shown", True))]
        if not evs:
            continue
        tracks = {e.track for e in evs if e.track is not None}
        out[typ] = {
            "events": len(evs),
            "distinct_vehicles": len(tracks) if tracks else None,
            "by_class": dict(Counter(e.vehicle_class for e in evs if e.vehicle_class)),
            "total_s": round(sum(e.duration for e in evs), 1),
        }
    return out
