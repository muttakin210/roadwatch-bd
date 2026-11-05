"""Confidence calibration: raw rule score -> probability of being correct (PLAN §6.0).

Platt scaling first (2 parameters, safe with little data); isotonic regression once there are
~500+ labelled candidates per type. Fit on location-wise cross-validated candidates, never on test.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..types import Event


@dataclass
class Calibrator:
    method: str = "none"          # none | platt | isotonic
    a: float = 1.0                # platt: p = 1 / (1 + exp(-(a*s + b)))
    b: float = 0.0
    xs: list[float] = field(default_factory=list)  # isotonic knots
    ys: list[float] = field(default_factory=list)
    n: int = 0

    def __call__(self, s: np.ndarray | float) -> np.ndarray | float:
        s = np.asarray(s, float)
        if self.method == "platt":
            return 1.0 / (1.0 + np.exp(-(self.a * s + self.b)))
        if self.method == "isotonic":
            return np.interp(s, self.xs, self.ys)
        return s

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def fit_platt(scores, labels, iters: int = 100) -> Calibrator:
    """Newton's method on logistic loss, with Platt's label smoothing."""
    s = np.asarray(scores, float); y = np.asarray(labels, float)
    n_pos, n_neg = y.sum(), len(y) - y.sum()
    t = np.where(y > 0, (n_pos + 1) / (n_pos + 2), 1 / (n_neg + 2))
    a, b = 1.0, 0.0
    X = np.stack([s, np.ones_like(s)], 1)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ [a, b])))
        g = X.T @ (p - t)
        Hm = X.T @ (X * (p * (1 - p))[:, None]) + 1e-6 * np.eye(2)
        step = np.linalg.solve(Hm, g)
        a, b = a - step[0], b - step[1]
        if np.abs(step).max() < 1e-8:
            break
    return Calibrator("platt", float(a), float(b), n=len(s))


def fit_isotonic(scores, labels) -> Calibrator:
    """Pool-adjacent-violators, increasing."""
    o = np.argsort(scores)
    s = np.asarray(scores, float)[o]; y = np.asarray(labels, float)[o]
    blocks = [[y[i], 1.0, s[i], s[i]] for i in range(len(s))]  # mean, weight, lo, hi
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0]:
            m1, w1, lo, _ = blocks[i]; m2, w2, _, hi = blocks[i + 1]
            blocks[i] = [(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, lo, hi]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    xs, ys = [], []
    for m, _, lo, hi in blocks:
        xs += [lo, hi]; ys += [m, m]
    return Calibrator("isotonic", xs=[float(v) for v in xs], ys=[float(v) for v in ys], n=len(s))


def expected_calibration_error(probs, labels, bins: int = 10) -> float:
    p = np.asarray(probs, float); y = np.asarray(labels, float)
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) | (hi == 1))
        if m.any():
            ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(ece)


def load_calibrators(path: str | Path | None) -> dict[str, Calibrator]:
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: Calibrator(**v) for k, v in json.load(f).items()}


def save_calibrators(cals: dict[str, Calibrator], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: c.to_dict() for k, c in cals.items()}, f, indent=2)


def calibrate(events: list[Event], cals: dict[str, Calibrator], cfg) -> list[Event]:
    c = cfg.calibration
    for e in events:
        cal = cals.get(e.type)
        e.calibrated = cal is not None and cal.method != "none"
        e.confidence = float(cal(e.raw_score)) if e.calibrated else float(e.raw_score)
        cut = c.per_type_cutoff.get(e.type, c.show_min_confidence) if c.per_type_cutoff else c.show_min_confidence
        e.details["shown"] = bool(e.confidence >= cut)
    return events
