"""Detector interface + swappable backends (PLAN §5.3).

⚠ Licence: Ultralytics YOLO is AGPL-3.0. Use it only if the platform is open-sourced under AGPL
or you hold an Enterprise licence. Apache-2.0 alternatives: RF-DETR, D-FINE, YOLOX, RT-DETR (HF).
Everything else in the pipeline talks only to `Detector`, so the backend can be swapped freely.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np

from .types import CLASSES, Detection

# COCO → unified classes, for the Phase-1 prototype with un-fine-tuned COCO weights.
# HF RT-DETR (PekingU/rtdetr_*) labels COCO class 3 with the Pascal-VOC name "motorbike", while
# Ultralytics and RF-DETR say "motorcycle"; without both keys the default detector drops every motorbike.
COCO_TO_UNIFIED = {"person": "person", "bicycle": "bicycle", "car": "car", "motorcycle": "motorcycle",
                   "motorbike": "motorcycle", "bus": "bus", "truck": "truck"}


class Detector(Protocol):
    name: str

    def __call__(self, frame: np.ndarray, frame_idx: int, t: float) -> list[Detection]: ...


def _mk(boxes, scores, labels, names, frame_idx, t, conf, mapping) -> list[Detection]:
    out = []
    for b, s, l in zip(boxes, scores, labels):
        if s < conf:
            continue
        n = names[int(l)] if names is not None else str(l)
        cls = mapping.get(n, n) if mapping is not None else n
        if cls in CLASSES:
            out.append(Detection(frame_idx, t, np.asarray(b, float), cls, float(s)))
    return out


class UltralyticsDetector:
    """AGPL-3.0 — see the module docstring."""
    name = "ultralytics"

    def __init__(self, weights: str = "yolo11s.pt", imgsz: int = 960, conf: float = 0.25, device=None):
        from ultralytics import YOLO
        self.model, self.imgsz, self.conf, self.device = YOLO(weights), imgsz, conf, device
        names = self.model.names
        self.names = [names[i] for i in range(len(names))]
        self.mapping = None if set(self.names) <= set(CLASSES) else COCO_TO_UNIFIED

    def __call__(self, frame, frame_idx, t):
        r = self.model.predict(frame, imgsz=self.imgsz, conf=self.conf, device=self.device, verbose=False)[0]
        b = r.boxes
        return _mk(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy(),
                   self.names, frame_idx, t, self.conf, self.mapping)


class RFDETRDetector:
    """Apache-2.0 (roboflow/rf-detr)."""
    name = "rfdetr"

    def __init__(self, weights: str | None = None, conf: float = 0.3, size: str = "base"):
        import rfdetr
        cls = rfdetr.RFDETRBase if size == "base" else getattr(rfdetr, f"RFDETR{size.capitalize()}")
        self.model = cls(pretrain_weights=weights) if weights else cls()
        self.conf = conf
        from rfdetr.util.coco_classes import COCO_CLASSES
        self.names = COCO_CLASSES if weights is None else None
        self.mapping = COCO_TO_UNIFIED if weights is None else None

    def __call__(self, frame, frame_idx, t):
        import cv2
        d = self.model.predict(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), threshold=self.conf)
        names = self.names if self.names is not None else CLASSES
        return _mk(d.xyxy, d.confidence, d.class_id, names, frame_idx, t, self.conf, self.mapping)


class HFDetector:
    """Hugging Face Transformers object detection, e.g. RT-DETR (Apache-2.0): PekingU/rtdetr_r18vd."""
    name = "hf"

    def __init__(self, model_id: str = "PekingU/rtdetr_r18vd", conf: float = 0.3, device: str | None = None):
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.proc = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForObjectDetection.from_pretrained(model_id).to(self.device).eval()
        id2label = self.model.config.id2label
        self.names = [id2label[i] for i in sorted(id2label)]
        self.mapping = None if set(self.names) <= set(CLASSES) else COCO_TO_UNIFIED
        self.conf = conf

    def __call__(self, frame, frame_idx, t):
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        inp = self.proc(images=rgb, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model(**inp)
        r = self.proc.post_process_object_detection(out, threshold=self.conf, target_sizes=[rgb.shape[:2]])[0]
        return _mk(r["boxes"].cpu().numpy(), r["scores"].cpu().numpy(), r["labels"].cpu().numpy(),
                   self.names, frame_idx, t, self.conf, self.mapping)


BACKENDS = {"ultralytics": UltralyticsDetector, "rfdetr": RFDETRDetector, "hf": HFDetector}


def make_detector(backend: str = "hf", **kw) -> Detector:
    if backend not in BACKENDS:
        raise ValueError(f"unknown detector backend {backend!r}; choose from {sorted(BACKENDS)}")
    return BACKENDS[backend](**kw)
