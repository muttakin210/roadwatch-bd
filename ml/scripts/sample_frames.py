"""Sample frames for box annotation every N seconds, skipping near-duplicates (PLAN §4.3).

    python scripts/sample_frames.py ../data/raw_videos --out ../data/annotations/frames --every 1.5

Prefer *varied* frames over many frames from one spot: --max-per-clip caps each clip.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--every", type=float, default=1.5, help="seconds between samples")
    ap.add_argument("--max-per-clip", type=int, default=60)
    ap.add_argument("--min-diff", type=float, default=6.0, help="mean abs pixel diff to count as new")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    vids = [p for p in sorted(a.src.rglob("*")) if p.suffix.lower() in VIDEO_EXT] if a.src.is_dir() else [a.src]
    total = 0
    for v in vids:
        cap = cv2.VideoCapture(str(v))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, int(round(a.every * fps)))
        i, kept, last = 0, 0, None
        while kept < a.max_per_clip:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, f = cap.read()
            if not ok:
                break
            small = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)
            if last is None or np.abs(small - last).mean() >= a.min_diff:
                cv2.imwrite(str(a.out / f"{v.stem}_{i:06d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 92])
                kept += 1
                last = small
            i += step
        cap.release()
        total += kept
        print(f"{v.name}: {kept} frames")
    print("total", total)


if __name__ == "__main__":
    main()
