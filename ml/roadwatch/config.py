"""Load events.yaml into an attribute-accessible config, with optional overrides."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "configs" / "events.yaml"


class Cfg(dict):
    """dict with attribute access; nested dicts become Cfg too."""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Cfg(v) if isinstance(v, dict) and not isinstance(v, Cfg) else v


def _deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> Cfg:
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if overrides:
        data = _deep_update(copy.deepcopy(data), overrides)
    return _wrap(data)


def _wrap(d: Any) -> Any:
    if isinstance(d, dict):
        return Cfg({k: _wrap(v) for k, v in d.items()})
    return d


# Loose thresholds for candidate mining (PLAN §4.3): high recall, people confirm/reject.
LOOSE_OVERRIDES = {
    "bus_stop": {"min_stop_s": 4.0, "kerb_gap_bus_widths": 0.25},
    "wrong_way": {"angle_deg": 110, "min_s": 1.0, "min_trusted_frac": 0.4},
    "flow": {"min_tracks": 5, "min_agreement": 0.6},
    "congestion": {"jam_min_s": 15},
    "calibration": {"show_min_confidence": 0.0},
}
