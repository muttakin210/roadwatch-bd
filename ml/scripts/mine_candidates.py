"""Candidate mining (PLAN §4.3): run the pipeline with LOOSE thresholds and write a review sheet.

Don't watch 60 h of video: a person confirms/rejects each candidate in the CSV (verdict column:
1 = correct, 0 = wrong). Fully watch a random 10% of footage to measure what candidates miss.

    python scripts/mine_candidates.py ../data/raw_videos --out ../data/events/candidates.csv --detector hf
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadwatch.config import LOOSE_OVERRIDES, load_config  # noqa: E402
from roadwatch.pipeline import run_video  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
FIELDS = ["clip", "type", "subtype", "vehicle_class", "track", "start_s", "end_s", "raw_score", "reason",
          "verdict", "corrected_type", "notes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--detector", default="hf")
    ap.add_argument("--weights")
    ap.add_argument("--hints-dir", type=Path, help="optional <clip>.json hints next to each clip")
    ap.add_argument("--render", action="store_true", help="also write annotated videos for review")
    ap.add_argument("--allow-no-ffmpeg", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config(overrides=LOOSE_OVERRIDES)
    vids = [p for p in sorted(a.src.rglob("*")) if p.suffix.lower() in VIDEO_EXT] if a.src.is_dir() else [a.src]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    kw = ({"model_id": a.weights} if a.detector == "hf" else {"weights": a.weights}) if a.weights else {}
    detector = None
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        for v in vids:
            hints = None
            if a.hints_dir and (a.hints_dir / f"{v.stem}.json").exists():
                hints = json.loads((a.hints_dir / f"{v.stem}.json").read_text(encoding="utf-8"))
            if detector is None:
                from roadwatch.detect import make_detector
                detector = make_detector(a.detector, **kw)
            res = run_video(v, a.out.parent / "mined" / v.stem, hints, detector=detector, cfg=cfg,
                            calibration=None, render=a.render, allow_no_ffmpeg=a.allow_no_ffmpeg)
            for e in res["events"]:
                w.writerow({"clip": v.name, "type": e["type"], "subtype": e.get("subtype", ""),
                            "vehicle_class": e.get("vehicle_class", ""), "track": e.get("track", ""),
                            "start_s": e["start"], "end_s": e["end"], "raw_score": e["raw_score"],
                            "reason": e["reason"], "verdict": "", "corrected_type": "", "notes": ""})
            f.flush()
            print(f"{v.name}: {len(res['events'])} candidates")


if __name__ == "__main__":
    main()
