"""E3 — wrong-way driving, plus U-turn tag and one-way-road handling (PLAN §6.4)."""
from __future__ import annotations

import numpy as np

from ..road import RoadModel
from ..track import Track, angle_diff, circ_mean_deg, circ_median_deg
from ..types import Event, SLOW_CLASSES, note, rp


def _find_uturn(tr: Track, a: int, b: int, cfg) -> tuple[int, int] | None:
    """Window (i, j) inside [a, b] where heading turns smoothly by >= uturn_min_deg within uturn_max_s."""
    w = cfg.wrong_way
    h = tr.heading[a:b + 1]
    ok = ~np.isnan(h)
    if ok.sum() < 4:
        return None
    idx = np.arange(a, b + 1)[ok]
    un = np.degrees(np.unwrap(np.radians(h[ok])))
    t = tr.t[idx]
    for s in range(len(idx)):
        e = np.searchsorted(t, t[s] + w.uturn_max_s, side="right") - 1
        if e <= s:
            continue
        seg = un[s:e + 1]
        net = seg - seg[0]
        k = int(np.argmax(np.abs(net)))
        if abs(net[k]) >= w.uturn_min_deg:
            path = np.abs(np.diff(seg[:k + 1])).sum()
            if path <= 1.5 * abs(net[k]):  # smooth, one-directional turn
                return int(idx[s]), int(idx[s + k])
    return None


def _severity(tr: Track, road: RoadModel, a: int, b: int, cfg) -> tuple[str, str | None]:
    if tr.cls in SLOW_CLASSES:
        sev, sub = "medium", "slow_vehicle"
    else:
        sev, sub = "high", None
    gaps = []
    for i in range(a, b + 1, max(1, (b - a) // 10)):
        w = float(min(tr.wh[i]))
        g = road.kerb_gap_px(tr.boxes[i], float("nan"))
        if not np.isnan(g):
            gaps.append(g / max(w, 1))
    if gaps and np.median(gaps) < cfg.wrong_way.hug_kerb_widths:
        sev, sub = "low", "against_flow_at_kerb"
    return sev, sub


def _judge_segment(tr, a, b, flow, road, cfg, oneway_dir=None):
    w = cfg.wrong_way
    idx = np.arange(a, b + 1)
    idx = idx[~np.isnan(tr.heading[idx])]
    if len(idx) == 0:
        return None
    diffs, trusted, srcs, agrees = [], 0, {}, []
    for i in idx:
        if oneway_dir is not None:
            exp_dir, ok, src, ag = oneway_dir, True, "oneway", 1.0
        else:
            cd = flow.expected_cell(flow.cell_of(*tr.gp[i]), exclude=tr.id)
            exp_dir, ok, src, ag = cd.dir, cd.trusted, cd.source, cd.agreement
        if ok:
            trusted += 1
            diffs.append(float(angle_diff(tr.heading[i], exp_dir)))
            srcs[src] = srcs.get(src, 0) + 1
            agrees.append(ag)
    if trusted < w.min_trusted_frac * len(idx) or not diffs:
        return {"judged": False}
    med = float(np.median(diffs))
    if med <= w.angle_deg:
        return {"judged": True, "wrong": False}
    dur = float(tr.t[b] - tr.t[a])
    sev, sub = _severity(tr, road, a, b, cfg)
    src = max(srcs, key=srcs.get)
    raw = 0.4 + 0.3 * min((med - w.angle_deg) / 45, 1) + 0.15 * min(dur / 5, 1) + 0.15 * float(np.mean(agrees))
    reason = f"moved {dur:.1f} s opposite to traffic ({med:.0f}°)"
    parts = [rp("ww_main", s=f"{dur:.1f}", deg=f"{med:.0f}")]
    if sub == "against_flow_at_kerb":
        reason += " · along the kerb edge"
        parts.append(rp("ww_kerb"))
    return {"judged": True, "wrong": True, "event": Event(
        type="wrong_way", vehicle_class=tr.cls, subtype=sub, track=tr.id,
        start=float(tr.t[a]), end=float(tr.t[b]), raw_score=float(np.clip(raw, 0, 1)),
        severity=sev, reason=reason,
        details={"reason_parts": parts, "angle_diff_deg": round(med), "direction_source": src,
                 "trusted_frac": round(trusted / len(idx), 2)})}


def detect_wrong_way(tracks: list[Track], road: RoadModel, flow, hints, cfg):
    """Returns (events, road_level_notes)."""
    w = cfg.wrong_way
    events: list[Event] = []
    notes: list[dict[str, str]] = []
    segs = []
    for tr in tracks:
        if tr.cls == "person":
            continue
        for a, b in tr.moving_segments(cfg, w.min_s, w.min_len_vehicle_lengths):
            ut = _find_uturn(tr, a, b, cfg)
            if ut is not None:
                i, j = ut
                # Most U-turns are legal, and whether one is (a no-U-turn sign, a solid divider) can't be seen
                # by the model: keep it below the default show cut-off (0.6), so it's listed only among the
                # uncertain events until a reviewer confirms it.
                events.append(Event(type="u_turn", vehicle_class=tr.cls, track=tr.id,
                                    start=float(tr.t[i]), end=float(tr.t[j]), raw_score=0.45,
                                    severity="low", reason="turned ~180° (U-turn)",
                                    details={"reason_parts": [rp("uturn")]}))
                pieces = [(a, i - 1), (j + 1, b)]
            else:
                pieces = [(a, b)]
            for p, q in pieces:
                if q - p >= 2 and tr.t[q] - tr.t[p] >= w.min_s:
                    segs.append((tr, p, q))

    oneway_dir = None
    if hints.oneway:
        # On a one-way road any two-way flow is a violation; the minority direction is flagged,
        # unless the minority is large — then we can't tell who is breaking the rule.
        hs = np.array([circ_mean_deg(tr.heading[p:q + 1][~np.isnan(tr.heading[p:q + 1])])[0]
                       for tr, p, q in segs])
        if len(hs) >= cfg.flow.min_tracks:
            main = circ_median_deg(hs)
            minority = float(np.mean(angle_diff(hs, main) > 90))
            if minority > w.oneway_minority_max:
                notes.append(note("oneway_two_way", "two-way traffic on a one-way road"))
                return events, notes
            oneway_dir = main

    judged_any = False
    for tr, p, q in segs:
        r = _judge_segment(tr, p, q, flow, road, cfg, oneway_dir)
        if r and r.get("judged"):
            judged_any = True
        if r and r.get("wrong"):
            events.append(r["event"])
    if segs and not judged_any:
        notes.append(note("ww_cannot_judge", "not enough traffic to judge direction"))
    return events, notes
