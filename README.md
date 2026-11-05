# RoadWatch BD

Finds unusual road problems in Bangladeshi traffic videos: **traffic jams (E1)**, **buses stopping
mid-road (E2)** and **wrong-way driving (E3)**. It returns a blurred, annotated video and an
`events.json` with a plain-language reason and a confidence for every event. See **[PLAN.md](PLAN.md)**.

## Status: Phase 0–1 code (what exists now)

| Part | File | State |
|---|---|---|
| Pre-processing (ffprobe allow-list, ffmpeg normalise, 15 fps) | `ml/roadwatch/preprocess.py` | ✅ needs ffmpeg on PATH |
| Camera motion (ORB + RANSAC → static/shaky/moving, stabilise) | `ml/roadwatch/camera_motion.py` | ✅ tested |
| Detector interface + backends (HF RT-DETR, RF-DETR, Ultralytics) | `ml/roadwatch/detect.py` | ✅ COCO weights; BD fine-tune = Phase 3 |
| Tracking (ByteTrack / IoU), Kalman smoothing, stopped state, **stitching** | `ml/roadwatch/track.py` | ✅ tested |
| Road (heat-map kerbs, user edge taps) | `ml/roadwatch/road.py` | ✅ segmentation model = Phase 4 |
| Flow field (leave-one-out, arrows, LHT rule, ambiguity) | `ml/roadwatch/flow.py` | ✅ tested |
| Scene state (flowing / signal_queue / jam / unknown) | `ml/roadwatch/events/scene_state.py` | ✅ tested |
| E1 / E2 / E3 / U-turn / one-way rules, merge, calibration | `ml/roadwatch/events/` | ✅ tested |
| Privacy blur (YuNet faces, plate hook, safety net) | `ml/roadwatch/privacy.py` | ⚠ plate model = Phase 3 |
| Render + end-to-end pipeline + CLI | `ml/roadwatch/render.py`, `pipeline.py` | ✅ tested on synthetic video |
| Scripts: dataset mapping, frame sampling, candidate mining, calibration | `ml/scripts/` | ✅ |
| Prototype API (resumable chunked upload, SSE progress, feedback, report) | `backend/` | ✅ SQLite + thread worker |
| Web app: upload (trim, 720p in-browser compression, resumable), map pin, direction arrows, live progress, results timeline, feedback, downloads, share, report, Bangla + English | `web/` | ✅ Playwright e2e |

**Not done, and can't be done in code:** recording footage, labelling, training the BD detector,
plate model and segmentation model, tuning thresholds on real data, and the §15 decisions
(`docs/decisions.md`). Every threshold in `ml/configs/events.yaml` is a starting value from the
plan. None has been tuned on real Dhaka video yet.

## Setup (Windows)

```powershell
cd "D:\Traffic AI model project\ml"
python -m venv .venv --system-site-packages
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m pytest -q          # rule unit tests + end-to-end smoke test, no GPU
```

Install **ffmpeg** (`winget install Gyan.FFmpeg`) for real uploads. Without it the pipeline refuses to
run unless you pass `--allow-no-ffmpeg`, which skips validation and rotation handling and is for development only.

## First step this week (PLAN §11)

Record one 5-minute footbridge clip, then:

```powershell
cd ml
.venv\Scripts\python -m roadwatch.pipeline D:\clips\farmgate_01.mp4 --out ..\data\processed\farmgate_01 --detector hf
```

Open `annotated.mp4` to see the track trails and the problems on real Dhaka traffic. Optional
hints file (`--hints hints.json`), using analysis-frame pixel coordinates (long side 1280):

```json
{"camera_along_road": true,
 "arrows": [[400, 650, 400, 200], [880, 200, 880, 650]],
 "road_edges": {"left": [[180, 120], [60, 719]], "right": [[1100, 120], [1240, 719]],
                "divider": [[640, 120], [640, 719]]}}
```

## Prototype platform

```powershell
cd backend
..\ml\.venv\Scripts\pip install -r requirements.txt
..\ml\.venv\Scripts\uvicorn app:app --reload      # http://127.0.0.1:8000
```

Then the web app (second terminal):

```powershell
cd web
npm install
npm run build; npm start            # http://localhost:3000 (proxies /api to :8000; set ROADWATCH_API to change)
npx playwright test                 # end-to-end: starts both servers, uploads a clip, waits for results
```

The bare page at http://127.0.0.1:8000 still works for quick checks.

Env: `ROADWATCH_DETECTOR=hf|rfdetr|ultralytics`, `ROADWATCH_DAILY_LIMIT=20`, `ROADWATCH_ALLOW_NO_FFMPEG=1` (dev only),
`ROADWATCH_SECURE_COOKIE=1` (behind HTTPS), `ROADWATCH_AUTH_LIMIT=10` (login/sign-up attempts per IP per 15 min).

First admin: sign up on the site, then `cd backend; ..\ml\.venv\Scripts\python manage.py set-role you@example.com admin`.

### Install as an app (Android, iOS, Windows, macOS, Linux)

The site is a Progressive Web App: one codebase, installed from the browser, no app store.

| Platform | Browser | How |
|---|---|---|
| Android | Chrome, Edge, Samsung Internet | the site offers **Install**, or menu → *Install app* |
| iPhone / iPad | Safari | Share → *Add to Home Screen* (the site shows this hint) |
| Windows | Chrome, Edge | install icon in the address bar, or the site's **Install** button |
| macOS | Chrome, Edge; Safari 17+ | install icon; in Safari: File → *Add to Dock* |
| Linux / ChromeOS | Chrome, Edge, Chromium | install icon in the address bar |

Installing needs **HTTPS** (plain http works only on `localhost`), so other devices can open the site over
the LAN (`http://<this-pc-ip>:3000`) but can only install it once it's deployed behind HTTPS.
The service worker (`web/public/sw.js`) caches only the app shell; `/api/` (videos, results, accounts)
is never cached.

### Cross-browser tests

`playwright.config.ts` has one project per platform: `android` (Pixel 7), `iphone`, `ipad`,
`windows-linux-chrome`, `edge`, `mac-safari`, `firefox`. The slow upload test runs on the phones only.

```powershell
npx playwright install webkit firefox
# many sign-ups from one IP trip the login limit: raise it for the test backend only
$env:ROADWATCH_AUTH_LIMIT=500; ..\ml\.venv\Scripts\uvicorn app:app --port 8000   # in backend/
npx playwright test e2e/pwa.spec.ts e2e/accounts.spec.ts e2e/admin.spec.ts
```

Playwright's WebKit build for Windows can't decode H.264 (real Safari can), so on `iphone` the upload
test takes the "browser can't preview this video" path: upload without trim/arrows.

## Data loop
1. `scripts/sample_frames.py` → frames to label in CVAT (follow `docs/annotation_guideline.md`).
2. `scripts/convert_datasets.py` → DhakaAI / Poribohon-BD / BadODD to the unified classes.
3. `scripts/mine_candidates.py` → loose-threshold candidates CSV; a person fills `verdict`.
4. `scripts/fit_calibration.py` → location-wise CV ECE + `models/calibration.json`.

## Training the Bangladeshi detector
BadODD (CC BY 4.0, 9,825 road images from 9 districts) is the first training set; licences of
all candidate datasets are in `docs/dataset_card.md`.

```
cd ml
# BadODD from Zenodo record 13823687 → data/datasets/badodd/extracted, then:
python scripts/convert_datasets.py --dataset badodd --src ../data/datasets/badodd/extracted --dst ../data/processed/badodd
python scripts/train_detector.py --data ../data/processed/badodd --out models/rtdetr_bd     # needs a GPU
python -m roadwatch.pipeline clip.mp4 --out ../data/processed/test --weights models/rtdetr_bd/best --fresh
```

No GPU here? Run `ml/notebooks/train_rtdetr_kaggle.ipynb` on Kaggle (free T4): it downloads
BadODD, converts it, trains and gives you `rtdetr_bd_best.zip` to unzip into `ml/models/`.

Known limits: BadODD's "Auto Rickshaw" mixes CNGs, easybikes and legunas, so all become
`cng_autorickshaw`; it has no leguna or rickshaw-van class; and it is dashcam footage, so
check the model on footbridge clips before trusting it.
