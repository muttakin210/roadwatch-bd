# Detector evaluation — hf `COCO default`

Split `..\data\processed\badodd_paired\clean\test` · 1019 images · IoU 0.5 · operating threshold 0.3 · 2026-11-05

**mAP@50, all classes with ground truth:** 0.203 (95 % bootstrap CI 0.182–0.272, resampling 12 videos)

**mAP@50, classes the model can output** (person, bicycle, motorcycle, car, bus, truck): 0.338 (95 % CI 0.299–0.418)

| Class | GT boxes | AP@50 | Precision @op | Recall @op | Model can output it |
|---|---|---|---|---|---|
| person | 3085 | 0.546 | 0.414 | 0.609 | yes |
| bicycle | 139 | 0.103 | 0.101 | 0.518 | yes |
| rickshaw | 978 | 0.000 | — | 0.000 | **no** |
| motorcycle | 717 | 0.414 | 0.374 | 0.517 | yes |
| cng_autorickshaw | 1290 | 0.000 | — | 0.000 | **no** |
| car | 611 | 0.505 | 0.181 | 0.645 | yes |
| bus | 377 | 0.278 | 0.228 | 0.467 | yes |
| truck | 473 | 0.180 | 0.146 | 0.514 | yes |
| ambulance | 56 | 0.000 | — | 0.000 | **no** |
| other | 31 | 0.000 | — | 0.000 | **no** |

## What the detector called each ground-truth object (at the operating threshold)

| Ground truth | Top predictions (share of GT boxes) |
|---|---|
| person | person 61%, missed 38%, car 0%, truck 0% |
| bicycle | bicycle 49%, missed 40%, motorcycle 6%, person 4% |
| rickshaw | missed 58%, bicycle 13%, person 9%, motorcycle 7% |
| motorcycle | motorcycle 49%, missed 42%, person 5%, bicycle 3% |
| cng_autorickshaw | truck 37%, missed 27%, car 21%, bus 9% |
| car | car 54%, missed 29%, truck 13%, bus 4% |
| bus | missed 46%, bus 39%, truck 7%, car 7% |
| truck | truck 41%, missed 35%, car 15%, bus 8% |
| ambulance | car 54%, truck 30%, missed 14%, bus 2% |
| other | missed 77%, truck 10%, bicycle 6%, bus 3% |
