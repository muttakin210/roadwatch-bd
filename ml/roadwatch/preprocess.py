"""Probe and normalise uploads (PLAN §5.1, §8.7).

ffprobe validates the file by its real content (not its name); ffmpeg applies rotation,
converts VFR -> CFR H.264, caps the long side at 1280 px, resamples to ~15 fps, caps at 5 min.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ALLOWED_CONTAINERS = {"mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"}
ALLOWED_CODECS = {"h264", "hevc", "vp9"}
MAX_DURATION_S = 300
MAX_BYTES = 200 * 1024 * 1024


class VideoRejected(ValueError):
    pass


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    codec: str
    rotation: int
    creation_time: str | None
    location: str | None   # ISO 6709 string if the phone wrote one (usually missing on forwards)

    @property
    def orientation(self) -> str:
        w, h = (self.height, self.width) if self.rotation in (90, 270) else (self.width, self.height)
        return "portrait" if h > w else "landscape"


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: str | Path) -> VideoInfo:
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise VideoRejected("file larger than 200 MB")
    if not have_ffmpeg():
        raise RuntimeError("ffprobe/ffmpeg not found on PATH — install ffmpeg (https://ffmpeg.org)")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise VideoRejected("not a readable video")
    meta = json.loads(out.stdout)
    fmt = meta.get("format", {})
    if fmt.get("format_name") not in ALLOWED_CONTAINERS:
        raise VideoRejected(f"container not allowed: {fmt.get('format_name')}")
    vs = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
    if not vs:
        raise VideoRejected("no video stream")
    v = vs[0]
    if v.get("codec_name") not in ALLOWED_CODECS:
        raise VideoRejected(f"codec not allowed: {v.get('codec_name')}")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"]) % 360
    rot = int(v.get("tags", {}).get("rotate", rot)) % 360
    tags = fmt.get("tags", {})
    return VideoInfo(
        duration=float(fmt.get("duration", 0)), width=int(v["width"]), height=int(v["height"]),
        fps=fps, codec=v["codec_name"], rotation=rot,
        creation_time=tags.get("creation_time"),
        location=tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709"),
    )


def normalise(src: str | Path, dst: str | Path, fps: int = 15, long_side: int = 1280,
              max_s: int = MAX_DURATION_S, trim: tuple[float, float] | None = None) -> Path:
    """ffmpeg auto-applies the rotation flag; output is CFR H.264 without audio."""
    dst = Path(dst)
    scale = f"scale='if(gt(iw,ih),min({long_side},iw),-2)':'if(gt(iw,ih),-2,min({long_side},ih))'"
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if trim:
        cmd += ["-ss", str(trim[0]), "-to", str(trim[1])]
    cmd += ["-i", str(src), "-t", str(max_s), "-an",
            "-vf", f"{scale},fps={fps}", "-fps_mode", "cfr",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(dst)]
    subprocess.run(cmd, check=True, timeout=600)
    return dst


def iter_frames(path: str | Path, fps: int = 15, long_side: int = 1280, max_s: int = MAX_DURATION_S):
    """Yield (frame_idx, t, BGR frame). Works on normalised files; also resamples/resizes itself
    so development runs work without ffmpeg (no rotation / VFR handling in that case)."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoRejected("cannot open video")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or fps
    next_t, i, out_i = 0.0, 0, 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t_src = i / src_fps
            i += 1
            if t_src + 1e-6 < next_t:
                continue
            if t_src > max_s:
                break
            h, w = frame.shape[:2]
            s = long_side / max(h, w)
            if s < 1:
                frame = cv2.resize(frame, (int(w * s) // 2 * 2, int(h * s) // 2 * 2), interpolation=cv2.INTER_AREA)
            yield out_i, out_i / fps, frame
            out_i += 1
            next_t = out_i / fps
    finally:
        cap.release()
