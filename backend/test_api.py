"""API smoke test with the ML pipeline stubbed out.  cd backend && python -m pytest -q"""
import importlib
import json
import sys
import time
from pathlib import Path


def test_upload_process_events_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("ROADWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("ROADWATCH_NEWS", "0")
    sys.path.insert(0, str(Path(__file__).parent))
    app_mod = importlib.import_module("app")
    importlib.reload(app_mod)

    def fake_run_video(path, out_dir, hints, **kw):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "annotated.mp4").write_bytes(b"\0" * 100)
        (out_dir / "events.json").write_text(json.dumps({  # the real pipeline writes this report
            "notes": ["not enough traffic to judge direction"],
            "note_parts": [{"k": "ww_cannot_judge", "en": "not enough traffic to judge direction"}]}))
        assert hints["camera_type"] == "footbridge" and hints["camera_along_road"] is True
        return {"duration_s": 60, "camera_motion": "static", "model_version": "fake", "rules_version": "ev-test",
                "congestion": {"avg": 42}, "summary": {"wrong_way": {"events": 1}},
                "events": [{"type": "wrong_way", "vehicle_class": "motorcycle", "track": 3, "start": 10.0,
                            "end": 14.0, "raw_score": 0.8, "confidence": 0.8, "severity": "high",
                            "reason": "moved 4 s opposite to traffic (170°)", "details": {"shown": True}},
                           {"type": "wrong_way", "track": 4, "start": 20.0, "end": 22.0, "raw_score": 0.3,
                            "confidence": 0.3, "reason": "x", "details": {"shown": False}}]}

    import roadwatch.pipeline
    monkeypatch.setattr(roadwatch.pipeline, "run_video", fake_run_video)
    monkeypatch.setattr(app_mod, "_get_detector", lambda: None)

    from fastapi.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.post("/api/videos", files={"file": ("clip.mp4", b"fakevideo", "video/mp4")},
               data={"hints": json.dumps({"camera_along_road": True}), "camera_type": "footbridge"})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    for _ in range(50):
        if c.get(f"/api/videos/{vid}").json()["status"] == "done":
            break
        time.sleep(0.1)
    v = c.get(f"/api/videos/{vid}").json()
    assert v["status"] == "done" and v["congestion_avg"] == 42
    assert v["notes"] == [{"k": "ww_cannot_judge", "en": "not enough traffic to judge direction"}]
    evs = c.get(f"/api/videos/{vid}/events").json()["events"]
    assert len(evs) == 1                                       # uncertain one hidden
    assert len(c.get(f"/api/videos/{vid}/events?include_uncertain=1").json()["events"]) == 2
    assert c.post(f"/api/events/{evs[0]['id']}/feedback", json={"verdict": "correct"}).json()["ok"]
    assert c.post(f"/api/events/{evs[0]['id']}/feedback", json={"verdict": "maybe"}).status_code == 400
    assert c.get(f"/api/videos/{vid}/annotated").status_code == 200
    assert c.post("/api/videos", files={"file": ("a.mp4", b"x")}, data={"hints": "[1]"}).status_code == 400


def test_chunked_resumable_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("ROADWATCH_DATA", str(tmp_path))
    monkeypatch.setenv("ROADWATCH_NEWS", "0")
    sys.path.insert(0, str(Path(__file__).parent))
    app_mod = importlib.import_module("app")
    importlib.reload(app_mod)
    seen = {}

    def fake_run_video(path, out_dir, hints, **kw):
        seen["bytes"] = Path(path).read_bytes()
        seen["hints"] = hints
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "events.json").write_text("{}")
        return {"duration_s": 1, "camera_motion": "static", "model_version": "fake", "rules_version": "t",
                "congestion": {"avg": 0}, "summary": {}, "events": []}

    import roadwatch.pipeline
    monkeypatch.setattr(roadwatch.pipeline, "run_video", fake_run_video)
    monkeypatch.setattr(app_mod, "_get_detector", lambda: None)
    monkeypatch.setattr(app_mod, "CHUNK_BYTES", 10)
    from fastapi.testclient import TestClient
    c = TestClient(app_mod.app)

    data = bytes(range(256)) * 1  # 256 bytes -> 26 chunks of 10
    up = c.post("/api/uploads", json={"size": len(data)}).json()
    uid = up["id"]
    off = 0
    for _ in range(5):  # send a few chunks, then "lose the connection"
        off = c.put(f"/api/uploads/{uid}?offset={off}", content=data[off:off + 10]).json()["offset"]
    # a stale client retries an old offset: server says where it really is
    r = c.put(f"/api/uploads/{uid}?offset=0", content=data[:10])
    assert r.status_code == 409 and r.json()["detail"]["offset"] == 50
    # incomplete upload cannot be registered
    assert c.post("/api/videos", json={"upload_id": uid}).status_code == 409
    off = c.get(f"/api/uploads/{uid}").json()["offset"]  # resume
    while off < len(data):
        off = c.put(f"/api/uploads/{uid}?offset={off}", content=data[off:off + 10]).json()["offset"]
    assert c.put(f"/api/uploads/{uid}?offset={off}", content=b"x").status_code == 413  # past the end
    r = c.post("/api/videos", json={"upload_id": uid, "camera_type": "roadside", "hints": {"oneway": True}})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    for _ in range(50):
        if c.get(f"/api/videos/{vid}").json()["status"] == "done":
            break
        time.sleep(0.1)
    assert seen["bytes"] == data and seen["hints"]["camera_type"] == "roadside" and seen["hints"]["oneway"]
    assert c.get(f"/api/videos/{vid}/events.json").status_code == 200
    assert c.post("/api/videos", json={"upload_id": uid}).status_code == 404       # consumed
    assert c.post("/api/videos", json={"upload_id": "../../etc"}).status_code == 404
    assert c.post("/api/uploads", json={"size": 300 * 1024 * 1024}).status_code == 413
    assert c.post("/api/videos", json={"upload_id": uid, "camera_type": "drone"}).status_code in (400, 404)
