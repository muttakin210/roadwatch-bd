"""Fine-tune RT-DETR (Apache-2.0) on YOLO-format data in the unified classes (PLAN §5.3, Phase 3).

    # smoke test on CPU (a few steps, proves the loop works)
    python scripts/train_detector.py --data ../data/processed/badodd --out ../ml/models/rtdetr_smoke \
        --epochs 1 --max-train 16 --max-val 8 --batch 2

    # real run (GPU, e.g. Kaggle T4): see notebooks/train_rtdetr_kaggle.ipynb
    python scripts/train_detector.py --data /kaggle/working/badodd --out /kaggle/working/rtdetr_bd --epochs 30

Data layout: <data>/<train|val>/{images,labels}, YOLO txt lines "cls cx cy w h" (normalised), cls = index
into roadwatch.types.CLASSES (what convert_datasets.py writes). The saved model's id2label is CLASSES, so
roadwatch.detect.HFDetector uses it directly: `--detector hf --weights <out>/best`.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadwatch.types import CLASSES  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png")


class YoloDataset(torch.utils.data.Dataset):
    def __init__(self, split_dir: Path, limit: int | None = None, train: bool = False, seed: int = 0):
        self.items = []
        for lp in sorted((split_dir / "labels").glob("*.txt")):
            img = next((p for p in (split_dir / "images").glob(lp.stem + ".*") if p.suffix.lower() in IMG_EXT), None)
            if img is not None:
                self.items.append((img, lp))
        if not self.items:
            raise SystemExit(f"no image/label pairs under {split_dir}")
        if limit:
            random.Random(seed).shuffle(self.items)
            self.items = self.items[:limit]
        self.train = train

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        img_path, lp = self.items[i]
        img = Image.open(img_path).convert("RGB")
        W, H = img.size
        boxes, cls = [], []
        for row in lp.read_text().splitlines():
            p = row.split()
            if len(p) < 5:
                continue
            c, cx, cy, w, h = int(p[0]), *map(float, p[1:5])
            if w <= 0 or h <= 0:
                continue
            boxes.append([(cx - w / 2) * W, (cy - h / 2) * H, w * W, h * H])  # COCO xywh, pixels
            cls.append(c)
        if self.train and random.random() < 0.5:  # horizontal flip; the detector is direction-agnostic
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
            boxes = [[W - x - w, y, w, h] for x, y, w, h in boxes]
        ann = {"image_id": i, "annotations": [
            {"bbox": b, "category_id": c, "area": b[2] * b[3], "iscrowd": 0} for b, c in zip(boxes, cls)]}
        return img, ann, (H, W)


def make_collate(proc):
    def collate(batch):
        imgs, anns, sizes = zip(*batch)
        enc = proc(images=list(imgs), annotations=list(anns), return_tensors="pt")
        targets = [{"boxes": torch.tensor([[x, y, x + w, y + h] for x, y, w, h in (a["bbox"] for a in an["annotations"])],
                                          dtype=torch.float32).reshape(-1, 4),
                    "labels": torch.tensor([a["category_id"] for a in an["annotations"]], dtype=torch.long)}
                   for an in anns]
        return enc["pixel_values"], enc["labels"], targets, list(sizes)
    return collate


@torch.no_grad()
def evaluate(model, proc, loader, device, amp: bool) -> dict:
    from torchmetrics.detection import MeanAveragePrecision
    metric = MeanAveragePrecision(iou_type="bbox", class_metrics=True)
    model.eval()
    losses = []
    for pix, labels, targets, sizes in loader:
        pix = pix.to(device)
        labels = [{k: v.to(device) for k, v in t.items()} for t in labels]
        with torch.autocast(device.type, enabled=amp):
            out = model(pixel_values=pix, labels=labels)
        losses.append(float(out.loss))
        res = proc.post_process_object_detection(out, threshold=0.01, target_sizes=sizes)
        metric.update([{k: r[k].float().cpu() if k == "boxes" else r[k].cpu() for k in ("boxes", "scores", "labels")}
                       for r in res], targets)
    m = metric.compute()
    per_class = {}
    if m.get("classes") is not None and m["map_per_class"].numel() > 1:
        per_class = {CLASSES[int(c)]: round(float(ap), 4) for c, ap in zip(m["classes"], m["map_per_class"])}
    model.train()
    return {"val_loss": round(sum(losses) / max(len(losses), 1), 4), "map": round(float(m["map"]), 4),
            "map50": round(float(m["map_50"]), 4), "ap_per_class": per_class}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fine-tune RT-DETR on unified-class YOLO data")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", default="PekingU/rtdetr_r18vd")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lr-backbone", type=float, default=1e-5)
    ap.add_argument("--size", type=int, default=640, help="square input size")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-train", type=int, default=None, help="limit images (smoke tests)")
    ap.add_argument("--max-val", type=int, default=500, help="val images used for mAP each epoch")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    from transformers import AutoImageProcessor, AutoModelForObjectDetection
    random.seed(a.seed); torch.manual_seed(a.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    amp = device.type == "cuda"

    proc = AutoImageProcessor.from_pretrained(a.base, size={"height": a.size, "width": a.size})
    model = AutoModelForObjectDetection.from_pretrained(
        a.base, id2label=dict(enumerate(CLASSES)), label2id={c: i for i, c in enumerate(CLASSES)},
        ignore_mismatched_sizes=True,  # new class head; everything else keeps the COCO pretraining
    ).to(device)

    collate = make_collate(proc)
    tr = YoloDataset(a.data / "train", a.max_train, train=True, seed=a.seed)
    va = YoloDataset(a.data / "val", a.max_val, seed=a.seed)
    tl = torch.utils.data.DataLoader(tr, a.batch, shuffle=True, num_workers=a.workers, collate_fn=collate,
                                     drop_last=len(tr) > a.batch, persistent_workers=a.workers > 0)
    vl = torch.utils.data.DataLoader(va, a.batch, num_workers=a.workers, collate_fn=collate)

    bb = [p for n, p in model.named_parameters() if "backbone" in n]
    rest = [p for n, p in model.named_parameters() if "backbone" not in n]
    opt = torch.optim.AdamW([{"params": bb, "lr": a.lr_backbone}, {"params": rest, "lr": a.lr}], weight_decay=1e-4)
    total = a.epochs * len(tl)
    warm = min(500, max(1, total // 20))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))
    scaler = torch.amp.GradScaler(enabled=amp)

    a.out.mkdir(parents=True, exist_ok=True)
    log = {"args": {k: str(v) for k, v in vars(a).items()}, "classes": CLASSES, "train_images": len(tr),
           "val_images": len(va), "device": str(device), "epochs": []}
    best = -1.0
    print(f"train {len(tr)} imgs, val {len(va)} imgs, {len(tl)} steps/epoch on {device}", flush=True)
    step = 0
    for ep in range(a.epochs):
        model.train()
        t0, run = time.time(), 0.0
        for pix, labels, _, _ in tl:
            pix = pix.to(device)
            labels = [{k: v.to(device) for k, v in t.items()} for t in labels]
            with torch.autocast(device.type, enabled=amp):
                loss = model(pixel_values=pix, labels=labels).loss
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.1)
            scaler.step(opt); scaler.update(); sched.step()
            step += 1
            run += float(loss.detach())
            if step % 50 == 0:
                print(f"  step {step}/{total} loss {run / ((step - 1) % len(tl) + 1):.3f}", flush=True)
        ev = evaluate(model, proc, vl, device, amp)
        ev |= {"epoch": ep + 1, "train_loss": round(run / max(1, len(tl)), 4), "minutes": round((time.time() - t0) / 60, 1)}
        log["epochs"].append(ev)
        print(f"epoch {ep + 1}: train_loss {ev['train_loss']} val_loss {ev['val_loss']} "
              f"mAP50 {ev['map50']} mAP {ev['map']} ({ev['minutes']} min)", flush=True)
        if ev["map50"] > best:
            best = ev["map50"]
            model.save_pretrained(a.out / "best"); proc.save_pretrained(a.out / "best")
            log["best"] = ev
        (a.out / "train_log.json").write_text(json.dumps(log, indent=1))
    model.save_pretrained(a.out / "last"); proc.save_pretrained(a.out / "last")
    print("best mAP50", best, "->", a.out / "best")


if __name__ == "__main__":
    main()
