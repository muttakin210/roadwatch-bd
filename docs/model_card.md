# Model card — RoadWatch BD (template, fill in during Phase 6)

**Versions:** detector `det-?` · rules `ev-0.1.0` (see `ml/configs/events.yaml`) · calibration `models/calibration.json`

## Intended use
Flag *possible* traffic incidents (jam, bus stopping mid-road, wrong-way driving) in uploaded
Bangladeshi road videos, for citizens, journalists and researchers. **Not** for automatic fines or
naming people/companies. Any official use requires human review of each case.

## Supported input (MVP)
Static or slightly shaky footbridge / roadside / CCTV video, daytime and dusk, ≤ 5 min, landscape preferred.
Night, rain and moving-vehicle footage: shown with a low-confidence warning.

## Metrics (PLAN §7) — report with 95 % bootstrap CIs, on the footbridge/roadside test set

| Part | Metric | Target | Result | 95 % CI |
|---|---|---|---|---|
| Detection | mAP@50 overall | ≥ 0.70 | | |
| Detection | AP@50 bus / rickshaw / CNG / car / motorcycle | ≥ 0.80 | | |
| Road | drivable IoU · kerb error (lane-widths) | ≥ 0.80 · ≤ 0.3 | | |
| Tracking | IDF1 | ≥ 0.65 | | |
| Blur | recall plates + faces | ≥ 95 % | | |
| Scene state | accuracy (signal queue vs jam) | ≥ 85 % | | |
| E1 | Cohen's κ | ≥ 0.6 | | |
| E2 | P / R | ≥ 0.80 / 0.70 | | |
| E3 | P / R | ≥ 0.85 / 0.65 | | |
| E2 / E3 | false alarms per hour | ≤ 2 / ≤ 1 | | |
| Calibration | ECE | ≤ 0.10 | | |
| System | s per video-minute (warm T4) | ≤ 90 | | |

Break down by day / dusk / night / rain, static / shaky / moving, landscape / portrait, and the held-out location.

## Baselines
(a) COCO detector without fine-tuning · (b) no stabilisation · (c) no scene-state step.

## Known limitations
- Kerb geometry assumes the camera looks roughly *along* the road.
- Wrong-way needs ≥ 8 moving tracks per road cell, a user arrow, a one-way hint, or a visible divider (left-hand-traffic rule).
- Distances are in bus-widths, not metres, unless the clip is calibrated.

## Error analysis
Every E2/E3 false positive, sorted by cause: road geometry · tracking · threshold · detector.
