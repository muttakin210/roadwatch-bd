"""make_group_split.py: whole videos per split, sizes matched, the manifest rebuilds the same split."""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "make_group_split", Path(__file__).parents[1] / "scripts" / "make_group_split.py")
gs = importlib.util.module_from_spec(_spec)
sys.modules["make_group_split"] = gs  # @dataclass looks its module up while the file loads
_spec.loader.exec_module(gs)


def test_video_of_splits_off_the_trailing_frame_number():
    assert gs.video_of("chittagong_bohoddarhat1_10384") == ("chittagong_bohoddarhat1", 10384)
    assert gs.video_of("dhaka5_khilkhet_0") == ("dhaka5_khilkhet", 0)
    with pytest.raises(ValueError):
        gs.video_of("no_frame_number")


def _table(sizes):
    return {f"v{i}" + ("_night" if i % 5 == 0 else ""): {"images": n, "boxes": Counter(person=n, car=n // 2 + 1)}
            for i, n in enumerate(sizes)}


def test_search_keeps_videos_whole_matches_sizes_and_is_deterministic():
    table = _table([30, 25, 20, 18, 15, 12, 10, 10, 8, 6, 5, 5, 4, 3, 3, 2])
    target = {"train": 0.6, "val": 0.2, "test": 0.2}
    assign, c = gs.search(table, target, trials=300, seed=1)
    assert set(assign) == set(table) and set(assign.values()) == set(gs.SPLITS)
    summ = gs.summarise(assign, table)
    total = sum(r["images"] for r in table.values())
    for s, t in target.items():
        assert abs(summ[s]["images"] / total - t) < 0.05
    assert gs.search(table, target, trials=300, seed=1) == (assign, c)


def _add(src, split, stem, rows):
    (src / split / "images").mkdir(parents=True, exist_ok=True)
    (src / split / "labels").mkdir(parents=True, exist_ok=True)
    (src / split / "images" / f"{stem}.jpg").write_bytes(b"\xff\xd8fake")
    (src / split / "labels" / f"{stem}.txt").write_text("\n".join(rows))


def test_build_moves_every_frame_of_a_video_to_its_manifest_split(tmp_path):
    src = tmp_path / "src"
    # video "a" is spread over all three official splits, as every BadODD video is
    _add(src, "train", "a_0", ["0 0.5 0.5 0.1 0.1"])
    _add(src, "val", "a_59", ["8 0.5 0.5 0.1 0.1"])
    _add(src, "test", "a_118", [])
    _add(src, "train", "b_0", ["0 0.5 0.5 0.1 0.1"])
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"splits": {"train": ["b"], "val": [], "test": ["a"]}}))

    counts = gs.build(src, man, tmp_path / "dst")
    assert sorted(p.name for p in (tmp_path / "dst" / "test" / "images").iterdir()) == ["a_0.jpg", "a_118.jpg", "a_59.jpg"]
    assert (tmp_path / "dst" / "test" / "labels" / "a_59.txt").read_text() == "8 0.5 0.5 0.1 0.1"
    assert counts == {"train": 1, "test": 3}

    with pytest.raises(SystemExit):  # never mixes a new split into an old output folder
        gs.build(src, man, tmp_path / "dst")
    _add(src, "train", "c_0", [])
    with pytest.raises(SystemExit):  # a video the manifest does not know is an error, not a silent drop
        gs.build(src, man, tmp_path / "dst2")


def test_paired_shares_the_test_set_and_swaps_only_the_leak_frames(tmp_path):
    src = tmp_path / "src"
    for f in (0, 59, 118, 177):       # test video, spread over the official splits
        _add(src, "test" if f % 2 else "train", f"a_{f}", ["0 0.5 0.5 0.1 0.1"])
    for f in range(4):                 # training video
        _add(src, "train", f"b_{f}", ["8 0.5 0.5 0.1 0.1"])
    _add(src, "val", "c_0", [])        # validation video
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"splits": {"train": ["b"], "val": ["c"], "test": ["a"]}}))

    info = gs.paired(src, man, tmp_path / "dst", seed=0)

    def names(proto, split):
        return sorted(p.name for p in (tmp_path / "dst" / proto / split / "images").iterdir())

    assert names("clean", "test") == names("leaky", "test") == ["a_0.jpg", "a_118.jpg"]
    assert names("clean", "train") == ["b_0.jpg", "b_1.jpg", "b_2.jpg", "b_3.jpg"]
    leaky_train = names("leaky", "train")
    assert len(leaky_train) == 4 and {"a_59.jpg", "a_177.jpg"} <= set(leaky_train)
    assert names("clean", "val") == names("leaky", "val") == ["c_0.jpg"]
    assert info["leakage"]["leaky"]["median_gap_frames"] == 59
    assert info["leakage"]["clean"]["with_same_video_frame"] == 0


def test_frame_gaps_measure_the_official_leak_and_none_for_the_video_split():
    def it(video, frame, split):
        return gs.Item(f"{video}_{frame}", split, Path(), Path(), video, frame, Counter())

    items = [it("a", 0, "train"), it("a", 59, "test"), it("a", 118, "train"), it("a", 177, "val"), it("b", 5, "test")]
    off = gs.frame_gaps(items, lambda x: x.official)
    assert off["test_images"] == 2 and off["with_same_video_frame"] == 1 and off["median_gap_frames"] == 59
    vid = gs.frame_gaps(items, lambda x: {"a": "train", "b": "test"}[x.video])
    assert vid["test_images"] == 1 and vid["with_same_video_frame"] == 0 and vid["median_gap_frames"] is None
