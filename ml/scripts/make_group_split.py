"""Re-split BadODD so that no video has frames in two splits (benchmark paper; thesis RQ1).

BadODD's official split is by image. Every one of its 44 videos has frames in train and val (42 also in
test), and the labelled frames of a video are only ~59 frames apart, so almost every test image has a
near-identical training image. Scores on that split partly measure memorised scenes.

This script pools the official train/val/test images, groups them by video (the file name minus its
trailing ``_<frame>``) and assigns whole videos to train / val / test. Out of many random assignments it
keeps the one whose split sizes, per-class box shares and share of night footage are closest to the
official split, so the two protocols differ in leakage and as little else as possible. The assignment is
saved to a manifest that is committed, so every machine (and Kaggle) rebuilds exactly the same split.

    cd ml
    # once: search for an assignment and write the manifest (+ leakage statistics of both protocols)
    python scripts/make_group_split.py search --src ../data/processed/badodd \\
        --manifest configs/splits/badodd_video_v1.json
    # build the split folders from the manifest (hard links on the same drive: no extra disk space)
    python scripts/make_group_split.py build --src ../data/processed/badodd \\
        --manifest configs/splits/badodd_video_v1.json --dst ../data/processed/badodd_video
    # the leakage experiment: leaky/ and clean/ training sets of equal size that share one test set
    python scripts/make_group_split.py paired --src ../data/processed/badodd \\
        --manifest configs/splits/badodd_video_v1.json --dst ../data/processed/badodd_paired
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_datasets import _link_or_copy  # noqa: E402
from roadwatch.types import CLASSES  # noqa: E402

SPLITS = ("train", "val", "test")
IMG_EXT = (".jpg", ".jpeg", ".png")
_FRAME = re.compile(r"^(?P<video>.+)_(?P<frame>\d+)$")


def video_of(stem: str) -> tuple[str, int]:
    """'chittagong_bohoddarhat1_10384' -> ('chittagong_bohoddarhat1', 10384)."""
    m = _FRAME.match(stem)
    if not m:
        raise ValueError(f"cannot read a video name and frame number from {stem!r}")
    return m["video"], int(m["frame"])


def is_night(video: str) -> bool:
    return "night" in video


@dataclass
class Item:
    stem: str
    official: str      # split folder the image came from
    image: Path
    label: Path
    video: str
    frame: int
    boxes: Counter     # class name -> boxes in this image


def scan(src: Path) -> list[Item]:
    items = []
    for split in SPLITS:
        lab_dir = src / split / "labels"
        if not lab_dir.is_dir():
            continue
        imgs = {p.stem: p for p in (src / split / "images").iterdir() if p.suffix.lower() in IMG_EXT}
        for lp in sorted(lab_dir.glob("*.txt")):
            if lp.stem not in imgs:
                continue
            rows = [r.split() for r in lp.read_text().splitlines()]
            boxes = Counter(CLASSES[int(r[0])] for r in rows if len(r) >= 5)
            video, frame = video_of(lp.stem)
            items.append(Item(lp.stem, split, imgs[lp.stem], lp, video, frame, boxes))
    if not items:
        raise SystemExit(f"no image/label pairs under {src}/<train|val|test>")
    return items


def video_table(items: list[Item]) -> dict[str, dict]:
    table: dict[str, dict] = defaultdict(lambda: {"images": 0, "boxes": Counter()})
    for it in items:
        table[it.video]["images"] += 1
        table[it.video]["boxes"].update(it.boxes)
    return dict(table)


def summarise(assign: dict[str, str], table: dict[str, dict]) -> dict[str, dict]:
    out = {s: {"videos": 0, "images": 0, "night_images": 0, "boxes": Counter()} for s in SPLITS}
    for v, s in assign.items():
        o, r = out[s], table[v]
        o["videos"] += 1
        o["images"] += r["images"]
        o["boxes"].update(r["boxes"])
        if is_night(v):
            o["night_images"] += r["images"]
    return out


# Night footage comes in five videos, two of them very long (695 and 869 frames), so a split's night share
# can only be matched roughly; weighting it like the class shares would trade class balance for it.
NIGHT_WEIGHT = 0.1


def cost(assign: dict[str, str], table: dict[str, dict], target: dict[str, float]) -> float:
    """0 = every split has exactly its target share of the images, of each class's boxes and of night images.

    Hard-ish constraints (+10 each): every class with ground truth, and some night footage, in every split.
    """
    summ = summarise(assign, table)
    tot_img = sum(r["images"] for r in table.values())
    tot_box = Counter()
    for r in table.values():
        tot_box.update(r["boxes"])
    classes = [k for k in CLASSES if tot_box[k]]
    tot_night = sum(r["images"] for v, r in table.items() if is_night(v))
    c = 0.0
    for s in SPLITS:
        o, t = summ[s], target[s]
        if o["images"] == 0:
            return float("inf")
        c += abs(o["images"] / tot_img - t) / t                       # split size
        devs = [abs(o["boxes"][k] / tot_box[k] - t) / t for k in classes]
        c += sum(devs) / len(devs) + max(devs)                         # each class ~t of its boxes, none far off
        c += 10.0 * sum(1 for k in classes if o["boxes"][k] == 0)     # a class missing from a split
        if tot_night:
            c += NIGHT_WEIGHT * abs(o["night_images"] / tot_night - t) / t
            c += 10.0 * (o["night_images"] == 0)
    return c


def search(table: dict[str, dict], target: dict[str, float], trials: int = 20000, seed: int = 0):
    """Random greedy fills (largest relative image deficit first), then move/swap hill-climbing."""
    rng = random.Random(seed)
    videos = sorted(table)
    tot = sum(r["images"] for r in table.values())
    best, best_cost = None, float("inf")
    for _ in range(trials):
        order = videos[:]
        rng.shuffle(order)
        filled = dict.fromkeys(SPLITS, 0)
        assign = {}
        for v in order:
            s = max(SPLITS, key=lambda s: (target[s] * tot - filled[s]) / (target[s] * tot))
            assign[v] = s
            filled[s] += table[v]["images"]
        c = cost(assign, table, target)
        if c < best_cost:
            best, best_cost = assign, c
    improved = True
    while improved:
        improved = False
        moves = [(v, s) for v in videos for s in SPLITS if s != best[v]]
        swaps = [(a, b) for i, a in enumerate(videos) for b in videos[i + 1:] if best[a] != best[b]]
        for cand in ([{**best, v: s} for v, s in moves] + [{**best, a: best[b], b: best[a]} for a, b in swaps]):
            cc = cost(cand, table, target)
            if cc < best_cost - 1e-12:
                best, best_cost, improved = cand, cc, True
                break
    return dict(sorted(best.items())), best_cost


def frame_gaps(items: list[Item], split_of) -> dict:
    """For every test image: frames to the nearest train/val image of the same video (the leak)."""
    seen = defaultdict(list)
    for it in items:
        if split_of(it) != "test":
            seen[it.video].append(it.frame)
    gaps = [min((abs(it.frame - f) for f in seen[it.video]), default=None)
            for it in items if split_of(it) == "test"]
    near = sorted(g for g in gaps if g is not None)

    def q(p):
        return near[int(p * (len(near) - 1))] if near else None

    return {"test_images": len(gaps), "with_same_video_frame": len(near),
            "median_gap_frames": q(0.5), "p10_gap_frames": q(0.1), "p90_gap_frames": q(0.9),
            "within_30_frames": sum(g <= 30 for g in near)}


def _jsonable(summ: dict[str, dict]) -> dict:
    return {s: {"videos": o["videos"], "images": o["images"], "night_images": o["night_images"],
                "boxes": {k: o["boxes"][k] for k in CLASSES if o["boxes"][k]}} for s, o in summ.items()}


def official_summary(items: list[Item]) -> dict[str, dict]:
    out = {s: {"videos": set(), "images": 0, "night_images": 0, "boxes": Counter()} for s in SPLITS}
    for it in items:
        o = out[it.official]
        o["videos"].add(it.video)
        o["images"] += 1
        o["night_images"] += is_night(it.video)
        o["boxes"].update(it.boxes)
    for o in out.values():
        o["videos"] = len(o["videos"])
    return out


def print_summary(name: str, summ: dict[str, dict]) -> None:
    tot = Counter()
    for o in summ.values():
        tot.update(o["boxes"])
    print(f"\n{name}")
    print(f"  {'split':6s} {'videos':>6s} {'images':>7s} {'night':>6s}  " + " ".join(f"{k[:8]:>8s}" for k in CLASSES if tot[k]))
    for s, o in summ.items():
        shares = " ".join(f"{o['boxes'][k] / tot[k]:8.2f}" for k in CLASSES if tot[k])
        print(f"  {s:6s} {o['videos']:6d} {o['images']:7d} {o['night_images']:6d}  {shares}")


def cmd_search(a) -> None:
    items = scan(a.src)
    table = video_table(items)
    off = official_summary(items)
    tot = len(items)
    target = {s: off[s]["images"] / tot for s in SPLITS}  # same proportions as the official split
    assign, c = search(table, target, a.trials, a.seed)
    summ = summarise(assign, table)
    leak = {"official_split": frame_gaps(items, lambda it: it.official),
            "video_split": frame_gaps(items, lambda it: assign[it.video])}
    manifest = {
        "name": a.manifest.stem,
        "created": date.today().isoformat(),
        "about": "BadODD re-split so that every video lies in exactly one of train/val/test; sizes, per-class "
                 "box shares and night share matched to the official split. Built by scripts/make_group_split.py.",
        "source": "BadODD (Zenodo 13823687, CC BY 4.0) converted by scripts/convert_datasets.py; official "
                  "train+val+test pooled.",
        "group_by": "video = image file name without its trailing _<frame>",
        "search": {"seed": a.seed, "trials": a.trials, "cost": round(c, 4)},
        "splits": {s: sorted(v for v, x in assign.items() if x == s) for s in SPLITS},
        "summary": {"video_split": _jsonable(summ), "official_split": _jsonable(off)},
        "leakage": leak,
    }
    a.manifest.parent.mkdir(parents=True, exist_ok=True)
    a.manifest.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print_summary("official split (share of each class's boxes per split)", off)
    print_summary(f"video split, cost {c:.4f}", summ)
    print("\nleakage (test image -> nearest train/val frame of the same video):")
    for k, v in leak.items():
        print(f"  {k:15s} {v}")
    print(f"\nwritten {a.manifest}")


def _load(src: Path, manifest: Path, dst: Path) -> tuple[list[Item], dict[str, str]]:
    if dst.exists() and any(dst.iterdir()):
        raise SystemExit(f"{dst} is not empty; delete it first so no stale images stay in a split")
    split_of_video = {v: s for s, vs in json.loads(manifest.read_text(encoding="utf-8"))["splits"].items() for v in vs}
    items = scan(src)
    unknown = sorted({it.video for it in items} - set(split_of_video))
    if unknown:
        raise SystemExit(f"videos missing from {manifest.name}: {unknown}")
    absent = sorted(set(split_of_video) - {it.video for it in items})
    if absent:
        raise SystemExit(f"videos in {manifest.name} but not under {src}: {absent}")
    return items, split_of_video


def _write(dst: Path, its: list[Item]) -> None:
    (dst / "images").mkdir(parents=True, exist_ok=True)
    (dst / "labels").mkdir(parents=True, exist_ok=True)
    for it in its:
        _link_or_copy(it.image, dst / "images" / it.image.name)
        _link_or_copy(it.label, dst / "labels" / it.label.name)


def build(src: Path, manifest: Path, dst: Path) -> Counter:
    items, split_of_video = _load(src, manifest, dst)
    for s in SPLITS:
        _write(dst / s, [it for it in items if split_of_video[it.video] == s])
    counts = Counter(split_of_video[it.video] for it in items)
    print("images per split:", {s: counts[s] for s in SPLITS})
    return counts


def paired(src: Path, manifest: Path, dst: Path, seed: int = 0) -> dict:
    """The same test images under two training sets of equal size: one has seen the test videos, one has not.

    The test videos are the manifest's test split. Their frames, in frame order, alternate between the
    shared test set (even positions) and a leak pool (odd positions: one sampling step from a test
    frame, as in BadODD's official split). clean/train is the manifest's train split; leaky/train swaps
    as many randomly chosen clean/train images for the leak pool. Both keep the manifest's val split,
    so model selection never sees the test videos. Any score difference is the effect of the leak.
    """
    items, split_of_video = _load(src, manifest, dst)
    test_videos = defaultdict(list)
    for it in items:
        if split_of_video[it.video] == "test":
            test_videos[it.video].append(it)
    test, leak = [], []
    for v in sorted(test_videos):
        frames = sorted(test_videos[v], key=lambda it: it.frame)
        test += frames[0::2]
        leak += frames[1::2]
    train = sorted((it for it in items if split_of_video[it.video] == "train"), key=lambda it: it.stem)
    val = sorted((it for it in items if split_of_video[it.video] == "val"), key=lambda it: it.stem)
    drop = {it.stem for it in random.Random(seed).sample(train, len(leak))}
    layouts = {"clean": {"train": train, "val": val, "test": test},
               "leaky": {"train": [it for it in train if it.stem not in drop] + leak, "val": val, "test": test}}
    for proto, splits in layouts.items():
        for s, its in splits.items():
            _write(dst / proto / s, its)

    def gaps(splits):
        lab = {it.stem: s for s, its in splits.items() for it in its}
        return frame_gaps([it for its in splits.values() for it in its], lambda it: lab[it.stem])

    info = {"manifest": manifest.name, "seed": seed, "created": date.today().isoformat(),
            "about": paired.__doc__.split("\n\n")[1].replace("\n    ", " ").strip(),
            "images": {p: {s: len(its) for s, its in sp.items()} for p, sp in layouts.items()},
            "leak_pool_images": len(leak),
            "test_images_per_video": {v: len(f[0::2]) for v, f in sorted(test_videos.items())},
            "leakage": {p: gaps(sp) for p, sp in layouts.items()}}
    (dst / "paired.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print("images:", info["images"])
    for p, g in info["leakage"].items():
        print(f"  {p}: {g}")
    return info


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="find a video-level assignment and write the manifest")
    s.add_argument("--src", type=Path, required=True, help="converted BadODD with train/val/test folders")
    s.add_argument("--manifest", type=Path, required=True)
    s.add_argument("--trials", type=int, default=20000)
    s.add_argument("--seed", type=int, default=0)
    b = sub.add_parser("build", help="link images into split folders as the manifest says")
    b.add_argument("--src", type=Path, required=True)
    b.add_argument("--manifest", type=Path, required=True)
    b.add_argument("--dst", type=Path, required=True)
    p = sub.add_parser("paired", help="leaky/ and clean/ data roots that share one test set (see paired())")
    p.add_argument("--src", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--dst", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd == "search":
        cmd_search(a)
    elif a.cmd == "build":
        build(a.src, a.manifest, a.dst)
    else:
        paired(a.src, a.manifest, a.dst, a.seed)


if __name__ == "__main__":
    main()
