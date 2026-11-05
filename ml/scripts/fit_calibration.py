"""Fit per-type confidence calibration from reviewed candidates (PLAN §6.0).

Input: candidates.csv with a filled `verdict` column (1/0) and a `location` column (or a
--locations CSV mapping clip -> location). Uses location-wise cross-validation to report an honest
ECE, then fits on all rows and writes models/calibration.json. Never include test-set clips.

    python scripts/fit_calibration.py ../data/events/candidates_reviewed.csv --locations ../data/clips_index.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadwatch.events.calibrate import (expected_calibration_error, fit_isotonic, fit_platt,  # noqa: E402
                                        save_calibrators)

ISOTONIC_MIN = 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", type=Path)
    ap.add_argument("--locations", type=Path, help="CSV with columns clip,place")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "models" / "calibration.json")
    a = ap.parse_args()
    loc = {}
    if a.locations:
        with open(a.locations, encoding="utf-8") as f:
            loc = {r["clip"]: r["place"] for r in csv.DictReader(f)}
    rows = defaultdict(list)
    with open(a.candidates, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("verdict", "").strip() in ("0", "1"):
                place = r.get("location") or loc.get(r["clip"]) or r["clip"]
                rows[r["type"]].append((float(r["raw_score"]), int(r["verdict"]), place))
    cals = {}
    for typ, data in rows.items():
        s = np.array([d[0] for d in data]); y = np.array([d[1] for d in data]); g = np.array([d[2] for d in data])
        fit = fit_isotonic if len(s) >= ISOTONIC_MIN else fit_platt
        places = sorted(set(g))
        if len(places) >= 2:
            p_cv = np.zeros(len(s))
            for pl in places:  # leave-one-location-out
                tr, te = g != pl, g == pl
                if len(set(y[tr])) < 2:
                    p_cv[te] = y[tr].mean()
                    continue
                p_cv[te] = fit(s[tr], y[tr])(s[te])
            print(f"{typ}: n={len(s)} precision={y.mean():.2f} raw ECE={expected_calibration_error(s, y):.3f} "
                  f"CV ECE ({fit.__name__})={expected_calibration_error(p_cv, y):.3f}  (target <= 0.10)")
        else:
            print(f"{typ}: n={len(s)} - only one location, no honest CV estimate")
        if len(set(y)) == 2:
            cals[typ] = fit(s, y)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    save_calibrators(cals, a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
