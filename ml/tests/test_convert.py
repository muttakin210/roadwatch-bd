"""convert_datasets.py: BadODD YOLO ids → unified classes (mapping checked by eye on 2026-11-05)."""
import importlib.util
from pathlib import Path

from roadwatch.types import CLASS_ID

_spec = importlib.util.spec_from_file_location("convert_datasets", Path(__file__).parents[1] / "scripts" / "convert_datasets.py")
cd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cd)


def test_badodd_ids_map_to_unified_classes(tmp_path):
    src = tmp_path / "src" / "train"
    (src / "images").mkdir(parents=True); (src / "labels").mkdir()
    (src / "images" / "a.jpg").write_bytes(b"\xff\xd8fake")
    # one box per BadODD id 0..12, plus an out-of-frame box that must be clipped
    rows = [f"{i} 0.5 0.5 0.1 0.1" for i in range(13)] + ["3 1.2 0.5 0.1 0.1"]
    (src / "labels" / "a.txt").write_text("\n".join(rows))
    stats = cd.convert_yolo(tmp_path / "src", tmp_path / "dst", cd.MAPS["badodd"], cd.BADODD_NAMES)

    out = (tmp_path / "dst" / "train" / "labels" / "a.txt").read_text().splitlines()
    got = [int(r.split()[0]) for r in out]
    want = ["cng_autorickshaw", "bicycle", "bus", "car", "other", "other", "motorcycle", "person",
            "ambulance", "rickshaw", "truck", "car"]  # train(10) and wheelchair(12) dropped
    assert got == [CLASS_ID[c] for c in want]
    assert float(out[-1].split()[1]) == 1.0  # clipped into the frame
    assert stats["other"] == 2 and "train" not in stats
    assert (tmp_path / "dst" / "train" / "images" / "a.jpg").exists()
