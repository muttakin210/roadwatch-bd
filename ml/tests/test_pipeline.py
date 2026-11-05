"""End-to-end smoke test: synthetic video → run_video → events.json + annotated.mp4.
Uses a fake detector that returns ground-truth boxes, so no model weights are needed."""
import json
import subprocess

import cv2
import numpy as np

import synth as S
from roadwatch.pipeline import run_video
from roadwatch.preprocess import have_ffmpeg
from roadwatch.types import Detection


class FakeDetector:
    name = "fake"

    def __init__(self, tracks):
        self.tracks = tracks

    def __call__(self, frame, i, t):
        out = []
        for tr in self.tracks:
            j = np.where(np.abs(tr.t - t) < 0.5 / S.FPS)[0]
            if len(j):
                out.append(Detection(i, t, tr.boxes[j[0]].copy(), tr.cls, 0.9))
        return out


def _write_video(path, tracks, duration):
    rng = np.random.default_rng(0)
    small = rng.integers(30, 150, (S.H // 8, S.W // 8, 3), dtype=np.uint8)  # blocky texture ORB can lock on
    bg = cv2.resize(small, (S.W, S.H), interpolation=cv2.INTER_NEAREST)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), S.FPS, (S.W, S.H))
    for i in range(int(duration * S.FPS)):
        t = i / S.FPS
        img = bg.copy()
        for tr in tracks:
            j = np.where(np.abs(tr.t - t) < 0.5 / S.FPS)[0]
            if len(j):
                x1, y1, x2, y2 = tr.boxes[j[0]].astype(int)
                cv2.rectangle(img, (x1, y1), (x2, y2), (200, 200, 200), -1)
        vw.write(img)
    vw.release()
    if have_ffmpeg():
        # OpenCV writes mp4v, which the upload allow-list rejects; real uploads are h264/h265/vp9
        tmp = path.with_name("h264_" + path.name)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        str(tmp)], check=True)
        tmp.replace(path)


def test_run_video_end_to_end(tmp_path):
    dur = 40
    bike = S.drive("motorcycle", 420, 15, 8, up=False)
    tracks = S.background(dur) + [bike]
    vid = tmp_path / "clip.mp4"
    _write_video(vid, tracks, dur)
    hints = {"road_edges": {"left": [[S.LEFT_KERB, 0], [S.LEFT_KERB, S.H - 1]],
                            "right": [[S.RIGHT_KERB, 0], [S.RIGHT_KERB, S.H - 1]]}}
    res = run_video(vid, tmp_path / "out", hints, detector=FakeDetector(tracks), tracker="iou",
                    allow_no_ffmpeg=True, calibration=None, yunet_model=None)
    assert res["camera_motion"] == "static" and res["camera_motion_reliable"]
    saved = json.loads((tmp_path / "out" / "events.json").read_text())
    ww = [e for e in saved["events"] if e["type"] == "wrong_way"]
    assert len(ww) == 1 and ww[0]["vehicle_class"] == "motorcycle"
    assert (tmp_path / "out" / "annotated.mp4").stat().st_size > 10_000


def test_mp4v_upload_is_rejected(tmp_path):
    """Allow-list check works on the file's real codec, not its extension."""
    import pytest
    from roadwatch.preprocess import VideoRejected, probe
    if not have_ffmpeg():
        pytest.skip("ffmpeg not installed")
    vid = tmp_path / "clip.mp4"
    vw = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 15, (320, 240))
    for _ in range(15):
        vw.write(np.zeros((240, 320, 3), np.uint8))
    vw.release()
    with pytest.raises(VideoRejected, match="codec"):
        probe(vid)
