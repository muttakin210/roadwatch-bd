"""Scene state per time window: flowing / signal_queue / jam / unknown (PLAN §6.1). Runs first."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..track import Track, angle_diff, circ_median_deg, runs


@dataclass
class SceneTimeline:
    window_s: float
    states: list[str]                       # one per window
    stopped_ratio: list[float]
    episodes: list[dict] = field(default_factory=list)

    def window_index(self, t: float) -> int:
        return int(np.clip(t // self.window_s, 0, max(len(self.states) - 1, 0)))

    def state_over(self, t0: float, t1: float) -> str:
        """Majority state over [t0, t1]."""
        if not self.states:
            return "unknown"
        i0, i1 = self.window_index(t0), self.window_index(t1)
        sub = self.states[i0:i1 + 1]
        return max(set(sub), key=sub.count)

    def intervals(self, state: str) -> list[list[float]]:
        m = np.array([s == state for s in self.states])
        return [[a * self.window_s, (b + 1) * self.window_s] for a, b in runs(m)]


def _window_stats(tracks: list[Track], n_win: int, w: float) -> tuple[np.ndarray, np.ndarray]:
    stopped = np.zeros(n_win); total = np.zeros(n_win); nveh = np.zeros(n_win)
    for tr in tracks:
        if tr.cls == "person":
            continue
        wi = np.clip((tr.t // w).astype(int), 0, n_win - 1)
        np.add.at(stopped, wi, tr.stopped.astype(float))
        np.add.at(total, wi, 1.0)
        for i in np.unique(wi):
            nveh[i] += 1
    ratio = np.divide(stopped, total, out=np.zeros(n_win), where=total > 0)
    return ratio, nveh


def _queue_front(tracks: list[Track], t0: float, t1: float, main_dir: float) -> float | None:
    """Most-downstream stopped ground point along the main approach direction (px)."""
    if np.isnan(main_dir):
        return None
    u = np.array([np.cos(np.radians(main_dir)), np.sin(np.radians(main_dir))])
    best = None
    for tr in tracks:
        if tr.cls == "person":
            continue
        idx = np.where((tr.t >= t0) & (tr.t <= t1) & tr.stopped)[0]
        if len(idx) == 0:
            continue
        h = tr.approach_heading(int(idx[0]))
        if np.isnan(h) or angle_diff(h, main_dir) > 60:
            continue
        proj = float(np.median(tr.gp[idx] @ u))
        best = proj if best is None else max(best, proj)
    return best


def scene_state(tracks: list[Track], duration: float, frame_wh: tuple[int, int], cfg) -> SceneTimeline:
    s, w = cfg.scene, cfg.window_s
    n_win = max(1, int(np.ceil(duration / w)))
    ratio, nveh = _window_stats(tracks, n_win, w)
    is_stopped = (ratio >= s.stopped_ratio) & (nveh >= s.min_vehicles)
    states = ["flowing"] * n_win
    episodes = []

    # main approach direction = circular median of moving headings
    hs = np.concatenate([tr.heading[~np.isnan(tr.heading)] for tr in tracks if tr.cls != "person"] or [np.array([])])
    main_dir = circ_median_deg(hs[:: max(1, len(hs) // 2000)]) if len(hs) else float("nan")
    diag = float(np.hypot(*frame_wh))

    for a, b in runs(is_stopped):
        t0, t1 = a * w, min((b + 1) * w, duration)
        episodes.append({"w0": a, "w1": b, "t0": t0, "t1": t1, "dur": t1 - t0,
                         "front": _queue_front(tracks, t0, t1, main_dir), "state": None})

    # signal queue: >=2 episodes with a consistent queue front and regular stop-go cycles
    for i, ep in enumerate(episodes):
        for j in (i - 1, i + 1):
            if not (0 <= j < len(episodes)):
                continue
            other = episodes[j]
            period = abs(other["t0"] - ep["t0"])
            same_line = (ep["front"] is not None and other["front"] is not None
                         and abs(ep["front"] - other["front"]) <= s.stop_line_tol * diag)
            if same_line and s.cycle_min_s <= period <= s.cycle_max_s and ep["dur"] <= s.cycle_max_s:
                ep["state"] = "signal_queue"

    for ep in episodes:
        if ep["state"] is None:
            if duration < s.min_clip_for_state_s:
                ep["state"] = "unknown"
            elif ep["dur"] >= s.jam_min_episode_s:
                ep["state"] = "jam"
            else:
                ep["state"] = "unknown"
        for k in range(ep["w0"], ep["w1"] + 1):
            states[k] = ep["state"]
    return SceneTimeline(w, states, ratio.round(3).tolist(), episodes)
