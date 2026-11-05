import numpy as np

import synth as S
from roadwatch.events.calibrate import expected_calibration_error, fit_isotonic, fit_platt
from roadwatch.events.merge import merge, summarise
from roadwatch.road import RoadModel
from roadwatch.track import angle_diff, circ_median_deg
from roadwatch.types import Event


def test_angle_helpers():
    assert angle_diff(170, -170) == 20
    assert abs(circ_median_deg(np.array([179, -179, 178, 0])) - 179) < 2


def test_kinematics_speed_and_stop():
    c = S.cfg()
    tr = S.stop_and_go("car", 420, 0, y_stop=400, stop_s=10, mps=8).compute_kinematics(c)
    moving = tr.speed_mps[~tr.stopped]
    assert 6 < np.median(moving) < 10           # approx m/s from class size
    segs = tr.stopped_segments(5)
    assert len(segs) == 1 and 9 <= tr.t[segs[0][1]] - tr.t[segs[0][0]] <= 11
    assert abs(tr.approach_heading(segs[0][0]) - (-90)) < 10


def test_merge_same_track_small_gap():
    ev = [Event("wrong_way", 10, 12, 0.6, "a", track=5), Event("wrong_way", 13.5, 16, 0.7, "b", track=5),
          Event("wrong_way", 30, 33, 0.7, "c", track=5), Event("wrong_way", 11, 14, 0.7, "d", track=6)]
    m = merge(ev, 3.0)
    assert len(m) == 3
    assert summarise(m)["wrong_way"]["distinct_vehicles"] == 2


def test_platt_and_isotonic_calibration():
    rng = np.random.default_rng(1)
    s = rng.uniform(0, 1, 2000)
    y = rng.uniform(0, 1, 2000) < s ** 2       # true P(correct) = s^2
    for cal in (fit_platt(s, y), fit_isotonic(s, y)):
        p = cal(s)
        assert expected_calibration_error(p, y) < 0.06
        assert np.all(np.diff(cal(np.linspace(0, 1, 50))) >= -1e-9)   # monotone
    assert expected_calibration_error(s, y) > 0.1  # raw scores are not calibrated


def test_road_from_heatmap_finds_kerbs():
    c = S.cfg()
    tracks = S.prepare(S.background(120, lanes_up=[230, 420, 600], lanes_down=[680, 860, 1050]), c)
    r = RoadModel.from_heatmap(tracks, S.W, S.H)
    y = 400
    assert abs(r.left_kerb[y] - (230 - 20)) < 15
    assert abs(r.right_kerb[y] - (1050 + 20)) < 15


def test_kerb_side_follows_left_hand_traffic():
    r = S.road()
    box = np.array([700, 300, 770, 450])         # right carriageway
    # moving down (towards camera): kerb side is the image right
    assert r.kerb_gap_px(box, 90) == S.RIGHT_KERB - 770
    # moving up: kerb side is the image left
    assert r.kerb_gap_px(box, -90) == 700 - S.LEFT_KERB


def test_camera_motion_classes():
    import cv2
    from roadwatch.camera_motion import MotionEstimator
    rng = np.random.default_rng(0)
    bg = cv2.resize(rng.integers(30, 150, (100, 160, 3), dtype=np.uint8), (640, 400), interpolation=cv2.INTER_NEAREST)

    def classify(offsets):
        m = MotionEstimator()
        for dx, dy in offsets:
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            m.update(cv2.warpAffine(bg, M, (640, 400), borderMode=cv2.BORDER_REFLECT))
        return m.result()

    assert classify([(0, 0)] * 15).cls == "static"
    jitter = rng.uniform(-4, 4, (15, 2))
    assert classify(jitter).cls == "shaky"
    assert classify([(8 * k, 0) for k in range(15)]).cls == "moving"
    # slow steady tilt (~3 px/frame, under the per-frame limit) still wanders off the first view
    slow = classify([(0, 3 * k) for k in range(30)])
    assert slow.cls == "moving"
    assert all(np.allclose(T, np.eye(3)) for T in slow.transforms)  # never warped to frame 0
