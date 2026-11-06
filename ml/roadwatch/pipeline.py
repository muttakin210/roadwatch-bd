"""End-to-end: run_video(path, hints) → blurred annotated video + events.json (PLAN §3, two passes).

PASS 1: probe → normalise → detect + camera motion → track → stitch → road → flow
PASS 2: scene state → event rules → merge → calibrate → blur → render

    python -m roadwatch.pipeline clip.mp4 --out out/ --detector hf [--hints hints.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import __version__
from .camera_motion import MotionEstimator, stabilise, warp_boxes
from .config import load_config
from .events import analyse
from .events.calibrate import load_calibrators
from .preprocess import have_ffmpeg, iter_frames, normalise, probe
from .privacy import Blurrer
from .render import Renderer
from .road import RoadModel
from .track import build_tracks, make_tracker, stitch_tracks
from .types import Detection, Hints, note

log = logging.getLogger("roadwatch")
ML_DIR = Path(__file__).resolve().parents[1]


def run_video(path: str | Path, out_dir: str | Path, hints: Hints | dict | None = None, **kw) -> dict:
    """See _run_video. The normalised copy (unblurred pixels) lives in a temp folder that is always removed."""
    tmp = Path(tempfile.mkdtemp(prefix="roadwatch_"))
    try:
        return _run_video(path, out_dir, hints, tmp=tmp, **kw)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_atomic(path: Path, text: str) -> None:
    part = path.with_name(path.name + ".part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


def _run_video(path: str | Path, out_dir: str | Path, hints: Hints | dict | None = None, *, tmp: Path,
               detector=None, detector_backend: str = "hf", detector_kw: dict | None = None,
               cfg=None, tracker: str = "auto", calibration: str | Path | None = ML_DIR / "models" / "calibration.json",
               yunet_model: str | Path | None = ML_DIR / "models" / "face_detection_yunet_2023mar.onnx",
               render: bool = True, progress: Callable[[str, float], None] | None = None,
               allow_no_ffmpeg: bool = False, reuse_detections: bool = True) -> dict:
    t_start = time.time()
    cfg = cfg or load_config()
    hints = hints if isinstance(hints, Hints) else Hints.from_dict(hints)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda step, frac: log.info("%s %.0f%%", step, frac * 100))
    fps = int(cfg.analysis_fps)
    notes = []

    # ---- probe + normalise -------------------------------------------------------
    say("checking video", 0.0)
    info = None
    src = Path(path)
    if have_ffmpeg():
        info = probe(src)
        norm = tmp / "norm.mp4"
        normalise(src, norm, fps=fps, trim=hints.trim)   # trim: the browser couldn't cut the clip itself
        src = norm
    elif not allow_no_ffmpeg:
        raise RuntimeError("ffmpeg not found. Install it, or pass allow_no_ffmpeg=True for local development.")
    else:
        log.warning("ffmpeg missing: no validation, rotation or VFR handling (development only)")
        if hints.trim:
            notes.append(note("trim_ignored", "the chosen trim couldn't be applied; the clip was analysed from its start"))

    # ---- PASS 1a: detect + camera motion (cached: re-running rules needs no detector) ----
    st = Path(path).stat()
    det_name = getattr(detector, "name", None) or f"{detector_backend}:{json.dumps(detector_kw or {}, sort_keys=True)}"
    trim_key = list(hints.trim) if hints.trim and have_ffmpeg() else None
    cache_key = [str(Path(path).resolve()), st.st_size, int(st.st_mtime), det_name, fps, trim_key]
    cache_file = out_dir / "pass1_cache.pkl"
    cached = None
    if reuse_detections and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
            if cached.get("key") != cache_key or "motion_state" not in cached:
                cached = None
        except Exception:
            cached = None
    if cached:
        log.info("reusing cached detections from %s", cache_file)
        dets_per_frame, size = cached["dets"], cached["size"]
        mres = MotionEstimator.from_state(cached["motion_state"]).result()
        model_version = cached["model_version"]
    else:
        if detector is None:
            from .detect import make_detector
            detector = make_detector(detector_backend, **(detector_kw or {}))
        model_version = getattr(detector, "name", "custom") + f"-{__version__}"
        dets_per_frame = []
        motion = MotionEstimator()
        size = None
        n_est = max(1, int((info.duration if info else 300) * fps))
        for i, t, frame in iter_frames(src, fps=fps):
            size = (frame.shape[1], frame.shape[0])
            dets = detector(frame, i, t)
            dets_per_frame.append(dets)
            motion.update(frame, np.array([d.box for d in dets]).reshape(-1, 4))
            if i % 15 == 0:
                say("detecting", min(i / n_est, 1.0))
        if size is None:
            raise RuntimeError("no frames decoded")
        mres = motion.result()
        with open(cache_file, "wb") as f:
            pickle.dump({"key": cache_key, "dets": dets_per_frame, "size": size, "motion_state": motion.state(),
                         "model_version": model_version}, f)
    duration = len(dets_per_frame) / fps
    log.info("camera motion: %s (median %.2f px/frame)", mres.cls, mres.median_px)

    # ---- PASS 1b: track in (stabilised) reference coordinates --------------------
    say("analysing", 0.0)
    trk = make_tracker(tracker, fps)
    assoc = []
    for i, dets in enumerate(dets_per_frame):
        if mres.cls == "shaky" and dets:
            wb = warp_boxes(np.array([d.box for d in dets]), mres.transforms[i])
            dets = [Detection(d.frame, d.t, b, d.cls, d.conf) for d, b in zip(dets, wb)]
        assoc += trk.update(dets)
    tracks = stitch_tracks(build_tracks(assoc), cfg)
    for tr in tracks:
        tr.compute_kinematics(cfg)

    W, H = size
    if hints.road_edges and hints.road_edges.get("left") and hints.road_edges.get("right"):
        road = RoadModel.from_edges(W, H, hints.road_edges["left"], hints.road_edges["right"],
                                    hints.road_edges.get("divider"))
    else:
        road = RoadModel.from_heatmap(tracks, W, H)
        if not np.any(~np.isnan(road.left_kerb)):
            notes.append(note("no_road_edges", "road edges not found, so the whole frame was treated as road"))
            road = RoadModel.from_edges(W, H, [(0, 0), (0, H - 1)], [(W - 1, 0), (W - 1, H - 1)], source="full_frame")

    # ---- PASS 2: events --------------------------------------------------------------
    res = analyse(tracks, road, duration, hints, cfg, load_calibrators(calibration), camera_motion=mres.cls)
    events = res.pop("_events")
    notes += res["note_parts"]
    res["camera_motion_reliable"] = mres.reliable
    if not mres.reliable:
        notes.append(note("cam_low_texture", "too little background texture to check camera motion; analysed as static"))
    elif mres.cls == "moving":
        notes.append(note("cam_moving", "the camera moved (pan, tilt or a moving vehicle): only congestion is fully "
                                        "supported; hold the camera still for wrong-way and bus-stop checks"))
    if info and info.orientation == "portrait":
        notes.append(note("portrait", "portrait video shows a narrow strip of road; landscape gives better results"))
    res["note_parts"] = notes
    res["notes"] = [n["en"] for n in notes]
    res.update({
        "model_version": model_version,
        "orientation": info.orientation if info else None,
        "duration_s": round(duration, 2),
        "frame_size": [W, H],
        "road_source": road.source,
    })

    # ---- render (blurred) -------------------------------------------------------------
    if render:
        say("rendering", 0.0)
        blur = Blurrer(yunet_model)
        if not blur.faces_enabled:
            n = note("face_blur_off", "the face-detection model is missing: only the heads of detected people were blurred")
            res["note_parts"].append(n)
            res["notes"].append(n["en"])
        raw_render = out_dir / "annotated_mp4v.mp4"
        rnd = Renderer(raw_render, fps, size, tracks, events,
                       res["congestion"]["timeline"], cfg.window_s)
        for i, t, frame in iter_frames(src, fps=fps):
            if i >= len(dets_per_frame):
                break
            dets = dets_per_frame[i]
            frame = blur(frame, dets)                    # blur first, on original pixel coords
            if mres.cls == "shaky":
                frame = stabilise(frame, mres.transforms[i])
            rnd.write(frame, t)
            if i % 30 == 0:
                say("rendering", i / len(dets_per_frame))
        rnd.close()
        final = out_dir / "annotated.mp4"
        if have_ffmpeg():
            # OpenCV writes MPEG-4 Part 2, which browsers can't play: re-encode to H.264 + faststart.
            # Encode next to it and swap in at the end, so a re-analysis never serves a half-written file.
            encoded = out_dir / "annotated.part.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_render), "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(encoded)], check=True, timeout=900)
            os.replace(encoded, final)
            raw_render.unlink()
        else:
            log.warning("ffmpeg missing: annotated.mp4 stays MPEG-4 Part 2 and won't play in browsers")
            raw_render.replace(final)
        res["annotated"] = "annotated.mp4"

    res["processing_s"] = round(time.time() - t_start, 1)
    _write_atomic(out_dir / "events.json", json.dumps(res, indent=1, default=float))
    say("done", 1.0)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run RoadWatch on one video: writes annotated.mp4 + events.json")
    ap.add_argument("video")
    ap.add_argument("--out", default="out")
    ap.add_argument("--hints", help="JSON file with arrows / road_edges / camera_along_road / oneway")
    ap.add_argument("--detector", default="hf", choices=["hf", "rfdetr", "ultralytics"])
    ap.add_argument("--weights", help="detector weights / HF model id")
    ap.add_argument("--tracker", default="auto", choices=["auto", "bytetrack", "iou"])
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--allow-no-ffmpeg", action="store_true", help="development only")
    ap.add_argument("--fresh", action="store_true", help="ignore cached detections in --out")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    hints = json.load(open(a.hints, encoding="utf-8")) if a.hints else None
    kw = {}
    if a.weights:
        kw = {"model_id": a.weights} if a.detector == "hf" else {"weights": a.weights}
    res = run_video(a.video, a.out, hints, detector_backend=a.detector, detector_kw=kw, tracker=a.tracker,
                    render=not a.no_render, allow_no_ffmpeg=a.allow_no_ffmpeg,
                    reuse_detections=not a.fresh)
    print(json.dumps(res["summary"], indent=1))
    for n in res["notes"]:
        print("note:", n)


if __name__ == "__main__":
    main()
