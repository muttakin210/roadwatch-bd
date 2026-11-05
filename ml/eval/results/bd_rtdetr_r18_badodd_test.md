# Detector evaluation — hf `models/kaggle_run1/rtdetr_bd/best`

Split `..\data\processed\badodd\test` · 2033 images · IoU 0.5 · operating threshold 0.3 · 2026-11-05

**mAP@50, all classes with ground truth:** 0.663 (95 % bootstrap CI 0.607–0.718, resampling 42 videos)

**mAP@50, classes the model can output** (person, bicycle, rickshaw, motorcycle, cng_autorickshaw, car, bus, truck, ambulance, other): 0.663 (95 % CI 0.607–0.718)

| Class | GT boxes | AP@50 | Precision @op | Recall @op | Model can output it |
|---|---|---|---|---|---|
| person | 6325 | 0.756 | 0.490 | 0.798 | yes |
| bicycle | 256 | 0.504 | 0.340 | 0.637 | yes |
| rickshaw | 1984 | 0.828 | 0.526 | 0.860 | yes |
| motorcycle | 1266 | 0.769 | 0.563 | 0.800 | yes |
| cng_autorickshaw | 3517 | 0.877 | 0.651 | 0.887 | yes |
| car | 1236 | 0.805 | 0.511 | 0.828 | yes |
| bus | 620 | 0.758 | 0.343 | 0.831 | yes |
| truck | 782 | 0.678 | 0.462 | 0.748 | yes |
| ambulance | 66 | 0.518 | 0.231 | 0.682 | yes |
| other | 57 | 0.135 | 0.131 | 0.316 | yes |

## What the detector called each ground-truth object (at the operating threshold)

| Ground truth | Top predictions (share of GT boxes) |
|---|---|
| person | person 80%, missed 19%, rickshaw 1%, cng_autorickshaw 1% |
| bicycle | bicycle 59%, missed 25%, motorcycle 7%, rickshaw 6% |
| rickshaw | rickshaw 83%, missed 10%, cng_autorickshaw 4%, person 2% |
| motorcycle | motorcycle 78%, missed 16%, bicycle 2%, person 2% |
| cng_autorickshaw | cng_autorickshaw 86%, missed 7%, rickshaw 2%, person 1% |
| car | car 80%, missed 12%, cng_autorickshaw 3%, truck 2% |
| bus | bus 82%, missed 15%, truck 2%, car 1% |
| truck | truck 66%, missed 15%, bus 8%, cng_autorickshaw 5% |
| ambulance | ambulance 48%, car 21%, truck 12%, missed 8% |
| other | rickshaw 49%, missed 21%, other 12%, truck 9% |
