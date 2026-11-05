"""Tests for the AP / matching maths in eval/eval_detector.py (no model, no GPU)."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_spec = importlib.util.spec_from_file_location(
    "eval_detector", Path(__file__).resolve().parents[1] / "eval" / "eval_detector.py")
ed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ed)


def test_perfect_detections_give_ap_one():
    assert ed.average_precision([0.9, 0.8], [1, 1], n_gt=2) == pytest.approx(1.0)


def test_false_positive_ranked_first_halves_ap():
    # recall 1.0 is only reached at precision 0.5
    assert ed.average_precision([0.9, 0.8], [0, 1], n_gt=1) == pytest.approx(0.5)


def test_missed_object_caps_recall():
    assert ed.average_precision([0.9], [1], n_gt=2) == pytest.approx(0.5)


def test_no_detections_is_zero_and_no_gt_is_none():
    assert ed.average_precision([], [], n_gt=3) == 0.0
    assert ed.average_precision([0.9], [0], n_gt=0) is None


def test_weight_two_equals_duplicated_detections():
    conf, tp = [0.9, 0.7, 0.5], [1, 0, 1]
    weighted = ed.average_precision(conf, tp, n_gt=4, weight=[2, 2, 2])
    duplicated = ed.average_precision(conf * 2, tp * 2, n_gt=4)
    assert weighted == pytest.approx(duplicated)


def test_matching_class_iou_and_duplicates():
    gt = [[0, 0, 10, 10], [20, 20, 30, 30]]
    gt_cls = ["rickshaw", "car"]
    dets = [[0, 0, 10, 10],    # right place, wrong class -> FP
            [20, 20, 30, 30],  # car on car -> TP
            [21, 21, 30, 30],  # second car on the same car -> FP (duplicate)
            [50, 50, 60, 60]]  # nothing there -> FP
    tp = ed.match_image(dets, ["motorcycle", "car", "car", "car"], [0.9, 0.8, 0.7, 0.6], gt, gt_cls)
    assert tp.tolist() == [False, True, False, False]


def test_low_iou_is_not_a_match():
    tp = ed.match_image([[0, 0, 10, 10]], ["car"], [0.9], [[6, 0, 16, 10]], ["car"])  # IoU = 4/16 = 0.25
    assert tp.tolist() == [False]


def test_video_of_reads_badodd_file_names():
    assert ed.video_of("chittagong_bohoddarhat1_10384.jpg") == "chittagong_bohoddarhat1"
    assert ed.video_of("frame.jpg") == "frame"


def test_image_bootstrap_draw_is_unchanged():
    # earlier results (image bootstrap, seed 0) must be reproducible after the video option was added
    old = np.bincount(np.random.default_rng(0).integers(0, 5, 5), minlength=5).astype(float)
    assert ed.bootstrap_weights(np.random.default_rng(0), None, 5).tolist() == old.tolist()


def test_video_bootstrap_moves_whole_videos():
    groups = ["a", "a", "b", "c", "c", "c"]
    rng = np.random.default_rng(3)
    for _ in range(20):
        w = ed.bootstrap_weights(rng, groups, len(groups))
        assert w[0] == w[1] and w[3] == w[4] == w[5]   # frames of a video share one weight
        assert w[[0, 2, 3]].sum() == 3                  # three videos drawn per sample


def test_iou_matrix_shapes():
    assert ed.iou_matrix(np.zeros((0, 4)), np.zeros((3, 4))).shape == (0, 3)
    assert ed.iou_matrix(np.array([[0, 0, 2, 2.]]), np.array([[1, 1, 3, 3.]]))[0, 0] == pytest.approx(1 / 7)
