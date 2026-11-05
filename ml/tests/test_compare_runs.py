"""eval/compare_runs.py: paired bootstrap of the difference between two runs on the same images."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(_EVAL))  # compare_runs imports eval_detector from its own folder
_spec = importlib.util.spec_from_file_location("compare_runs", _EVAL / "compare_runs.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)


def _runs(tmp_path, n_videos=3):
    split = tmp_path / "test"
    (split / "labels").mkdir(parents=True)
    good, bad = [], []
    for v in "abc"[:n_videos]:
        for f in (0, 1):
            (split / "labels" / f"{v}_{f}.txt").write_text("8 0.5 0.5 0.2 0.2")  # one car at 40..60 px
            rec = {"image": f"{v}_{f}.jpg", "w": 100, "h": 100, "cls": ["car"], "conf": np.array([0.9])}
            good.append(rec | {"boxes": np.array([[40, 40, 60, 60.]])})
            bad.append(rec | {"boxes": np.array([[0, 0, 10, 10.]])})   # misses the car
    return split, good, bad


def test_better_run_wins_everywhere_and_identical_runs_differ_by_zero(tmp_path):
    split, good, bad = _runs(tmp_path)
    r = cr.compare(good, bad, split, ["car"], ["car"], n_boot=50)
    assert r["diff"] == pytest.approx(1.0) and r["ci95"] == pytest.approx([1.0, 1.0])
    assert r["videos_a_better"] == 3 and r["share_of_draws_a_not_better"] == 0.0
    same = cr.compare(good, good, split, ["car"], ["car"], n_boot=50)
    assert same["diff"] == 0 and same["ci95"] == [0.0, 0.0] and same["videos_a_better"] == 0


def test_runs_on_different_images_are_refused(tmp_path):
    split, good, bad = _runs(tmp_path)
    with pytest.raises(SystemExit):
        cr.compare(good, bad[:-1], split, ["car"], ["car"], n_boot=5)
