"""Event-engine rule tests on synthetic tracks (PLAN §7 "Rule unit tests")."""
import re
from pathlib import Path

import numpy as np

import synth as S
from roadwatch.events import analyse
from roadwatch.track import stitch_tracks
from roadwatch.types import Hints

ALONG = Hints(camera_along_road=True)


I18N = Path(__file__).resolve().parents[2] / "web" / "lib" / "i18n.tsx"


def _reason_templates():
    """rsn_* templates per language from the web app's dictionary ({} if the web app is absent)."""
    if not I18N.exists():
        return {}
    src = I18N.read_text(encoding="utf-8")
    bn_at = src.index("  bn: {")
    pick = lambda chunk: dict(re.findall(r'^\s+((?:rsn|nt)_\w+): "(.*)",$', chunk, re.M))
    return {"en": pick(src[:bn_at]), "bn": pick(src[bn_at:])}


TEMPLATES = _reason_templates()


def check_reason_parts(events):
    """Every event carries translatable reason parts, and the web app's English templates rebuild
    exactly the pipeline's English reason, so the Bangla page says the same thing."""
    for e in events:
        parts = e.get("details", {}).get("reason_parts")
        assert parts, f"{e['type']} event has no reason_parts"
        if not TEMPLATES:
            continue
        rendered = []
        for part in parts:
            key = "rsn_" + part["k"]
            assert key in TEMPLATES["en"] and key in TEMPLATES["bn"], f"{key} missing from web/lib/i18n.tsx"
            rendered.append(re.sub(r"\{(\w+)\}", lambda m: part[m.group(1)], TEMPLATES["en"][key]))
        assert " · ".join(rendered) == e["reason"]


def test_every_reason_and_note_key_has_both_translations():
    """Static check over the source: each rp("key") / note("key") used by the pipeline has an
    English and a Bangla template in the web app, so no text silently stays English."""
    if not TEMPLATES:
        return
    src = "".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[1] / "roadwatch").rglob("*.py"))
    used = {"rsn_" + k for k in re.findall(r'\brp\("(\w+)"', src)} | {"nt_" + k for k in re.findall(r'\bnote\("(\w+)"', src)}
    assert len(used) >= 15, used  # sanity: the regexes found the call sites
    for lang in ("en", "bn"):
        assert not used - TEMPLATES[lang].keys(), f"missing {lang}: {sorted(used - TEMPLATES[lang].keys())}"


def run(tracks, duration, hints=None, road=None, **over):
    c = S.cfg(**over)
    S.prepare(tracks, c)
    res = analyse(tracks, road or S.road(), duration, hints or Hints(), c)
    check_reason_parts(res["events"])
    return res


def of(res, typ):
    return [e for e in res["events"] if e["type"] == typ]


# ---------------------------------------------------------------- E2 bus mid-road
def test_bus_stops_in_lane_2_raises_e2():
    bus = S.stop_and_go("bus", 420, 20, y_stop=400, stop_s=15)
    res = run(S.background(120) + [bus], 120)
    e2 = of(res, "bus_midroad_stop")
    assert len(e2) == 1 and e2[0]["track"] == bus.id
    assert 13 <= e2[0]["end"] - e2[0]["start"] <= 16
    assert e2[0]["details"]["kerb_gap_bus_widths"] > 0.5
    assert "bus-widths from the kerb" in e2[0]["reason"]


def test_bus_pulled_in_to_kerb_is_not_e2():
    bus = S.stop_and_go("bus", S.LEFT_KERB + 40, 20, y_stop=400, stop_s=15)
    assert not of(run(S.background(120) + [bus], 120), "bus_midroad_stop")


def test_short_stop_is_not_e2():
    bus = S.stop_and_go("bus", 420, 20, y_stop=400, stop_s=4)
    assert not of(run(S.background(120) + [bus], 120), "bus_midroad_stop")


def test_bus_stuck_behind_stopped_traffic_is_not_e2():
    bus = S.stop_and_go("bus", 420, 20, y_stop=500, stop_s=15)
    # two cars stopped right ahead of the bus (smaller y = ahead when moving up)
    ahead = [S.stop_and_go("car", 420, 18, y_stop=y, stop_s=22) for y in (320, 250)]
    assert not of(run(S.background(120, lanes_up=[300, 540]) + [bus] + ahead, 120), "bus_midroad_stop")


def test_jam_behind_bus_does_not_cancel_e2():
    """v2.1 fix: a jam behind a blocking bus is caused by it and must not cancel E2."""
    bus = S.stop_and_go("bus", 420, 20, y_stop=350, stop_s=25)
    t_arr = bus.t[np.argmin(np.abs(bus.boxes[:, 3] - 350))]
    behind = [S.stop_and_go("car", 420, t_arr - 3 + k, y_stop=430 + 70 * k, stop_s=22 - k) for k in range(4)]
    res = run(S.background(120, lanes_up=[300, 540]) + [bus] + behind, 120)
    e2 = of(res, "bus_midroad_stop")
    assert len(e2) == 1
    assert e2[0]["details"]["vehicles_blocked"] >= 3


def test_id_switch_is_stitched_into_one_event():
    full = S.stop_and_go("bus", 420, 20, y_stop=400, stop_s=20)
    cut = len(full) // 2
    gap = 7  # ~0.5 s of missing frames
    a = S.Track(9001, "bus", full.t[:cut], full.boxes[:cut])
    b = S.Track(9002, "bus", full.t[cut + gap:], full.boxes[cut + gap:])
    c = S.cfg()
    tracks = stitch_tracks(S.background(120) + [a, b], c)
    buses = [t for t in tracks if t.cls == "bus"]
    assert len(buses) == 1 and sorted(buses[0].source_ids) == [9001, 9002]
    res = run(tracks, 120)
    assert len(of(res, "bus_midroad_stop")) == 1


def test_red_light_queue_is_signal_not_jam_and_not_e2():
    """Queues stop at the same line every ~60 s → signal_queue; the bus at the front isn't E2."""
    tracks = []
    for cyc, t_red in enumerate((10, 70, 130)):
        for k, x in enumerate([300, 540]):
            for q in range(4):
                tracks.append(S.stop_and_go("car", x, t_red - 3 + q, y_stop=220 + 70 * q, stop_s=28 - q))
        if cyc == 1:
            tracks.append(S.stop_and_go("bus", 420, t_red - 4, y_stop=220, stop_s=27))
        else:
            for q in range(4):
                tracks.append(S.stop_and_go("car", 420, t_red - 3 + q, y_stop=220 + 70 * q, stop_s=28 - q))
    res = run(tracks, 190)
    assert "signal_queue" in res["scene"]["states"]
    assert "jam" not in res["scene"]["states"]
    assert not of(res, "bus_midroad_stop")
    assert not of(res, "congestion_jam")
    assert res["congestion"]["signal_queues"]


def test_leguna_is_reported_as_subtype():
    leg = S.stop_and_go("leguna", 420, 20, y_stop=400, stop_s=15)
    e2 = of(run(S.background(120) + [leg], 120), "bus_midroad_stop")
    assert len(e2) == 1 and e2[0]["subtype"] == "leguna"


# ---------------------------------------------------------------- E3 wrong way
def test_wrong_way_motorbike_raises_e3():
    bike = S.drive("motorcycle", 420, 30, 8, up=False)
    res = run(S.background(120) + [bike], 120)
    e3 = of(res, "wrong_way")
    assert len(e3) == 1 and e3[0]["track"] == bike.id
    assert e3[0]["details"]["angle_diff_deg"] > 135
    assert e3[0]["details"]["direction_source"] == "flow"
    assert e3[0]["severity"] == "high"


def test_normal_traffic_has_no_wrong_way():
    assert not of(run(S.background(120), 120), "wrong_way")


def test_wrong_way_rickshaw_is_separate_lower_severity():
    rk = S.drive("rickshaw", 420, 30, 4, up=False)
    e3 = of(run(S.background(120) + [rk], 120), "wrong_way")
    assert len(e3) == 1 and e3[0]["subtype"] == "slow_vehicle" and e3[0]["severity"] == "medium"


def test_wrong_way_group_cannot_outvote_with_leave_one_out():
    bikes = [S.drive("motorcycle", 420, 30 + 3 * k, 8, up=False) for k in range(2)]
    e3 = of(run(S.background(120) + bikes, 120), "wrong_way")
    assert {e["track"] for e in e3} == {b.id for b in bikes}


def test_u_turn_is_tagged_not_wrong_way():
    v = S.px_per_s("motorcycle", 8)
    t0, y_turn = 30, 200
    t1 = t0 + (S.H - 5 - y_turn) / v
    kf = [(t0, 600, S.H - 5), (t1, 600, y_turn)]
    for k in range(1, 13):  # semicircle 600 -> 680 over the divider
        a = np.pi * k / 12
        kf.append((t1 + k * 0.12, 640 - 40 * np.cos(a), y_turn - 40 * np.sin(a)))
    t2 = kf[-1][0]
    kf.append((t2 + (S.H - 5 - y_turn) / v, 680, S.H - 5))
    bike = S.track("motorcycle", kf)
    res = run(S.background(120) + [bike], 120)
    assert len([e for e in of(res, "u_turn") if e["track"] == bike.id]) == 1
    assert not [e for e in of(res, "wrong_way") if e["track"] == bike.id]


def test_reversing_slowly_is_not_wrong_way():
    car = S.track("car", [(30, 420, 300), (34, 420, 300 + S.px_per_s("car", 0.8) * 4)])
    assert not of(run(S.background(120) + [car], 120), "wrong_way")


def test_too_little_traffic_reports_cannot_judge():
    tracks = [S.drive("car", 420, 5 * k, 8, up=True) for k in range(3)] + [S.drive("motorcycle", 420, 30, 8, up=False)]
    res = run(tracks, 60, road=S.road(divider=False))
    assert not of(res, "wrong_way")
    assert "not enough traffic to judge direction" in res["notes"]


def test_left_hand_traffic_rule_fills_in_for_sparse_traffic():
    tracks = [S.drive("car", 420, 5 * k, 8, up=True) for k in range(3)] + [S.drive("motorcycle", 420, 30, 8, up=False)]
    e3 = of(run(tracks, 60, hints=ALONG), "wrong_way")
    assert len(e3) == 1 and e3[0]["details"]["direction_source"] == "lht"


def test_user_arrow_has_priority():
    tracks = [S.drive("car", 420, 5 * k, 8, up=True) for k in range(3)] + [S.drive("motorcycle", 420, 30, 8, up=False)]
    hints = Hints(arrows=[(420, 600, 420, 200)])  # traffic goes up
    e3 = of(run(tracks, 60, hints=hints, road=S.road(divider=False)), "wrong_way")
    assert len(e3) == 1 and e3[0]["details"]["direction_source"] == "arrow"


def test_oneway_large_minority_is_road_level_not_per_vehicle():
    tracks = S.background(120, per_lane=6)  # half up, half down
    res = run(tracks, 120, hints=Hints(oneway=True), road=S.road(divider=False))
    assert "two-way traffic on a one-way road" in res["notes"]
    assert not of(res, "wrong_way")


def test_oneway_small_minority_is_flagged():
    tracks = S.background(120, per_lane=6, lanes_down=[]) + [S.drive("car", 860, 40, 8, up=False)]
    e3 = of(run(tracks, 120, hints=Hints(oneway=True), road=S.road(divider=False)), "wrong_way")
    assert len(e3) == 1 and e3[0]["details"]["direction_source"] == "oneway"


# ---------------------------------------------------------------- E1 congestion
def _parked_grid(duration):
    tracks = []
    for row in range(14):
        for col in range(8):
            x = S.LEFT_KERB + 55 + col * 110
            y = 80 + row * 45
            tracks.append(S.track("car", [(0, x, y), (duration, x, y)]))
    for t in tracks:  # wider boxes so the road is ~90% covered
        cx = (t.boxes[:, 0] + t.boxes[:, 2]) / 2
        t.boxes[:, 0], t.boxes[:, 2] = cx - 50, cx + 50
    return tracks


def test_long_standstill_is_a_jam():
    res = run(_parked_grid(150), 150)
    jams = of(res, "congestion_jam")
    assert len(jams) == 1 and jams[0]["details"]["scene_state"] == "jam"
    assert res["congestion"]["avg"] > 60


def test_short_clip_jam_is_unknown_with_lower_score():
    long_ = of(run(_parked_grid(150), 150), "congestion_jam")[0]
    short = of(run(_parked_grid(40), 40), "congestion_jam")
    assert len(short) == 1 and short[0]["details"]["scene_state"] == "unknown"
    assert short[0]["raw_score"] < long_["raw_score"]


def test_free_flow_is_not_a_jam():
    res = run(S.background(120), 120)
    assert not of(res, "congestion_jam")
    assert all(lv in ("free", "moderate") for lv in res["congestion"]["levels"])
