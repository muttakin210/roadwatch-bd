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

### Public deployment (Vercel + this PC)

The website runs on Vercel (`vercel.json`: one public service, `web`). The backend stays on this PC: the
pipeline needs minutes of CPU per video, a persistent disk and background processing, which Vercel
functions don't provide. `web/proxy.ts` forwards `/api/*` to `ROADWATCH_API` with a shared secret.

```
browser ──https──▶ Vercel (web) ──proxy.ts + secret──▶ Cloudflare tunnel ──▶ uvicorn :8000 on this PC
```

- Secret: `data/platform/proxy_secret.txt` (git-ignored). The backend started with
  `ROADWATCH_PROXY_SECRET` refuses every request without it, so the tunnel URL alone is useless.
- Vercel env (production + preview): `ROADWATCH_API` = tunnel URL, `ROADWATCH_PROXY_SECRET`.
- The site only works while this PC, the backend and the tunnel are running.

Start (Git Bash, from the repo root):

```bash
export ROADWATCH_PROXY_SECRET="$(tr -d '\r\n' < data/platform/proxy_secret.txt)"
(cd backend && ../ml/.venv/Scripts/python -m uvicorn app:app --port 8000) &
"/c/Program Files (x86)/cloudflared/cloudflared.exe" tunnel --no-autoupdate --url http://127.0.0.1:8000
# a quick tunnel gets a NEW https://….trycloudflare.com address each start: point Vercel at it
printf '%s' "https://<new>.trycloudflare.com" | vercel env add ROADWATCH_API production --force
vercel deploy --prod
```

A permanent address needs a named Cloudflare tunnel on your own domain (free Cloudflare account).

### Road map, news and fines

- **Fines** (`backend/fine_rules.py`): each AI event type maps to the rule it breaks in the Road Transport
  Act 2018. The police/admin form is pre-filled with that rule's legal maximum, and the backend refuses
  anything higher. A reviewer and then police/admin still confirm every case, so nothing is fined automatically.
  `test_fine_rules.py` keeps these in step with the traffic rules page (`web/lib/rules.ts`).
- **News** (`backend/news.py`): headlines and links only, from the RSS feeds of The Daily Star, Prothom Alo
  (Bangla and English), TBS, Jagonews24 and BBC Bangla, refreshed every 2 hours. `ROADWATCH_NEWS=0` turns it off.
- **Live traffic (Google Maps)**: create a Maps JavaScript API key in Google Cloud (billing must be enabled;
  there is a free monthly credit). Restrict it to HTTP referrers `https://roadwatch-bd-alpha.vercel.app/*` and
  `http://localhost:3000/*`, and to the Maps JavaScript API only. Then set it on Vercel and redeploy:
  `printf '%s' "<key>" | vercel env add NEXT_PUBLIC_GOOGLE_MAPS_KEY production --force; vercel deploy --prod`.
  Without a key the map shows OpenStreetMap.
- **Live traffic without Google billing (TomTom)**: a free TomTom developer key (no card; about 50,000 map tiles
  a day) adds TomTom's live traffic-flow colours on top of the OpenStreetMap map:
  `printf '%s' "<key>" | vercel env add NEXT_PUBLIC_TOMTOM_KEY production --force; vercel deploy --prod`.
  If both keys are set, Google is used. Live traffic and RoadWatch incidents refresh every 2 minutes while the
  page is open. Live road speeds always need one of these providers: there is no free keyless source.
- **Offline map pack**: Google's terms don't allow saving Google map data offline, so the offline map is an
  OpenStreetMap extract of Bangladesh. Build it once with the [pmtiles CLI](https://github.com/protomaps/go-pmtiles/releases)
  from the newest [Protomaps build](https://maps.protomaps.com/builds/):
  ```bash
  pmtiles extract https://build.protomaps.com/<YYYYMMDD>.pmtiles data/platform/maps/bd.pmtiles \
      --bbox=88.0,20.55,92.7,26.65 --maxzoom=14
  ```
  The backend serves it at `/api/map/offline/bd.pmtiles`, and the map page offers "Save map for offline".
- **Place search** works offline from `web/public/geo/bd-places.json` (GeoNames, CC BY 4.0, about 50,000 places).
  It lacks many Dhaka neighbourhoods and landmarks (for example Farmgate).

### Look per platform

`app/layout.tsx` tags `<html data-os="ios|android|mac|windows|linux">` before the first paint, and
`globals.css` gives each platform its system font (SF, Roboto, Segoe UI Variable), corner radius and touch-target
size. On phones the main sections move to a bottom tab bar (iOS style on iPhone, Material 3 style on Android).
Animations are slow and faint, and stop for people who turn on "reduce motion".

### Cross-browser tests

`playwright.config.ts` has one project per platform: `android` (Pixel 7), `iphone`, `ipad`,
`windows-linux-chrome`, `edge`, `mac-safari`, `firefox`. The slow upload test runs on the phones only.

```powershell
npx playwright install webkit firefox
# many sign-ups from one IP trip the login limit: raise it for the test backend only
$env:ROADWATCH_AUTH_LIMIT=500; ..\ml\.venv\Scripts\uvicorn app:app --port 8000   # in backend/
npx playwright test e2e/pwa.spec.ts e2e/accounts.spec.ts e2e/admin.spec.ts
```

While the public site's backend holds port 8000, run the tests on other ports:
`E2E_API_PORT=8100 E2E_WEB_PORT=3100 npx playwright test --workers=3`.

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
