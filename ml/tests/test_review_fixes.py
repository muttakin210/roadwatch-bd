"""Regression tests for the 2026-11-06 review fixes (ML side)."""
import numpy as np
import pytest

import synth as S
from roadwatch.events import analyse
from roadwatch.events.congestion import occupancy
from roadwatch.privacy import Blurrer
from roadwatch.types import Detection, Hints

ALONG = Hints(camera_along_road=True)


def _run(tracks, duration, hints, road):
    c = S.cfg()
    S.prepare(tracks, c)
    return analyse(tracks, road, duration, hints, c)


def test_hints_take_only_declared_fields_and_reject_bad_shapes():
    h = Hints.from_dict({"oneway": True, "__class__": 1, "from_dict": 2, "camera_type": "cctv"})
    assert h.oneway is True and h.camera_type == "cctv" and type(h) is Hints
    with pytest.raises(ValueError):
        Hints.from_dict({"arrows": [[1, 2, 3]]})
    with pytest.raises(ValueError):
        Hints.from_dict({"oneway": "yes"})
    assert Hints.from_dict({"trim": [3, 40]}).trim == (3.0, 40.0)


def test_lht_uses_the_centre_line_when_there_is_no_divider():
    """The web app never sends a divider: 'camera along the road' must still work on a two-way road."""
    tracks = ([S.drive("car", 420, 5 * k, 8, up=True) for k in range(3)]
              + [S.drive("car", 860, 5 * k, 8, up=False) for k in range(3)]
              + [S.drive("motorcycle", 420, 30, 8, up=False)])
    e3 = [e for e in _run(tracks, 60, ALONG, S.road(divider=False))["events"] if e["type"] == "wrong_way"]
    assert len(e3) == 1 and e3[0]["vehicle_class"] == "motorcycle" and e3[0]["details"]["direction_source"] == "lht"


def test_centre_line_is_not_used_on_a_one_way_looking_road():
    tracks = ([S.drive("car", 420, 5 * k, 8, up=True) for k in range(3)]
              + [S.drive("car", 860, 5 * k, 8, up=True) for k in range(3)])
    res = _run(tracks, 60, ALONG, S.road(divider=False))
    assert not [e for e in res["events"] if e["type"] == "wrong_way"]


def test_occupancy_is_measured_over_the_rows_traffic_uses_in_the_whole_clip():
    road = S.road()
    boxes = np.array([[300, 640, 340, 700], [420, 640, 460, 700], [540, 640, 580, 700]], float)  # 3 cars side by side
    local = occupancy(boxes, road, 0.6)
    whole = occupancy(boxes, road, 0.6, span=(70, 719))
    assert whole < local / 5 and local > 0.1


def test_without_a_face_model_every_person_head_is_blurred():
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    small = Detection(0, 0.0, np.array([600, 300, 620, 330], float), "person", 0.9)  # 4% of frame height
    b = Blurrer(None)
    assert not b.faces_enabled
    out = b(frame, [small])
    head = (slice(300, 306), slice(600, 620))
    assert not np.array_equal(out[head], frame[head])            # head region was blurred
    assert np.array_equal(out[400:500, 0:100], frame[400:500, 0:100])   # the rest is untouched
