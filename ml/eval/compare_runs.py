"""Paired comparison of two detector runs on the same test images (benchmark paper: the leakage effect).

    cd ml
    python eval/compare_runs.py --split ../data/processed/badodd_paired/clean/test \\
        --a eval/kaggle/bench/results/bd_rtdetr_r18_leaky_on_paired \\
        --b eval/kaggle/bench/results/bd_rtdetr_r18_clean_on_paired --out eval/results/leak_rtdetr_r18

`--a` / `--b` are eval_detector.py output prefixes; their cached detections (.detections.pkl) are rescored
with the *same* bootstrap draws (whole videos by default), so the interval is for the difference A - B
itself rather than two overlapping intervals. It also reports in how many test videos A beats B.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np

from eval_detector import score, video_of


def compare(cache_a, cache_b, split: Path, classes_a, classes_b, iou=0.5, op_conf=0.3,
            n_boot=1000, seed=0, unit="video") -> dict:
    names = [r["image"] for r in cache_a]
    if names != [r["image"] for r in cache_b]:
        raise SystemExit("the two runs were not scored on the same images; a paired comparison needs that")
    groups = [video_of(n) for n in names] if unit == "video" else None
    ra = score(cache_a, split, classes_a, iou, op_conf, n_boot, seed, groups, return_samples=True)
    rb = score(cache_b, split, classes_b, iou, op_conf, n_boot, seed, groups, return_samples=True)
    diffs = np.asarray(ra["boot_all"]) - np.asarray(rb["boot_all"])
    out = {
        "metric": "mAP@50 over all classes with ground truth",
        "a": ra["map50_all_classes"], "b": rb["map50_all_classes"],
        "diff": ra["map50_all_classes"] - rb["map50_all_classes"],
        "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))] if n_boot else None,
        "share_of_draws_a_not_better": float(np.mean(diffs <= 0)) if n_boot else None,
        "bootstrap_unit": unit, "bootstrap_samples": n_boot, "n_images": len(names),
        "per_class_ap50": {c: {"a": ra["per_class"][c]["ap50"], "b": rb["per_class"][c]["ap50"]}
                           for c in ra["per_class"]},
    }
    per_video = {}
    for v in sorted(set(video_of(n) for n in names)):
        idx = [i for i, n in enumerate(names) if video_of(n) == v]
        sa = score([cache_a[i] for i in idx], split, classes_a, iou, op_conf, 0, seed)["map50_all_classes"]
        sb = score([cache_b[i] for i in idx], split, classes_b, iou, op_conf, 0, seed)["map50_all_classes"]
        per_video[v] = {"images": len(idx), "a": sa, "b": sb}
    out["per_video"] = per_video
    out["videos_a_better"] = sum(r["a"] > r["b"] for r in per_video.values())
    out["videos_b_better"] = sum(r["a"] < r["b"] for r in per_video.values())
    return out


def to_markdown(r: dict, name_a: str, name_b: str) -> str:
    lo, hi = r["ci95"] or (float("nan"), float("nan"))
    lines = [f"# {name_a} vs {name_b}", "",
             f"{r['n_images']} test images, {len(r['per_video'])} videos · {r['metric']}", "",
             f"**A − B = {r['diff']:+.3f}** (A {r['a']:.3f}, B {r['b']:.3f}; paired 95 % CI {lo:+.3f} to {hi:+.3f}, "
             f"{r['bootstrap_samples']} draws over {r['bootstrap_unit']}s) · A better in "
             f"{r['videos_a_better']} of {len(r['per_video'])} videos", "",
             "| Class | AP@50 A | AP@50 B | A − B |", "|---|---|---|---|"]
    for c, v in r["per_class_ap50"].items():
        lines.append(f"| {c} | {v['a']:.3f} | {v['b']:.3f} | {v['a'] - v['b']:+.3f} |")
    lines += ["", "| Video | Images | mAP@50 A | mAP@50 B |", "|---|---|---|---|"]
    for v, x in r["per_video"].items():
        lines.append(f"| {v} | {x['images']} | {x['a']:.3f} | {x['b']:.3f} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--split", type=Path, required=True, help="the shared test folder (images/, labels/)")
    ap.add_argument("--a", type=Path, required=True, help="eval_detector.py output prefix of run A")
    ap.add_argument("--b", type=Path, required=True, help="eval_detector.py output prefix of run B")
    ap.add_argument("--out", type=Path, required=True, help="output prefix for .json and .md")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--op-conf", type=float, default=0.3)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--bootstrap-unit", choices=["image", "video"], default="video")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    def load(prefix: Path) -> dict:
        with open(prefix.with_suffix(".detections.pkl"), "rb") as fh:  # our own eval_detector output only
            return pickle.load(fh)

    A, B = load(a.a), load(a.b)
    r = compare(A["cache"], B["cache"], a.split, A["model_classes"], B["model_classes"], a.iou, a.op_conf,
                a.bootstrap, a.seed, a.bootstrap_unit)
    r |= {"a_run": str(a.a), "b_run": str(a.b), "split": str(a.split)}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(r, indent=1))
    md = to_markdown(r, a.a.name, a.b.name)
    a.out.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
