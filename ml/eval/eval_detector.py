"""Detector evaluation on a YOLO-format split in the unified classes (PLAN §7; thesis RQ1).

Scores any roadwatch detector backend -- the COCO-pretrained baseline or a fine-tuned model --
on a split such as data/processed/badodd/test and reports:

* per-class AP@50 (all-point interpolation) and mAP@50 with a 95 % bootstrap CI over images;
* mAP over every class that has ground truth, and over only the classes the model can output
  (a COCO model can never output rickshaw / CNG, which is the point of the baseline);
* precision / recall at the pipeline's operating threshold;
* a "what did the detector call it" table: for each ground-truth class, the class of the
  best-overlapping detection at the operating threshold, or "missed".

Raw detections are cached, so the scores can be recomputed without re-running the model.

    cd ml
    .venv\\Scripts\\python eval\\eval_detector.py --split ..\\data\\processed\\badodd\\test ^
        --out eval\\results\\coco_rtdetr_badodd_test
    .venv\\Scripts\\python eval\\eval_detector.py --split ..\\data\\processed\\badodd\\test ^
        --model-id models\\rtdetr_bd\\best --out eval\\results\\bd_rtdetr_badodd_test
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `roadwatch` importable

from roadwatch.types import CLASSES  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


# ---------------------------------------------------------------- matching + AP (pure, tested)
def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """IoU between every box in a (N,4) and b (M,4), boxes as x1,y1,x2,y2."""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


def match_image(det_boxes, det_cls, det_conf, gt_boxes, gt_cls, iou_thr=0.5):
    """Greedy COCO-style matching within one image, per class, in descending confidence.

    Returns a bool array: True where the detection is a true positive. Each ground-truth box
    can be matched once; a second detection on the same object is a false positive.
    """
    det_boxes = np.asarray(det_boxes, float).reshape(-1, 4)
    gt_boxes = np.asarray(gt_boxes, float).reshape(-1, 4)
    tp = np.zeros(len(det_boxes), bool)
    if len(det_boxes) == 0 or len(gt_boxes) == 0:
        return tp
    ious = iou_matrix(det_boxes, gt_boxes)
    used = np.zeros(len(gt_boxes), bool)
    gt_cls = np.asarray(gt_cls)
    for i in np.argsort(-np.asarray(det_conf), kind="stable"):
        cand = np.where((gt_cls == det_cls[i]) & ~used & (ious[i] >= iou_thr))[0]
        if len(cand):
            j = cand[np.argmax(ious[i, cand])]
            used[j] = True
            tp[i] = True
    return tp


def average_precision(conf, tp, n_gt, weight=None) -> float | None:
    """All-point interpolated AP. `weight` repeats detections (used by the bootstrap).

    Returns None when there is no ground truth for the class.
    """
    if n_gt <= 0:
        return None
    conf = np.asarray(conf, float)
    tp = np.asarray(tp, float)
    w = np.ones_like(conf) if weight is None else np.asarray(weight, float)
    keep = w > 0
    conf, tp, w = conf[keep], tp[keep], w[keep]
    if len(conf) == 0:
        return 0.0
    order = np.argsort(-conf, kind="stable")
    tp, w = tp[order], w[order]
    ctp = np.cumsum(tp * w)
    cfp = np.cumsum((1 - tp) * w)
    rec = ctp / n_gt
    prec = ctp / np.maximum(ctp + cfp, 1e-12)
    mrec = np.concatenate([[0.0], rec, [1.0]])
    mpre = np.concatenate([[0.0], prec, [0.0]])
    mpre = np.maximum.accumulate(mpre[::-1])[::-1]
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


# ---------------------------------------------------------------- data
def load_gt(label_path: Path, w: int, h: int):
    boxes, cls = [], []
    if label_path.exists():
        for line in label_path.read_text().splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:5])
            boxes.append([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
            cls.append(CLASSES[c])
    return np.asarray(boxes, float).reshape(-1, 4), cls


def run_detector(args, images):
    import cv2

    from roadwatch.detect import make_detector

    kw = {"conf": args.conf_floor}
    if args.model_id:
        kw["model_id" if args.detector == "hf" else "weights"] = args.model_id
    det = make_detector(args.detector, **kw)
    if det.mapping is None:  # fine-tuned model: outputs unified classes directly
        model_classes = sorted(set(det.names if det.names is not None else CLASSES) & set(CLASSES))
    else:                    # COCO model: only what COCO_TO_UNIFIED can produce
        model_classes = sorted(set(det.mapping.values()))

    cache = []
    t0 = time.time()
    for k, img_path in enumerate(images):
        frame = cv2.imread(str(img_path))
        if frame is None:
            print(f"  ! unreadable image skipped: {img_path.name}")
            continue
        h, w = frame.shape[:2]
        ds = det(frame, k, 0.0)
        cache.append({
            "image": img_path.name, "w": w, "h": h,
            "boxes": np.asarray([d.box for d in ds], float).reshape(-1, 4),
            "cls": [d.cls for d in ds],
            "conf": np.asarray([d.conf for d in ds], float),
        })
        if (k + 1) % 50 == 0 or k + 1 == len(images):
            el = time.time() - t0
            eta = el / (k + 1) * (len(images) - k - 1)
            print(f"  {k + 1}/{len(images)} images  {el / (k + 1):.2f} s/img  ETA {eta / 60:.1f} min", flush=True)
    return cache, model_classes, getattr(det, "name", args.detector)


# ---------------------------------------------------------------- scoring
def score(cache, split: Path, model_classes, iou_thr, op_conf, n_boot, seed):
    n_img = len(cache)
    per_cls_conf, per_cls_tp, per_cls_img = defaultdict(list), defaultdict(list), defaultdict(list)
    gt_count = defaultdict(lambda: np.zeros(n_img))
    confusion = defaultdict(Counter)
    op_tp, op_det = Counter(), Counter()

    for i, rec in enumerate(cache):
        gt_boxes, gt_cls = load_gt(split / "labels" / (Path(rec["image"]).stem + ".txt"), rec["w"], rec["h"])
        for c in gt_cls:
            gt_count[c][i] += 1
        tp = match_image(rec["boxes"], rec["cls"], rec["conf"], gt_boxes, gt_cls, iou_thr)
        for c, s, t in zip(rec["cls"], rec["conf"], tp):
            per_cls_conf[c].append(s)
            per_cls_tp[c].append(t)
            per_cls_img[c].append(i)
            if s >= op_conf:
                op_det[c] += 1
                op_tp[c] += int(t)
        # what did the detector call each ground-truth object (any class, at the operating point)?
        keep = rec["conf"] >= op_conf
        ious = iou_matrix(gt_boxes, rec["boxes"][keep])
        kept_cls = [c for c, k in zip(rec["cls"], keep) if k]
        for g, c in enumerate(gt_cls):
            if ious.shape[1] and ious[g].max() >= iou_thr:
                confusion[c][kept_cls[int(np.argmax(ious[g]))]] += 1
            else:
                confusion[c]["missed"] += 1

    gt_classes = [c for c in CLASSES if gt_count[c].sum() > 0]

    def m_ap(weights, classes):
        aps = []
        for c in classes:
            n = float((gt_count[c] * weights).sum())
            if n <= 0:
                continue
            img = np.asarray(per_cls_img[c], int)
            ap = average_precision(per_cls_conf[c], per_cls_tp[c], n, weights[img] if len(img) else None)
            aps.append(ap)
        return float(np.mean(aps)) if aps else float("nan")

    ones = np.ones(n_img)
    per_class = {}
    for c in gt_classes:
        n = int(gt_count[c].sum())
        per_class[c] = {
            "n_gt": n,
            "ap50": average_precision(per_cls_conf[c], per_cls_tp[c], n),
            "precision_at_op": (op_tp[c] / op_det[c]) if op_det[c] else None,
            "recall_at_op": op_tp[c] / n,
            "n_det_at_op": op_det[c],
            "model_can_predict": c in model_classes,
        }
    predictable = [c for c in gt_classes if c in model_classes]

    rng = np.random.default_rng(seed)
    boot_all, boot_pred = [], []
    for _ in range(n_boot):
        wts = np.bincount(rng.integers(0, n_img, n_img), minlength=n_img).astype(float)
        boot_all.append(m_ap(wts, gt_classes))
        boot_pred.append(m_ap(wts, predictable))

    def ci(xs):
        return [float(np.percentile(xs, 2.5)), float(np.percentile(xs, 97.5))] if xs else None

    return {
        "n_images": n_img,
        "iou_threshold": iou_thr,
        "operating_conf": op_conf,
        "per_class": per_class,
        "map50_all_classes": m_ap(ones, gt_classes),
        "map50_all_classes_ci95": ci(boot_all),
        "map50_predictable_classes": m_ap(ones, predictable),
        "map50_predictable_classes_ci95": ci(boot_pred),
        "predictable_classes": predictable,
        "bootstrap_samples": n_boot,
        "confusion_at_op": {c: dict(confusion[c].most_common()) for c in gt_classes},
    }


def to_markdown(res: dict) -> str:
    def f(x):
        return "—" if x is None else f"{x:.3f}"

    lo, hi = res["map50_all_classes_ci95"] or [None, None]
    plo, phi = res["map50_predictable_classes_ci95"] or [None, None]
    lines = [
        f"# Detector evaluation — {res['detector']} `{res.get('model_id') or 'COCO default'}`",
        "",
        f"Split `{res['split']}` · {res['n_images']} images · IoU {res['iou_threshold']} · "
        f"operating threshold {res['operating_conf']} · {res['date']}",
        "",
        f"**mAP@50, all classes with ground truth:** {f(res['map50_all_classes'])} "
        f"(95 % bootstrap CI {f(lo)}–{f(hi)})",
        "",
        f"**mAP@50, classes the model can output** ({', '.join(res['predictable_classes'])}): "
        f"{f(res['map50_predictable_classes'])} (95 % CI {f(plo)}–{f(phi)})",
        "",
        "| Class | GT boxes | AP@50 | Precision @op | Recall @op | Model can output it |",
        "|---|---|---|---|---|---|",
    ]
    for c, r in res["per_class"].items():
        lines.append(f"| {c} | {r['n_gt']} | {f(r['ap50'])} | {f(r['precision_at_op'])} | "
                     f"{f(r['recall_at_op'])} | {'yes' if r['model_can_predict'] else '**no**'} |")
    lines += ["", "## What the detector called each ground-truth object (at the operating threshold)", "",
              "| Ground truth | Top predictions (share of GT boxes) |", "|---|---|"]
    for c, cnt in res["confusion_at_op"].items():
        tot = sum(cnt.values())
        top = ", ".join(f"{k} {v / tot:.0%}" for k, v in list(cnt.items())[:4])
        lines.append(f"| {c} | {top} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--split", required=True, type=Path, help="folder with images/ and labels/ (YOLO, unified ids)")
    ap.add_argument("--out", required=True, type=Path, help="output prefix, e.g. eval/results/coco_rtdetr_badodd_test")
    ap.add_argument("--detector", default="hf", choices=["hf", "rfdetr", "ultralytics"])
    ap.add_argument("--model-id", default=None, help="HF model id / local folder, or weights for other backends")
    ap.add_argument("--conf-floor", type=float, default=0.01, help="lowest score kept, for the PR curve")
    ap.add_argument("--op-conf", type=float, default=0.3, help="pipeline operating threshold for P/R and confusion")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0, help="evaluate a random subset of N images (0 = all)")
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--reuse-cache", action="store_true", help="skip inference and rescore the cached detections")
    args = ap.parse_args()

    images = sorted(p for p in (args.split / "images").iterdir() if p.suffix.lower() in IMG_EXT)
    if args.limit:
        rng = np.random.default_rng(args.seed)
        images = sorted(rng.choice(images, size=min(args.limit, len(images)), replace=False))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cache_path = args.out.with_suffix(".detections.pkl")

    t0 = time.time()
    if args.reuse_cache:
        with open(cache_path, "rb") as fh:
            saved = pickle.load(fh)
        cache, model_classes, det_name = saved["cache"], saved["model_classes"], saved["detector"]
    else:
        print(f"running {args.detector} on {len(images)} images from {args.split}")
        cache, model_classes, det_name = run_detector(args, images)
        with open(cache_path, "wb") as fh:
            pickle.dump({"cache": cache, "model_classes": model_classes, "detector": det_name}, fh)

    res = score(cache, args.split, model_classes, args.iou, args.op_conf, args.bootstrap, args.seed)
    res.update({"detector": det_name, "model_id": args.model_id, "split": str(args.split),
                "conf_floor": args.conf_floor, "date": date.today().isoformat(),
                "seconds": round(time.time() - t0, 1)})
    args.out.with_suffix(".json").write_text(json.dumps(res, indent=1))
    md = to_markdown(res)
    args.out.with_suffix(".md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"written {args.out.with_suffix('.json')} and .md")


if __name__ == "__main__":
    main()
