# Detector evaluation — hf `COCO default`

Split `..\data\processed\badodd_video\test` · 2034 images · IoU 0.5 · operating threshold 0.3 · 2026-11-05

**mAP@50, all classes with ground truth:** 0.198 (95 % bootstrap CI 0.191–0.207)

**mAP@50, classes the model can output** (person, bicycle, motorcycle, car, bus, truck): 0.330 (95 % CI 0.318–0.345)

| Class | GT boxes | AP@50 | Precision @op | Recall @op | Model can output it |
|---|---|---|---|---|---|
| person | 6115 | 0.539 | 0.408 | 0.608 | yes |
| bicycle | 264 | 0.105 | 0.092 | 0.492 | yes |
| rickshaw | 1911 | 0.000 | — | 0.000 | **no** |
| motorcycle | 1457 | 0.420 | 0.382 | 0.516 | yes |
| cng_autorickshaw | 2560 | 0.000 | — | 0.000 | **no** |
| car | 1233 | 0.500 | 0.186 | 0.648 | yes |
| bus | 752 | 0.249 | 0.212 | 0.427 | yes |
| truck | 973 | 0.171 | 0.150 | 0.501 | yes |
| ambulance | 104 | 0.000 | — | 0.000 | **no** |
| other | 55 | 0.000 | — | 0.000 | **no** |

## What the detector called each ground-truth object (at the operating threshold)

| Ground truth | Top predictions (share of GT boxes) |
|---|---|
| person | person 61%, missed 38%, car 0%, motorcycle 0% |
| bicycle | bicycle 46%, missed 43%, motorcycle 6%, person 4% |
| rickshaw | missed 59%, bicycle 14%, person 9%, motorcycle 7% |
| motorcycle | motorcycle 49%, missed 42%, person 5%, bicycle 2% |
| cng_autorickshaw | truck 36%, missed 29%, car 21%, bus 9% |
| car | car 54%, missed 30%, truck 13%, bus 3% |
| bus | missed 50%, bus 36%, truck 7%, car 7% |
| truck | truck 38%, missed 38%, car 14%, bus 9% |
| ambulance | car 47%, truck 29%, missed 20%, bus 4% |
| other | missed 73%, truck 9%, bicycle 7%, car 5% |
