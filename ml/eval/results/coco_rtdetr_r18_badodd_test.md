# Detector evaluation — hf `COCO default`

Split `..\data\processed\badodd\test` · 2033 images · IoU 0.5 · operating threshold 0.3 · 2026-11-05

**mAP@50, all classes with ground truth:** 0.245 (95 % bootstrap CI 0.214–0.281, resampling 42 videos)

**mAP@50, classes the model can output** (person, bicycle, motorcycle, car, bus, truck): 0.409 (95 % CI 0.357–0.468)

| Class | GT boxes | AP@50 | Precision @op | Recall @op | Model can output it |
|---|---|---|---|---|---|
| person | 6325 | 0.660 | 0.436 | 0.720 | yes |
| bicycle | 256 | 0.127 | 0.077 | 0.543 | yes |
| rickshaw | 1984 | 0.000 | — | 0.000 | **no** |
| motorcycle | 1266 | 0.563 | 0.402 | 0.638 | yes |
| cng_autorickshaw | 3517 | 0.000 | — | 0.000 | **no** |
| car | 1236 | 0.614 | 0.181 | 0.790 | yes |
| bus | 620 | 0.340 | 0.209 | 0.597 | yes |
| truck | 782 | 0.149 | 0.103 | 0.520 | yes |
| ambulance | 66 | 0.000 | — | 0.000 | **no** |
| other | 57 | 0.000 | — | 0.000 | **no** |

## What the detector called each ground-truth object (at the operating threshold)

| Ground truth | Top predictions (share of GT boxes) |
|---|---|
| person | person 72%, missed 27%, car 1%, motorcycle 0% |
| bicycle | bicycle 51%, missed 37%, motorcycle 7%, person 4% |
| rickshaw | missed 51%, bicycle 17%, car 9%, person 9% |
| motorcycle | motorcycle 60%, missed 28%, person 7%, bicycle 3% |
| cng_autorickshaw | truck 34%, car 27%, missed 22%, bus 9% |
| car | car 67%, missed 17%, truck 13%, bus 2% |
| bus | bus 52%, missed 33%, truck 10%, car 5% |
| truck | truck 41%, missed 35%, car 16%, bus 7% |
| ambulance | truck 47%, car 41%, missed 8%, bus 3% |
| other | missed 67%, person 12%, truck 12%, motorcycle 4% |
