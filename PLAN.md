# RoadWatch BD — Project Plan

**An AI model and web platform that finds unusual road problems in Bangladeshi traffic videos**

Version 2.1 · 2026-11-04 · Author: Atik Shahriar
*(v2.0 = full rewrite after two review passes; v2.1 = final logic check; see §16)*

---

## 0. Summary

People upload a road video (phone, footbridge, dashcam or CCTV clip). The system finds and
timestamps these problems:

| # | Event | Plain meaning | When |
|---|---|---|---|
| E1 | **Traffic congestion / jam** | Many vehicles, very little movement, lasting a while (not just a red light) | MVP |
| E2 | **Bus stopping mid-road** | A bus stops in a running lane (not pulled in to the kerb) to pick up or drop off passengers and blocks traffic | MVP |
| E3 | **Wrong-way driving** | A vehicle moves against the direction traffic should flow on that part of the road | MVP |
| E4 | Illegal stopping / parking | Any vehicle stopped in a running lane for a long time | Phase 2 |
| E5 | People on the carriageway | People standing or crossing in a running lane, away from a crossing | Phase 2 |
| E6 | Root-cause link | "This jam probably started because of the bus at 00:42" | Phase 2 |

It returns an annotated, privacy-blurred video, a timeline of events with a plain-language
reason for each one, a congestion score, and (if a location is given) a pin on an incident map.

**Main design choice:** there is **no single end-to-end model** that "detects wrong-way
driving". It is a **pipeline of separate, testable parts**:

```
video → normalise → camera-motion check → detect vehicles → track them
      → understand the road (edges, divider, flow direction) → scene state (signal / jam / flowing)
      → event rules → merge + calibrate → blurred report
```

Each part can be trained, tested and fixed on its own. This matters because labelled
Bangladeshi *event* data doesn't exist yet. A good detector can be trained from existing
datasets now, while event data builds up from your own recordings and the platform.

### MVP scope (what v1 promises — and what it doesn't)

| In the MVP | Not in the MVP (later) |
|---|---|
| Static or slightly shaky videos (footbridge, roadside, CCTV) | Full analysis of video shot from a moving vehicle (only congestion, marked "limited") |
| Daytime and dusk | A guarantee at night or in heavy rain (works, shown with a low-confidence warning) |
| Clips up to 5 min, landscape preferred | Live CCTV / streaming |
| E1, E2, E3 with reasons and confidence | E4, E5, E6 |
| Blurred output, feedback buttons, Bangla + English, anonymous uploads | Public incident map, accounts, contributor scores, API |

---

## 1. Review of the idea (honest feedback)

### What's strong
- **A real, local problem.** Buses stopping mid-road and wrong-way rickshaws/bikes are daily
  Dhaka problems, and most traffic AI work is built for Western, lane-disciplined roads.
  That gap is a real differentiator for a thesis, portfolio or startup.
- **Crowd-sourced video** needs no camera hardware. Anyone with a phone can add data.
- **The data loop.** Every upload plus feedback ("was this correct?") can become new
  training data once it is checked.

### What's harder than it looks (and how this plan handles it)

| Challenge | Why it's hard | How it's handled |
|---|---|---|
| **Moving / shaky camera** | If the camera moves, every vehicle seems to move, so speed and direction are wrong. | Camera-motion check + stabilisation (§5.2). MVP officially supports static/near-static video. |
| **"Wrong way" needs the right way** | The system must know which way each part of the road should flow. | Learned flow field + left-hand-traffic rule + optional user arrow (§5.6, §6.4). |
| **"Mid-road" needs road geometry** | A bus pulled in to the kerb is fine; in lane 2 it is not. | Road segmentation + track heat-map → kerb line (§5.4). |
| **Red lights & traffic police** | At a signal everything stops, which looks just like a jam or a blocking bus. | Scene-state step runs before the event rules (§6.1). |
| **Extreme density** | In a jam, vehicles hide each other; trackers lose and re-create IDs. | ByteTrack/BoT-SORT, **track stitching** and event merging (§5.5, §6.0); congestion uses area-level measures. |
| **BD-specific vehicles** | Standard models don't know CNGs, legunas, human haulers or rickshaw vans. | Fine-tune on Bangladeshi datasets + own frames (§4). |
| **Typical phone uploads** | Portrait, variable frame rate, re-compressed by WhatsApp/Messenger, no GPS/date. | Normalisation (§5.1); in-browser trim/compress; manual location (§8.1). |
| **Night, rain, glare** | Accuracy drops. | Augmentation, targeted data, confidence warning; out of the MVP guarantee. |
| **False accusations** | A wrong label next to a readable plate can harm someone. | Blur by default (§5.7), "possible incident" wording, calibrated confidence, human review before any official use. |
| **Licences** | Ultralytics YOLO is **AGPL-3.0**. | Decide in Phase 0; swappable detector; Apache-2.0 options (§5.3). |

### Verdict
Doable as a solo or small-team project **if scoped as above**. Get E1–E3 working well on
static daytime video first, then widen. Trying to handle every video type and every event
at once is the most common way projects like this fail.

---

## 2. Users & goals

**Who it's for**

| User | What they want | What we give |
|---|---|---|
| Commuters / citizens | Prove a daily problem, see whether others face it too | Fast result, a shareable blurred clip, "your report joined 23 others at this spot" |
| Journalists / bloggers | Evidence and numbers | Hotspot stats, downloadable reports |
| Researchers / students | Bangladeshi traffic data | Anonymised event data export, methodology docs |
| City bodies (DTCA, DMP Traffic, city corporations) | Where and when problems happen | Verified hotspot reports by time of day, *only after accuracy is proven* |

**Goals (not just ML scores)**
- **Beta:** 100 real uploads; ≥ 60% of event feedback says "correct".
- **6 months:** 1,000+ uploads from 50+ locations; one public hotspot report that gets shared widely.

**Why people would upload**
- Results are fast and shareable (a short blurred clip with labels works well on social media).
- Visible impact: a monthly "worst mid-road bus-stop spots in Dhaka" post.
- Partner with Facebook traffic-update groups and university clubs.

**Running costs & money:** keep costs near zero at first (§9). Possible support:
university research funding, innovation grants (e.g. a2i / ICT Division programmes),
hackathons, later paid analytics for organisations. Decide before scaling, because GPU
cost grows with uploads.

---

## 3. System architecture

```
┌──────────────┐  resumable upload    ┌──────────────────┐
│  Web app     │ ───────────────────▶ │  API (FastAPI)   │
│  Next.js     │ ◀── progress (SSE) ─ │  jobs, auth, DB  │
└──────┬───────┘                      └───┬──────────┬───┘
       │ results / map                    │ enqueue  │ read/write
       │                                  ▼          ▼
       │                        ┌──────────────┐  ┌──────────────┐
       │                        │ Queue (Redis)│  │ Postgres     │
       │                        └──────┬───────┘  │ (Supabase)   │
       │                               ▼          └──────────────┘
       │                ┌────────────────────────────────────────┐
       │                │ GPU worker (sandboxed, no secrets)     │
       │                │ PASS 1: probe → normalise → camera     │
       │                │   motion → detect → track → stitch     │
       │                │   → road mask → flow field             │
       │                │ PASS 2: scene state → event rules      │
       │                │   → merge → calibrate → blur → render  │
       │                └──────┬─────────────────────────────────┘
       │                       ▼
       └──── signed URLs ── Object storage (R2 / Supabase Storage, private)
                            raw video · blurred annotated video · events.json
```

**Why two passes:** uploads are processed offline, not live, so the system can look at the
**whole clip** before deciding anything. Pass 1 learns the road, the flow direction and
all tracks. Pass 2 judges each vehicle against that full picture. This is much more
reliable than deciding frame by frame, and it is a key advantage of batch processing.

---

## 4. Data plan

### 4.1 Existing datasets

> Check each dataset's licence before commercial use; most are research-only. Record
> licences in `docs\dataset_card.md`.

| Dataset | What it gives | Use |
|---|---|---|
| **DhakaAI (2020)** | ~3,000 Dhaka street images, 21 local vehicle classes | Main detector data |
| **Poribohon-BD** | Bangladeshi vehicle images, 15 classes | Extra detector data |
| **BadODD** | Road-view images from several BD districts, day and night | Detector data (dashcam view) |
| **IDD — India Driving Dataset** | South-Asian roads with drivable-area segmentation | Road segmentation |
| **UA-DETRAC / AI City Challenge** | Fixed-camera traffic video with tracks | Tracker tuning, benchmark |
| **Bangladeshi licence-plate datasets** (several public ones exist; check licences) | Plate boxes on BD plates | Plate-blur model (§5.7) |
| **COCO** | General objects | Pretrained weights |

**Viewpoint gap:** these sets are mostly street-level or dashcam views. The platform's main
input is **footbridge/roadside** footage, so your own frames must cover those views, and
the test set must be made of them.

### 4.2 Your own recordings

There is no public dataset of "bus stopping mid-road in Dhaka" or "wrong-way rickshaw".
**You have to collect it**, and that is also what makes the project original.

- **Places:** footbridges and roadside spots with known problems, e.g. Farmgate,
  Mohakhali, Gulistan, Jatrabari, Science Lab, Shahbag, Mirpur-10, Airport Road, Kuril,
  Uttara bus stops. For wrong-way: service lanes, near U-turns, one-way streets around
  Karwan Bazar and Old Dhaka.
- **Camera:** phone on a small tripod or clamp, 1080p, 30 fps, landscape, 2–5 min clips,
  whole road width in view.
- **Variety:** morning/evening rush, midday, dusk, some night and rain, different heights
  and angles.
- **Hard negatives (just as important):** red-light queues, police-held traffic, buses
  pulled in to the kerb, U-turns, reversing vehicles. These cause false alarms.
- **Also:** a few dashcam / moving-bus clips for the later moving-camera mode.
- **Target:** ~40–60 h raw video → ~300 E2 events, ~300 E3 events, ~150 jam segments.
- **Metadata sheet for each clip:** place, GPS, date/time, weather, camera height and
  angle, which way the camera faces along the road.
- **Storage:** ~4–8 GB per hour of 1080p30 → **~300 GB** raw. Use an external disk plus
  one cloud backup; keep a 720p working copy.
- **Ethics:** film public roads only; never publish unblurred clips.

### 4.3 Annotation

| Layer | Tool | What | Target |
|---|---|---|---|
| Boxes | CVAT / Label Studio (free) or Roboflow | Frames every 1–2 s, mostly footbridge/roadside views | **1,500–2,500 own frames** |
| Tracks | CVAT video mode | Short clips with persistent IDs (tracker evaluation only) | 20–30 clips × 1 min |
| Road | CVAT polygons | Drivable area, kerb, divider, bus bay, footpath | ~500 frames (IDD gives the rest) |
| Plates/faces | CVAT boxes | For checking blur (§5.7) | ~300 frames |
| Events | CVAT tags or a spreadsheet | `clip, type, start_s, end_s, track_id, notes` | All events + hard negatives |

**How to label faster**
- **Model-assisted labelling:** a first detector drafts boxes and people only fix
  mistakes (typically 3–5× faster). For round one, an open-vocabulary model
  (Grounding DINO / OWL-ViT) or a large "teacher" detector drafts the boxes.
- **Candidate mining for events:** don't watch 60 h of video. Run the pipeline with
  **loose thresholds** to suggest candidates; a person confirms or rejects each one.
  Fully watch a random 10% of footage to measure how many events the candidates miss.
- An optional **vision-language model** check (§6.9) can pre-sort candidates. A person still decides.

**Effort check:** a dense Dhaka frame has 40–80 vehicles. 2,000 frames × ~50 boxes ≈
**100,000 boxes**, roughly 60–100 h even with assistance. Budget it, share it with friends
or classmates, and prefer *varied* frames over many frames from one spot.

**Annotation guideline (write it before labelling):** 2–3 pages with example images.
It defines:
- each class (CNG vs leguna, rickshaw vs rickshaw-van)
- "stopped" and "in a running lane"
- where an event starts and ends
- jam vs signal queue
- how to label partly hidden vehicles

Two people label the same 50 frames and 30 events. If they agree on less than ~80% of
events, fix the definitions before going on.

**Legal reference:** match the definitions to the **Road Transport Act 2018** and DMP
traffic rules where possible, so "violation" means the same thing the law means.

### 4.4 Unified class list

```
0 person          5 easybike / e-rickshaw   10 bus (all: city, minibus, double-decker)
1 bicycle         6 cng_autorickshaw        11 truck
2 rickshaw        7 leguna / human hauler   12 pickup / covered van
3 rickshaw_van    8 car                     13 ambulance / emergency
4 motorcycle      9 microbus / SUV / jeep   14 other (tractor, cart, …)
```
- One `bus` class: city vs intercity is hard to tell from above and changes no rule.
- A script maps each dataset's labels to this list (e.g. DhakaAI "three wheelers (CNG)"
  → `cng_autorickshaw`).
- Merge any class with fewer than ~300 examples into its nearest neighbour or `other`.

### 4.5 Splits
- Split by **location and day**, never by random frame. Frames from the same clip in
  train and test give scores that are too good.
- 70 / 15 / 15 train / val / test, plus a **hard test set** (night, rain, dense jams) and
  a **held-out location** never used for tuning (§7).

### 4.6 Training compute
- Kaggle gives roughly **30 free GPU-hours per week** (T4/P100); Colab Pro or a local
  RTX GPU also works.
- Do fast experiments at **640 px** and only the final runs at **960–1280 px**.
- A full high-resolution run is roughly **10–25 GPU-hours**. This is an estimate, so
  measure the first run. Save checkpoints so a run can resume across sessions.
- Track every run (data version, config, scores) in Weights & Biases or MLflow.

---

## 5. Model pipeline

### 5.1 Pre-processing
- **`ffprobe` first:** reject anything that isn't a valid, allowed video (also a security
  step, §8.7).
- **`ffmpeg`:**
  - apply the rotation flag (portrait phone video)
  - convert **variable → constant frame rate** and re-encode to H.264
  - limit the long side to 1280 px
  - resample to **~15 fps** for analysis (fast motorbikes are hard to track below ~10 fps)
  - cap the length at 5 min
- Read GPS and time if present (usually missing on forwarded videos).
- Portrait video is allowed but shows a narrow strip of road. Expect weaker wrong-way
  results and tell the user that landscape is better.

### 5.2 Camera-motion handling
1. Track background points (ORB / optical flow) **outside** vehicle boxes.
2. Estimate frame-to-frame motion (homography with RANSAC).
3. Classify the clip:
   - **Static:** median background motion < ~1 px/frame → analyse directly.
   - **Shaky:** small jitter → stabilise to a reference frame, then analyse.
   - **Moving platform:** large steady motion → subtract camera motion; only congestion
     is fully supported; E2/E3 are marked "low confidence".
4. The user can trim to the steady part of the clip.

### 5.3 Object detection
- **⚠ Licence decision first.** Ultralytics YOLO is **AGPL-3.0**. If the platform's code
  stays closed (or may become a business), choose one:
  - (a) open-source the whole platform under AGPL
  - (b) buy an Ultralytics Enterprise licence
  - (c) use an Apache-2.0 detector: **RF-DETR**, **D-FINE**, **YOLOX**, or RT-DETR via
    Hugging Face Transformers

  Whatever you prototype with, put the detector behind a small interface (`detect.py`) so
  it can be swapped without touching anything else. ByteTrack (MIT) and `supervision`
  (MIT) are fine to use.
- **Model size:** a small model (`s`) for production, a medium one (`m`) to see the accuracy ceiling.
- **Training:**
  - start from COCO weights, then fine-tune on the merged BD set
  - image size 960–1280 (vehicles are tiny in footbridge shots)
  - augmentation: mosaic, colour, motion blur, rain/fog
  - 100–200 epochs
- **Small, far-away vehicles:** use tiled inference (**SAHI**) on the far part of the frame
  if needed. Measure whether it helps; it costs speed.
- **Targets:** mAP@50 ≥ 0.70 overall, ≥ 0.80 on bus, rickshaw, CNG, car and motorcycle,
  measured on the **footbridge/roadside test set**.
- **Export:** ONNX → TensorRT (GPU) or OpenVINO (CPU fallback).

### 5.4 Road understanding
- **Segmentation model:** SegFormer-B1/B2 (or a YOLO-seg model if the licence allows),
  trained on IDD plus your ~500 road polygons.
- **Track heat-map:** where vehicles actually drove during the clip.
- **For static cameras, combine both from the start:** where they agree is road; the outer
  edge of the heat-map is a good kerb estimate. For dashcams, segmentation is primary.
- **Outputs per clip** (the road doesn't move, so combine many frames):
  - drivable-area mask
  - left and right kerb lines
  - divider/median (if any)
  - optional bus-bay / footpath zones
- **Last fallback:** ask the user to tap the two road edges on the first frame.

### 5.5 Tracking
- **Tracker:** ByteTrack to start (good with low-confidence boxes in jams); BoT-SORT with
  camera-motion compensation for shaky clips.
- **Per track:**
  - class
  - box history
  - **ground point** (bottom-middle of the box)
  - smoothed velocity and heading (Kalman)
  - stopped / moving state
- **Track stitching:** in dense traffic one vehicle often gets 2–3 IDs. Join a track that
  ends to one that starts when:
  - it is the same class
  - the gap is < ~1.5 s
  - the start is close to the predicted position
  - optionally, the appearance matches (re-ID features)

  Without stitching, one bus stop becomes two events and one wrong-way bike is counted twice.
- **Speed:** divide pixel speed by a **typical size for the class** (bus ~11 m, car ~4.5 m,
  rickshaw ~2.5 m, motorbike ~2 m) → "approx. m/s". Raw box height is not used because
  hidden boxes shrink in jams. If the user marks 4 road points, use a bird's-eye homography
  instead.
- **Stopped** = smoothed speed below a threshold for ≥ 1 s, with hysteresis so jitter
  doesn't flip the state back and forth.
- **Distances** (e.g. kerb gap) are in **bus-widths / lane-widths** unless the clip is
  calibrated. Never show metres that weren't measured.
- **Target:** IDF1 ≥ 0.65 on your annotated BD clips.

### 5.6 Flow field (direction of traffic)
- Divide the road mask into a grid (e.g. 16×9 cells).
- For each cell, collect the headings of moving (stitched) tracks across the **whole
  clip**, then take the circular median → **dominant direction** plus an **agreement score**.
- **Minimum evidence:** a cell needs ≥ ~8 different moving tracks before its direction is
  trusted.
- **Leave-one-out:** when judging a track, compute the flow **without that track**, so a
  group of wrong-way vehicles can't outvote the real direction.
- **Ambiguous cells** (junctions, U-turn points, low agreement): no wrong-way judgement there.
- **Left-hand-traffic rule** (when a divider is visible and the camera faces *along* the
  road): Bangladesh drives on the left, so traffic on the **left side of the image moves
  away** from the camera and traffic on the **right side comes towards** it. This gives a
  direction even when there's little traffic, and acts as a sanity check on the learned
  flow. It doesn't apply when the camera looks across the road.
- If there's no trusted flow, no rule and no user arrow, report "not enough traffic to judge
  direction" rather than guess.

### 5.7 Privacy blur
- **Faces:** a light face detector (e.g. YuNet in OpenCV, which has a permissive licence).
- **Plates:** a small plate detector trained on Bangladeshi plate data plus your frames.
- **Safety net:** for vehicles close to the camera (large boxes, where a plate could be
  readable), also blur the plate area of the box even if no plate was found.
- **Measure it:** blur recall ≥ **95%** on 300 annotated frames. A missed plate is a
  privacy leak, so this target matters as much as detection accuracy.
- Everything shared, downloaded or shown publicly is blurred. Only the uploader's private
  raw file stays unblurred, and only until it is deleted.

---

## 6. Event engine

### 6.0 Rules that apply to every event
- All thresholds live in `events.yaml`. They are never tuned on the test set.
  - **Small-data warning:** ~300 events per type leaves only ~45 in a 15% validation split,
    which is too few to tune on alone.
  - Tune with **location-wise cross-validation** over train + val instead: each fold holds
    out one place. Use the **loose-threshold candidates**, which run into thousands once
    hard negatives are included, not only the confirmed events.
- **Reason:** each event carries a plain-language reason, e.g. *"stopped 14 s · ~1
  lane-width from the kerb · 9 vehicles held up behind"*.
- **Event merging:** events of the same type on the same (stitched) track with a gap of
  < ~3 s become one event. Summary counts are of **distinct vehicles**, not raw events.
- **Confidence calibration:** each rule produces a raw score. Fit a calibration curve (raw score →
  probability of being correct) on the cross-validated candidates, so "0.8" really means
  about 80% are right.
  - Start with **Platt scaling**, which has 2 parameters and is safe with little data.
  - Switch to **isotonic regression** once there are ~500+ labelled candidates per type.
  - Shown by default: calibrated confidence ≥ **0.6**.
  - Lower ones sit behind a "show uncertain" toggle.
  - Each event type has its own cut-off.

### 6.1 Scene state (runs first)
Many "everything stopped" moments are normal. Each time window gets a state:

| State | Signs |
|---|---|
| `flowing` | most tracks moving |
| `signal_queue` | queue front stops at the **same line** each time; regular stop–go cycles (~30–120 s); cross-traffic moves while this direction waits |
| `jam` | stopped with no regular cycle, or a queue front with no fixed stop line; lasts longer than one signal cycle |
| `unknown` | clip too short to tell (< ~1 cycle) |

- During `signal_queue`, E1 says "queue at signal" (not a jam), and E2 isn't raised for a
  bus that's simply in the queue.
- Clips under ~60 s can't show a full cycle, so jam confidence is lowered for them.
- Later: a small classifier for signal lights / traffic police at the queue front.

### 6.2 E1 — Congestion level
Per 5 s window, measured on the road mask:
- **`occupancy`:** take the union of vehicle **ground footprints** (lower part of each box),
  **row by row**, each image row divided by the road width at that row, then averaged.
  The union avoids double-counting overlapping boxes. The row-by-row normalisation stops
  close vehicles from counting more than far ones. If the clip is calibrated, measure in
  the bird's-eye view instead.
- **`median_speed`:** normalised speed of tracked vehicles.
- **`stopped_ratio`:** share of vehicles that are stopped.

| Level | Starting rule (tune on val) |
|---|---|
| Free flow | occupancy < 0.15, or speed high |
| Moderate | 0.15–0.35 and speed medium |
| Heavy | ≥ 0.35 and speed low |
| **Jam** | ≥ 0.45 **and** stopped_ratio ≥ 0.6 **for ≥ 30 s**, **and** scene state is `jam` (or `unknown`, with lower confidence) |

Output: a congestion score (0–100) over time, plus jam intervals.
*Phase 2:* replace the rules with a small learned model on the same features.

### 6.3 E2 — Bus stopping mid-road
A bus track raises E2 when **all** of these hold:
1. **Class** is `bus`. Optionally `leguna / human hauler`, reported as a separate subtype.
2. **Stopped for ≥ 8 s** (tune between 5 and 15 s).
3. **In a running lane:** the gap between the bus's kerb-side edge and the kerb line is
   **> ~0.5 bus-width**. A bus pulled in to the kerb is *not* E2, even at an informal stop.
   Most Dhaka stops have no bay, so the rule is about **blocking a lane**, not about where
   stops are.
4. **Stopped by choice, not stuck:** judged by the traffic **ahead of the bus**, not
   behind it.
   - The lane ahead must be **moving or empty**.
   - The bus must not be **inside a signal queue**, i.e. not waiting behind or at a stop line
     while that direction has a red light.
   - A jam **behind** the bus does *not* cancel E2: that jam is usually caused by the bus,
     and it is what E6 links back to it.

**More evidence (raises confidence):**
- people near the bus door side, or people tracks joining or leaving the bus
- vehicles behind it slowing down or swerving round it
- the bus moving off again afterwards

**Severity (when the location is known):** OpenStreetMap `highway=bus_stop` nearby →
"at a stop, but blocking" (medium); no stop nearby → high.

**Output:** start/end, track, duration, kerb gap (lane-widths), vehicles held up.

### 6.4 E3 — Wrong-way driving
A moving track raises E3 when:
1. it really moves (above a minimum speed) for **≥ 2 s** and **≥ 1 vehicle-length**
2. its heading differs from the trusted expected direction of the cells it crosses by
   **> 135°**
3. those cells are trusted (enough evidence, high agreement, not ambiguous)

**Expected direction, in order of priority:**
1. the user's arrow
2. OpenStreetMap `oneway=yes` (Phase 2): the camera's compass direction is unknown, but on
   a one-way road **any two-way flow is a violation**, so the minority direction is flagged.
   If the "minority" is large (> ~30% of moving vehicles), the system can't tell which
   side is breaking the rule. It then reports **"two-way traffic on a one-way road"** for
   the whole road and does not accuse individual vehicles.
3. the learned flow field (leave-one-out)
4. the left-hand-traffic rule

**Not wrong-way:**
- **Reversing:** slow, short, and the vehicle still faces the right way; filtered by the
  minimum speed and length.
- **U-turn:** heading turns smoothly by ~180° within a few seconds. This is a separate,
  low-severity "U-turn" tag.

**Severity by class:** wrong-way rickshaws and cycles are very common. They're reported
separately from wrong-way buses, cars, trucks and motorbikes, so the dangerous cases stand
out. Vehicles hugging the footpath edge get the lower "against flow" severity.

### 6.5 E4 — Illegal stopping (Phase 2)
Same as E2 for any vehicle class, with a longer limit (≥ 30 s), outside marked parking.
This is common for CNGs and legunas waiting for passengers.

### 6.6 E5 — People on the carriageway (Phase 2)
A person's foot point is inside a running lane for ≥ T s, away from a zebra crossing; a
crowd if ≥ K people. Only raised while traffic is `flowing`, because in jams people walk
between vehicles all the time.

### 6.7 E6 — Root-cause link (Phase 2)
If a jam starts within ~60 s **after** an E2/E4 blockage and **upstream** of it (along the
flow field), link them: *"Jam at 01:10 likely caused by the bus stopped at 00:42."* This
turns detections into insight and makes the strongest demo.

### 6.8 Pseudocode (pass 2)

```python
scene = scene_state(tracks, road, windows=5s)            # flowing / signal_queue / jam / unknown
flow  = FlowField(tracks, road, hints, min_tracks=8)      # trusted cells, agreement, ambiguity
events = []

for w in windows(5s):
    events += congestion(w, road, scene[w])               # E1 (jam only if scene says jam)

for t in stitched_tracks:
    if t.cls == "bus":
        for stop in t.stopped_segments(min_s=cfg.bus_stop_s):
            if (kerb_gap(stop, road) > cfg.kerb_gap
                    and lane_ahead_moving_or_empty(stop, tracks, flow)   # judge AHEAD,
                    and not in_signal_queue(stop, scene, flow)):          # not the queue behind
                events.append(E2(stop, raw=bus_score(stop, people, tracks_behind)))
    for seg in t.moving_segments(min_s=2, min_len=t.typical_length):
        if is_u_turn(seg):
            events.append(UTurn(seg)); continue
        exp = flow.expected(seg.cells, exclude=t)          # arrow > OSM > flow > LHT rule
        if exp.trusted and angle_diff(seg.heading, exp.dir) > 135:
            events.append(E3(seg, raw=ww_score(seg, exp)))

events = merge(events, gap_s=3)
events = calibrate(events)                               # isotonic, per event type
link_causes(events, flow)                                # Phase 2
```

### 6.9 Later: learned models and an AI second opinion
- **Track-sequence classifier** (after ~1,000+ checked events): a small GRU/Transformer
  over each track's features (position, speed, heading, kerb gap, nearby density) →
  event type. It's fast and still explainable through those features.
- **Clip classifier** (optional): VideoMAE / X3D on 4–8 s clips around candidates, as a
  second check to cut false positives.
- **Vision-language model check** (optional): send 4–6 **blurred** keyframes of a
  candidate to a VLM with a strict yes/no question ("Is the bus stopped in a running lane
  while passengers board?").
  - Most useful as a **labelling helper** while mining candidates.
  - In production, only if it measurably improves precision.
  - Watch the cost per call, the delay and privacy, and evaluate it like any other part.
- **The rules stay** as the fallback and as the explanation ("stopped 14 s, ~1 lane-width
  from the kerb").

---

## 7. Evaluation

| Part | Metric | MVP target |
|---|---|---|
| Detection | mAP@50, per-class AP (footbridge/roadside test set) | ≥ 0.70 overall |
| Road | IoU of drivable area; kerb-line error in lane-widths | IoU ≥ 0.80; error ≤ 0.3 |
| Tracking | IDF1, ID switches | IDF1 ≥ 0.65 |
| Blur | Recall on plates + faces | ≥ 95% |
| Scene state | Accuracy vs human labels (signal queue vs jam) | ≥ 85% |
| E1 | Agreement with human congestion level (Cohen's κ) | κ ≥ 0.6 |
| E2 | Precision / recall (a match = same bus, time overlap ≥ 30%) | P ≥ 0.80, R ≥ 0.70 |
| E3 | Precision / recall | P ≥ 0.85, R ≥ 0.65 |
| E2 / E3 | **False alarms per hour** of normal video | ≤ 2 (E2), ≤ 1 (E3) |
| Calibration | Expected calibration error | ≤ 0.10 |
| System | Processing time per video-minute, warm T4 | ≤ 90 s |

**How to test honestly**
- **Error bars:** with ~45 test events per type, a precision of 0.80 can really be
  anywhere from ~0.68 to ~0.90. Report **95% bootstrap confidence intervals**, and treat a
  target as met only if the result is close to it, not because of one lucky split.
- Report results **separately** for day / dusk / night / rain, static / shaky / moving,
  and landscape / portrait.
- **Held-out location:** tune on some places and test on a place never seen. Otherwise the
  thresholds just memorise one camera angle.
- **Baselines to beat:** (a) COCO detector with no fine-tuning; (b) no stabilisation;
  (c) no scene-state step. This shows each part is worth having, which is strong
  material for a thesis.
- **Error analysis:** look at every E2/E3 false positive and sort it by cause (road
  geometry, tracking, threshold, detector).
- **Rule unit tests:** synthetic tracks (a bus stopping in lane 2, a wrong-way bike, a
  U-turn, a red-light queue, an ID switch) go through the event engine. Fast, no GPU,
  run on every commit. A simulator such as SUMO can produce many more scenarios.
- **Regression set:** ~30 fixed clips with known events run on every model or rule
  change. Scores must not drop without a written reason.
- **Platform tests:** end-to-end browser tests (Playwright: upload → result) and a load
  test (20 jobs at once) before beta.

---

## 8. Platform / website

### 8.1 Features

**MVP**
1. **Upload page:**
   - choose a clip, trim it to the important 30 s–5 min, and **compress it to 720p in the
     browser** (ffmpeg.wasm / WebCodecs) before a **resumable** upload (target 30–80 MB,
     hard limit 200 MB)
   - optional location (map pin, or GPS from the file)
   - optional "traffic goes this way" arrows on the first frame
   - camera type (footbridge / roadside / CCTV / from vehicle)
   - recording tips: "hold steady 30 s+, landscape, show the whole road width"
2. **Processing page:** live steps (queued → starting → checking video → detecting →
   analysing → rendering), with a "notify me when ready" option (web push or email).
3. **Results page:**
   - blurred annotated video (boxes, track trails, event highlights, congestion bar)
   - **event timeline**: tap an event to jump to it; each event shows its reason and confidence
   - summary cards, e.g. "2 buses stopped mid-road (1 m 12 s blocking)" or
     "3 wrong-way vehicles (1 car, 2 motorbikes)"
   - feedback on each event: ✔ correct / ✖ wrong / wrong type
   - download MP4 + JSON; share link
4. **Bangla + English** throughout. **Mobile-first** design (most users are on phones and
   mobile data).
5. **Basic moderation:** report button, a check that the video is a road scene, a takedown flow.

**Phase 2**
6. Public incident map (Leaflet + OpenStreetMap), **verified incidents only**, filterable
   by type and time of day.
7. Accounts: upload history, contributor score.
8. Moderator panel: review queue, check event labels (approved labels feed retraining).
9. Stats pages, e.g. "Mohakhali: mid-road bus stops peak at 8–9 AM".

**Phase 3**
10. Live CCTV/RTSP mode (same pipeline over a rolling window).
11. Public API / data export for researchers, authorities and journalists.
12. Mobile app (React Native + Expo) that records and uploads directly.

### 8.2 Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + Tailwind + shadcn/ui | You know it; server-rendered public pages |
| Upload | tus resumable uploads (Uppy) + in-browser compression | Mobile connections drop |
| Map | Leaflet + OSM | Free; you've used it |
| API | FastAPI (Python) | Same language as the ML code |
| Queue | Redis + Celery (or ARQ) | Jobs take minutes |
| ML runtime | PyTorch → ONNX Runtime / TensorRT; detector per the licence decision (§5.3) | Speed, swappable |
| Video | ffmpeg, OpenCV, `supervision` | Standard, permissive licences |
| DB + auth | Supabase (Postgres + Auth) | You already use it |
| Storage | Cloudflare R2 (no egress fees) or Supabase Storage | Videos are large |
| Abuse protection | Cloudflare Turnstile + rate limits | Anonymous uploads |
| Errors / logs | Sentry + structured logs | Operations (§9.3) |
| Experiments / data | Weights & Biases or MLflow; DVC or versioned R2 folders | Reproducibility |

### 8.3 Database schema (first version)

```sql
users(id, email, name, role, created_at)                 -- role: user | moderator | admin
videos(id, user_id null, storage_key, content_hash, perceptual_hash,
       duration_s, fps, width, height, orientation, camera_type,
       lat, lng, place_name, location_source,             -- gps | user | none
       recorded_at, status,                               -- uploaded|queued|processing|done|failed
       moderation_status,                                 -- pending|ok|rejected|taken_down
       consent_training bool, created_at, raw_deleted_at)
jobs(id, video_id, model_version, rules_version, attempt, started_at,
     finished_at, error, progress)
results(video_id, job_id, annotated_key, report_key, congestion_avg,
        camera_motion_class, scene_summary jsonb)
events(id, video_id, job_id, type, subtype, vehicle_class, track_id,
       start_s, end_s, raw_score, confidence, severity, reason,
       details jsonb, snapshot_key, verified bool)
event_feedback(id, event_id, user_id null, verdict, corrected_type, note, created_at)
road_hints(video_id, arrows jsonb, road_points jsonb, edge_taps jsonb)
```

### 8.4 API

```
POST /api/uploads                 → resumable upload session
POST /api/videos                  → register video + metadata + hints, enqueue job
GET  /api/videos/{id}             → status, progress, summary
GET  /api/videos/{id}/events      → events (with ?include_uncertain=1)
GET  /api/videos/{id}/stream      → SSE progress
POST /api/videos/{id}/reanalyse   → re-run with the latest model
POST /api/events/{id}/feedback    → ✔ / ✖ / corrected type
POST /api/videos/{id}/report      → report / takedown request
GET  /api/map/incidents?bbox=&from=&to=&type=   (Phase 2, verified only)
GET  /api/stats/hotspots                        (Phase 2)
```

### 8.5 Output format (`events.json`)

```json
{
  "video_id": "…", "model_version": "det-0.3.1", "rules_version": "ev-0.5.0",
  "camera_motion": "static", "orientation": "landscape",
  "congestion": {"timeline": [[0,22],[5,31],[10,64]], "jams": [[130,270]],
                 "signal_queues": [[40,95]]},
  "events": [
    {"type": "bus_midroad_stop", "vehicle_class": "bus", "track": 17,
     "start": 42.0, "end": 56.5, "confidence": 0.87, "severity": "high",
     "reason": "stopped 14.5 s, ~1.1 lane-widths from kerb, 9 vehicles held up",
     "details": {"kerb_gap_lane_widths": 1.1, "vehicles_blocked": 9,
                 "passengers_seen": true, "scene_state": "flowing"}},
    {"type": "wrong_way", "vehicle_class": "motorcycle", "track": 51,
     "start": 88.2, "end": 93.0, "confidence": 0.91, "severity": "high",
     "reason": "moved 4.8 s opposite to traffic (172°)",
     "details": {"angle_diff_deg": 172, "direction_source": "flow_field"}}
  ]
}
```

### 8.6 Privacy, safety & legal
- **Blurred by default** everywhere outside the uploader's private raw file (§5.7).
- **Retention:** raw video deleted after **30 days** unless training consent is given;
  results kept until the user deletes them; feedback kept (it contains no video).
- **Consent:** a clear checkbox for training use; a plain privacy policy that follows
  current Bangladeshi data-protection law.
- **Wording:** always "**possible** incident (AI-detected, may be wrong)". Never name
  people, and never show plates.
- **Defamation risk:** don't publish rankings of named bus companies or drivers without
  verified data and legal advice.
- **Official use:** if authorities ever use the data, a person must review each case, and
  every step goes in an audit log.

### 8.7 Upload security
- Check type, size and codec from the file's real content (`ffprobe`), not its name.
  Allow-list mp4/mov/webm and h264/h265/vp9.
- The worker runs ffmpeg in a sandboxed container with **no secrets, minimal network
  access, and CPU/time/memory limits**. Keep ffmpeg up to date.
- Buckets are **private**; only short-lived signed URLs; never serve raw uploads from the
  main site's domain.
- Per-IP and per-account daily limits; Turnstile on anonymous uploads.

### 8.8 Trust in crowd reports
- **Location and time can be wrong or faked.** Store where each came from (GPS vs typed).
  Only **moderator-verified** incidents appear on the public map and stats.
- **Duplicates:** an exact hash plus a perceptual video hash catch re-uploads, so one
  incident isn't counted ten times.
- **Pranks, edited or non-road videos:** road-scene check, report button, review queue.
- **Noisy feedback:** only labels confirmed by a moderator (or by 2+ agreeing users) go
  into training data.

---

## 9. Deployment, cost & operations

### 9.1 Cost (MVP)

| Part | Option | Rough cost |
|---|---|---|
| Frontend | Vercel hobby | ৳0 |
| API + Redis | Railway / Render / Fly.io small instance | ~$5–10 / month |
| GPU worker | Serverless GPU (Modal, RunPod Serverless) that scales to zero | ~$0.01–0.03 per video-minute (T4/L4) |
| Storage | Cloudflare R2 | ~$0.015 / GB / month, no egress fees |
| DB / auth | Supabase free tier | ৳0 to start |
| CPU fallback (demo only) | Small detector + OpenVINO at ~5 fps on a VPS | Cheap but ~2–4× slower than real time |

Set a **monthly GPU budget alert** and a daily job cap from day one.

### 9.2 Throughput (estimate; measure it in Phase 3)
- 1 video-minute at 15 fps = 900 frames.
- A small detector at 960–1280 px on a T4 with TensorRT runs at roughly **40–80 FPS**
  (slower with SAHI), so ~15–30 s of detection.
- Decoding, tracking, a few segmentation frames, blur and rendering bring the total to
  ≈ **45–90 s per video-minute**. Rendering is often the slowest step, so use the NVENC
  encoder.
- **Cold start:** the first job after idle waits ~10–40 s while the container starts. Keep
  the image small, bake the weights in, and show "starting up…".
- Split long clips into 60 s chunks with overlap, so memory stays flat and progress is smooth.

### 9.3 Operations
- **Jobs:**
  - up to 2 retries with back-off
  - a hard timeout per job
  - a dead-letter list for jobs that keep failing
  - safe to re-run (same input → same output, no duplicate events)
- **Monitoring:** Sentry errors, job success rate, queue length, time per video-minute,
  GPU spend per day.
- **Versions:** every result stores `model_version` + `rules_version`. Old results never
  change silently; "re-analyse" makes a new result.
- **Drift check (monthly):** label ~50 fresh uploads and compare with the test scores. A
  drop means new kinds of video are coming in.
- **Backups:** daily database backup; the labelled datasets are backed up in two places.

---

## 10. Project folder structure

```
D:\Traffic AI model project\
├─ PLAN.md
├─ data\                            (git-ignored; versioned with DVC or R2 folders)
│  ├─ raw_videos\   public\   annotations\   processed\   events\
│  └─ clips_index.csv               (place, time, weather, camera angle…)
├─ ml\
│  ├─ configs\                      (dataset.yaml, train.yaml, events.yaml)
│  ├─ scripts\                      (convert_datasets.py, sample_frames.py, mine_candidates.py,
│  │                                  train_det.py, train_seg.py, export.py)
│  ├─ roadwatch\                    (Python package)
│  │  ├─ preprocess.py              (probe, normalise, resample)
│  │  ├─ camera_motion.py           (classify + stabilise)
│  │  ├─ detect.py                  (detector interface + backends)
│  │  ├─ track.py                   (tracker, stitching, speed, heading)
│  │  ├─ road.py                    (segmentation + heat-map, kerb, divider)
│  │  ├─ flow.py                    (flow field, LHT rule, hints)
│  │  ├─ events\                    (scene_state, congestion, bus_stop, wrong_way,
│  │  │                               merge, calibrate, causes)
│  │  ├─ privacy.py                 (face + plate blur)
│  │  ├─ render.py
│  │  └─ pipeline.py                (run_video(path, hints) → results)
│  ├─ tests\                        (synthetic-track rule tests, regression clips)
│  ├─ eval\                         (det, track, blur, event, calibration)
│  ├─ notebooks\
│  └─ models\                       (weights; git-ignored)
├─ backend\                         (FastAPI, Celery worker, Dockerfile.gpu)
├─ web\                             (Next.js)
└─ docs\                            (annotation_guideline.md, dataset_card.md, model_card.md,
                                     privacy_policy.md, report notes)
```

---

## 11. Roadmap (solo, part-time ≈ 20 h/week)

| Phase | Weeks | Work | Done when |
|---|---|---|---|
| **0. Setup & decisions** | 1 | Repo, env, download datasets, **licence decision**, annotation guideline v1, key papers | Datasets on disk; decisions in §15 answered |
| **1. Thin prototype** | 2–4 | Record ~5 h at 3 spots. COCO detector + ByteTrack + simple E1/E2/E3 rules + a bare upload page, end-to-end | One real clip goes upload → events → annotated video; a list of what breaks |
| **2. Data & labelling** | 3–9 | Record the rest (incl. hard negatives); 1.5–2.5k frames with model assistance; candidate mining; agreement check | Labelled sets; agreement ≥ 80% |
| **3. Detector + blur** | 6–9 | Class mapping, merge, train, SAHI test, export, plate/face blur, **measure throughput** | mAP@50 ≥ 0.70; blur recall ≥ 95% |
| **4. Tracking, road, flow, scene state** | 8–11 | Tracker tuning, stitching, camera-motion classes, road mask, flow field, signal-queue detection | Clean tracks + road on 10 clips; rule unit tests pass |
| **5. Event engine** | 10–13 | E1–E3 with reasons, merging, calibration, held-out-location tuning | §7 targets met on validation |
| **6. Evaluation & write-up** | 13–14 | Test set, baselines, error analysis, regression set, model card | Metrics table in `docs\` |
| **7. Platform MVP** | 13–18 | Upload (trim/compress/resumable), queue, GPU worker, results, feedback, moderation basics, security, monitoring, Bangla/English | A 2-min clip → result in < 3 min (warm); Playwright + load tests pass |
| **8. Beta** | 19–20 | Deploy; 20–50 testers (friends, university groups, Facebook traffic groups); watch errors and cost | ≥ 100 real uploads with feedback |
| **9. Phase 2** | 21–30 | E4–E6, verified map, moderator panel → retraining loop, OSM hints, moving-camera mode | Model v2 trained on checked platform data |
| **10. Phase 3** | later | Learned event models, live CCTV, mobile app, public API | — |

**Buffer:** plan for things to take ~20% longer. If you fall behind, cut scope in this
order:
1. notify-when-ready
2. in-browser compression (use a lower size limit instead)
3. SAHI
4. the segmentation model (heat-map + edge taps only)
5. E1 levels (jam / no jam only)

**Never cut:** blurring, the scene-state step, held-out evaluation.

**First step this week:** record one 5-minute footbridge clip. Then run a COCO-pretrained
detector + ByteTrack on it and draw the track trails. Seeing raw tracks on real Dhaka
traffic shows most of the hard problems straight away.

---

## 12. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Too few real events recorded | Can't tune or test E2/E3 | Hotspot recording; candidate mining; rules need far less data than learned models |
| Red-light / police queues read as jams or blocking | Many false alarms | Scene state (§6.1); hard negatives |
| Shaky or moving uploads dominate | Bad results | Motion classes, recording tips, low-confidence label |
| ID switches in dense jams | Split or double-counted events | Stitching + merging; area-level congestion |
| Wrong-way false alarms at junctions / U-turns | Loss of trust | Ambiguity mask, U-turn tag, leave-one-out flow, high-precision cut-offs |
| Footbridge viewpoint differs from public data | Weak detector | Own footbridge frames; footbridge test set |
| Labelling takes longer than planned | Timeline slips | Effort budget, helpers, model-assisted labelling |
| AGPL licence | Forced open-source or fees | Decide in Phase 0; swappable detector |
| Missed blur | Privacy harm | Safety-net blur, 95% recall target |
| Malicious video file | Server compromise | Sandbox + allow-lists (§8.7) |
| Fake / duplicate reports | Misleading map | Verified-only map, hashing (§8.8) |
| Defamation (naming companies) | Legal trouble | No named rankings without verification and advice |
| GPU cost spike | Bills | Scale-to-zero, quotas, budget alerts |
| Nobody uploads | No data loop | §2 adoption plan, partners |

---

## 13. Possible extensions
- **Bangla text or voice summary** of a video from `events.json` using an LLM
  ("৩টি বাস রাস্তার মাঝে থেমেছে…").
- **Hotspot forecasts:** which junctions jam at which hour, from incident history.
- **Emergency vehicle blocked** alert (ambulance stuck in a jam).
- **Bus-operator analysis** (livery classifier), only with verified data and legal review (§8.6).
- **Research paper:** "Modular detection of informal traffic violations in South-Asian
  mixed traffic", a natural thesis or conference paper from §7's evaluation.

---

## 14. References
- ByteTrack (Zhang et al., 2022); BoT-SORT (Aharon et al., 2022)
- IDD: India Driving Dataset (Varma et al., 2019)
- DhakaAI 2020, Poribohon-BD, BadODD dataset papers
- NVIDIA AI City Challenge papers on stopped-vehicle / anomaly detection and traffic flow
- SAHI: Slicing Aided Hyper Inference
- RF-DETR, D-FINE, YOLOX (Apache-2.0 detectors); Ultralytics docs (AGPL-3.0)
- `supervision` library (zones, line counters, trace drawing)
- Guo et al., *On Calibration of Modern Neural Networks* (2017), for confidence calibration
- Bangladesh Road Transport Act 2018 and DMP traffic rules (for event definitions)

---

## 15. Open decisions (answer in Phase 0)
1. **Open-source or closed?** Open source → AGPL YOLO is fine. Closed → use an Apache-2.0
   detector or buy a licence.
2. **Thesis/portfolio or product?** A thesis puts weight on §7 and the write-up (Phase 6).
   A product puts weight on adoption, cost and moderation (Phases 7–9).
3. **Who helps label?** This decides whether the Phase 2 timeline holds.
4. **Is night in or out of the MVP promise?** The current answer is out (low-confidence
   warning only).

---

## 16. Change log

**v1.0 → v1.1 (first review):**
- AGPL licence issue
- signal / police queues
- realistic labelling effort
- corrected throughput
- viewpoint gap
- annotation guideline
- candidate mining and storage size
- E2 kerb-stop and empty-lane cases
- wrong-way edge cases (reversing, U-turns, too few tracks, self-outvoting)
- speed and units fix
- phone-video normalisation
- mobile-first upload
- upload security
- crowd-report trust
- false alarms per hour, held-out location, regression and unit tests
- operations
- users and funding
- 20-week roadmap with an early prototype

**v1.1 → v2.0 (second review, full rewrite):**

| # | Problem in v1.1 | Fix in v2.0 |
|---|---|---|
| 1 | Patched text had contradictions: E2 rule 3 ("outside a bay") clashed with rule 5 (kerb stop is fine); E2 still listed "intercity bus" after the merge; §5.8 still showed metres; speed target 60 s vs estimate 45–90 s; broken cross-refs; duplicate feature numbering | Rewritten as one consistent document |
| 2 | No **track stitching / event merging**: ID switches in jams would split or double-count events | §5.5, §6.0 |
| 3 | Confidence scores were arbitrary numbers | Isotonic **calibration**, per-type display cut-offs, calibration error target (§6.0, §7) |
| 4 | Congestion density double-counted overlapping boxes and gave close vehicles too much weight | Union of ground footprints, normalised row by row (§6.2) |
| 5 | The left-hand-traffic rule was stated but not usable | Concrete image rule: left side moves away, right side comes towards, when the camera faces along the road (§5.6) |
| 6 | Pseudocode lacked scene state, stitching, U-turns, direction priority, merging, calibration | Rewritten (§6.8) |
| 7 | Plate/face blur had no data source, no target and no safety net | §5.7, blur recall ≥ 95% |
| 8 | No **MVP scope** box: "perfect on everything" risk | §0 in/out table |
| 9 | Processing was frame-by-frame in spirit; whole-clip context was unused | **Two-pass** architecture (§3) |
| 10 | No training-compute budget (Kaggle quota, run length) | §4.6 |
| 11 | No scope-cut plan or buffer | §11 |
| 12 | Defamation risk of ranking bus operators; no link to the law | §8.6, §4.3 (Road Transport Act 2018) |
| 13 | Database lacked hashes, location source, moderation, rules version, raw deletion | §8.3 |
| 14 | No tests for scene state, blur, or web platform (end-to-end, load) | §7 |
| 15 | No optional AI second opinion for candidate review | VLM check, with cost/privacy caveats (§6.9) |
| 16 | Users/goals sat at the end, after the tech | Moved to §2 |

**v2.0 → v2.1 (final logic check):**

| # | Problem in v2.0 | Fix in v2.1 |
|---|---|---|
| 1 | **E2 cancelled itself:** a bus blocking a lane creates a jam behind it, and E2 was blocked whenever the scene was `jam`. Real mid-road stops would be missed, and E6 could never fire | E2 judges only the traffic **ahead** of the bus; a jam behind it no longer cancels E2 (§6.3, §6.8) |
| 2 | Short clips (< 60 s) are `unknown`, so E1 could never report a jam, contradicting §6.1 | E1 accepts `unknown` with lower confidence (§6.2) |
| 3 | ~45 validation events per type is too few to tune thresholds or fit isotonic calibration | Location-wise cross-validation on candidates; Platt first, isotonic later (§6.0) |
| 4 | Test scores on ~45 events have wide error margins | 95% bootstrap confidence intervals (§7) |
| 5 | On a one-way road where most vehicles break the rule, the legal minority would be flagged | Large minority → "two-way traffic on a one-way road", no per-vehicle accusation (§6.4) |
