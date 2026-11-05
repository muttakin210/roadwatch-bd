"""Map each dataset's labels to the unified class list (PLAN §4.4) and write YOLO-format labels.

    python scripts/convert_datasets.py --dataset dhakaai --src D:/datasets/DhakaAI --dst ../data/processed/dhakaai

Input: Pascal-VOC XML (DhakaAI, Poribohon-BD) or COCO JSON (--coco file.json).
Unknown labels are reported and skipped — add them to MAPS rather than guessing.
Check each dataset's licence first and record it in docs/dataset_card.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roadwatch.types import CLASS_ID  # noqa: E402

_COMMON = {
    "bus": "bus", "minibus": "bus", "double decker bus": "bus", "double-decker": "bus", "city bus": "bus",
    "car": "car", "taxi": "car", "suv": "microbus", "jeep": "microbus", "microbus": "microbus", "minivan": "microbus",
    "van": "pickup", "covered van": "pickup", "pickup": "pickup", "pickup truck": "pickup",
    "truck": "truck", "army vehicle": "truck",
    "motorbike": "motorcycle", "motorcycle": "motorcycle", "scooter": "motorcycle",
    "bicycle": "bicycle", "bike": "bicycle",
    "rickshaw": "rickshaw", "rickshaw van": "rickshaw_van", "van rickshaw": "rickshaw_van",
    "auto rickshaw": "cng_autorickshaw", "three wheelers (cng)": "cng_autorickshaw", "cng": "cng_autorickshaw",
    "easybike": "easybike", "easy bike": "easybike", "e-rickshaw": "easybike", "battery rickshaw": "easybike",
    "leguna": "leguna", "human hauler": "leguna", "tempo": "leguna",
    "ambulance": "ambulance", "police car": "ambulance", "fire service": "ambulance",
    "person": "person", "pedestrian": "person",
    "wheelbarrow": "other", "tractor": "other", "cart": "other", "garbagevan": "pickup",
}
MAPS = {"dhakaai": _COMMON, "poribohon": _COMMON, "badodd": _COMMON, "coco": {
    "person": "person", "bicycle": "bicycle", "car": "car", "motorcycle": "motorcycle", "bus": "bus", "truck": "truck"}}


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().replace("_", " ").split())


def convert_voc(src: Path, dst: Path, mapping: dict) -> Counter:
    stats, unknown = Counter(), Counter()
    (dst / "images").mkdir(parents=True, exist_ok=True); (dst / "labels").mkdir(parents=True, exist_ok=True)
    for xml in sorted(src.rglob("*.xml")):
        root = ET.parse(xml).getroot()
        fn = root.findtext("filename") or xml.stem + ".jpg"
        img = next((p for p in [xml.with_name(fn), *xml.parent.glob(xml.stem + ".*")]
                    if p.exists() and p.suffix.lower() in (".jpg", ".jpeg", ".png")), None)
        size = root.find("size")
        if img is None or size is None:
            continue
        W, H = float(size.findtext("width")), float(size.findtext("height"))
        if W <= 0 or H <= 0:
            continue
        lines = []
        for obj in root.iter("object"):
            name = _norm(obj.findtext("name", ""))
            cls = mapping.get(name)
            if cls is None:
                unknown[name] += 1
                continue
            bb = obj.find("bndbox")
            x1, y1, x2, y2 = (float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
            x1, x2 = max(0, min(x1, x2)), min(W, max(x1, x2)); y1, y2 = max(0, min(y1, y2)), min(H, max(y1, y2))
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            lines.append(f"{CLASS_ID[cls]} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
            stats[cls] += 1
        stem = f"{xml.parent.name}_{xml.stem}"
        shutil.copy2(img, dst / "images" / (stem + img.suffix.lower()))
        (dst / "labels" / (stem + ".txt")).write_text("\n".join(lines))
    if unknown:
        print("UNMAPPED labels (add to MAPS):", dict(unknown.most_common()))
    return stats


def convert_coco(js: Path, img_dir: Path, dst: Path, mapping: dict) -> Counter:
    d = json.loads(js.read_text(encoding="utf-8"))
    cats = {c["id"]: _norm(c["name"]) for c in d["categories"]}
    imgs = {i["id"]: i for i in d["images"]}
    per: dict[int, list[str]] = {}
    stats = Counter()
    for a in d["annotations"]:
        cls = mapping.get(cats[a["category_id"]])
        if cls is None:
            continue
        im = imgs[a["image_id"]]
        x, y, w, h = a["bbox"]
        per.setdefault(im["id"], []).append(
            f"{CLASS_ID[cls]} {(x + w / 2) / im['width']:.6f} {(y + h / 2) / im['height']:.6f} "
            f"{w / im['width']:.6f} {h / im['height']:.6f}")
        stats[cls] += 1
    (dst / "images").mkdir(parents=True, exist_ok=True); (dst / "labels").mkdir(parents=True, exist_ok=True)
    for iid, lines in per.items():
        src = img_dir / imgs[iid]["file_name"]
        if src.exists():
            shutil.copy2(src, dst / "images" / src.name)
            (dst / "labels" / (src.stem + ".txt")).write_text("\n".join(lines))
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, choices=sorted(MAPS))
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--dst", required=True, type=Path)
    ap.add_argument("--coco", type=Path, help="COCO json (otherwise Pascal-VOC XML under --src)")
    a = ap.parse_args()
    m = MAPS[a.dataset]
    stats = convert_coco(a.coco, a.src, a.dst, m) if a.coco else convert_voc(a.src, a.dst, m)
    print("boxes per class:", dict(stats.most_common()))
    rare = [c for c, n in stats.items() if n < 300]
    if rare:
        print("fewer than ~300 examples (consider merging, PLAN §4.4):", rare)


if __name__ == "__main__":
    main()
