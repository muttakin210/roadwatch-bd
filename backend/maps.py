"""Road situation map: RoadWatch incidents, and the offline map pack for Bangladesh.

Incidents shown publicly:
- traffic jams the AI found in recent uploads (marked as AI estimates: nobody checked them), and
- violations (wrong way, mid-road bus stops, U-turns) only once a reviewer has confirmed them.
Hidden (moderated) videos never appear. Only the video's location and the event are shown, never the uploader.

Offline map: an OpenStreetMap vector extract of Bangladesh (PMTiles) at DATA/maps/bd.pmtiles, made with
`pmtiles extract` (see README, "Offline map pack"). Browsers download it once and keep it, so the map and place
search work without internet. Served with HTTP range support, so online visitors read only the tiles they view.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/map")
_db: Callable[[], sqlite3.Connection] | None = None
_pack: Path | None = None
BD_BBOX = (88.0, 20.55, 92.7, 26.65)   # lng/lat bounds of Bangladesh (with a little margin)
OFFENCES = ("wrong_way", "bus_midroad_stop", "u_turn")


def setup(db: Callable[[], sqlite3.Connection], data_dir: Path) -> None:
    global _db, _pack
    _db, _pack = db, data_dir / "maps" / "bd.pmtiles"


@router.get("/incidents")
def incidents(days: int = 7):
    days = max(1, min(days, 90))
    since = time.time() - days * 86400
    assert _db is not None
    with _db() as c:
        rows = c.execute(
            "SELECT e.id, e.type, e.vehicle_class, e.confidence, e.verified, e.start_s, v.id AS video_id, "
            "v.lat, v.lng, v.created_at, v.camera_type FROM events e JOIN videos v ON v.id = e.video_id "
            "WHERE v.status='done' AND COALESCE(v.moderation_status, '') != 'hidden' "
            "AND v.lat IS NOT NULL AND v.lng IS NOT NULL AND v.created_at >= ? "
            "AND v.lat BETWEEN ? AND ? AND v.lng BETWEEN ? AND ? "
            f"AND (e.type LIKE 'congestion%' OR (e.type IN ({','.join('?' * len(OFFENCES))}) AND e.verified = 1)) "
            # one analysis per video: the latest (a re-analysis must not double every jam); a violation a
            # reviewer confirmed stays even if it came from an earlier analysis
            "AND (e.job_id = (SELECT r.job_id FROM results r WHERE r.video_id = v.id ORDER BY r.rowid DESC LIMIT 1) "
            "     OR e.verified = 1) "
            "ORDER BY v.created_at DESC LIMIT 2000",
            (since, BD_BBOX[1], BD_BBOX[3], BD_BBOX[0], BD_BBOX[2], *OFFENCES)).fetchall()
    return {"days": days, "incidents": [
        {"id": r["id"], "type": r["type"], "vehicle_class": r["vehicle_class"], "verified": bool(r["verified"]),
         "confidence": r["confidence"], "lat": round(r["lat"], 5), "lng": round(r["lng"], 5),
         "video_id": r["video_id"], "at": r["created_at"], "start_s": r["start_s"]} for r in rows]}


@router.get("/offline")
def offline_info():
    if _pack is None or not _pack.is_file():
        return {"available": False}
    st = _pack.stat()
    return {"available": True, "bytes": st.st_size, "built": st.st_mtime, "bbox": BD_BBOX,
            "url": "/api/map/offline/bd.pmtiles", "attribution": "© OpenStreetMap contributors, Protomaps"}


@router.get("/offline/bd.pmtiles")
def offline_pack():
    if _pack is None or not _pack.is_file():
        raise HTTPException(404, "the offline map pack hasn't been built on this server")
    # FileResponse answers Range requests (206), so MapLibre can read single tiles straight from it
    return FileResponse(_pack, media_type="application/vnd.pmtiles", headers={"Cache-Control": "public, max-age=86400"})
