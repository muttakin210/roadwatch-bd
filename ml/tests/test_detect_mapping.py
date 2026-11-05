"""COCO label names differ between detector backends; none may be dropped by the mapping."""
import numpy as np

from roadwatch.detect import COCO_TO_UNIFIED, _mk


def test_motorbike_and_motorcycle_both_map_to_motorcycle():
    # HF RT-DETR (PekingU/rtdetr_r18vd) says "motorbike"; Ultralytics / RF-DETR say "motorcycle".
    assert COCO_TO_UNIFIED["motorbike"] == "motorcycle"
    assert COCO_TO_UNIFIED["motorcycle"] == "motorcycle"


def test_rtdetr_motorbike_detection_is_kept():
    names = ["person", "bicycle", "car", "motorbike", "aeroplane", "bus"]  # RT-DETR id2label order
    dets = _mk(boxes=[[0, 0, 10, 10]], scores=[0.9], labels=[3], names=names,
               frame_idx=0, t=0.0, conf=0.3, mapping=COCO_TO_UNIFIED)
    assert [d.cls for d in dets] == ["motorcycle"]
    assert np.allclose(dets[0].box, [0, 0, 10, 10])
