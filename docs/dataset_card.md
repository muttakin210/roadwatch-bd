# Dataset card

Record every dataset's licence **before** using it (PLAN §4.1). Most are research-only, which
matters if the platform becomes a product.

| Dataset | Version / URL | Licence | Commercial use? | Downloaded | Use | Notes |
|---|---|---|---|---|---|---|
| DhakaAI (2020) | | ☐ check | ☐ | | detector | 21 classes → unified (`scripts/convert_datasets.py --dataset dhakaai`) |
| Poribohon-BD | | ☐ check | ☐ | | detector | 15 classes |
| BadODD | | ☐ check | ☐ | | detector (dashcam view) | day + night |
| IDD — India Driving Dataset | | ☐ check | ☐ | | road segmentation | registration required |
| UA-DETRAC | | ☐ check | ☐ | | tracker tuning / benchmark | |
| AI City Challenge | | ☐ check | ☐ | | benchmark | |
| BD licence-plate set(s) | | ☐ check | ☐ | | plate-blur model | |
| COCO | cocodataset.org | CC BY 4.0 (annotations); images: Flickr terms | | | pretrained weights | |
| **Own recordings** | `data/raw_videos` | own | yes | | detector / events / **test set** | public roads only; never publish unblurred |

## Own data
- Metadata per clip in `data/clips_index.csv`.
- Splits by **location and day**, never by random frame: 70 / 15 / 15, plus a hard test set
  (night, rain, dense jams) and one **held-out location** never used for tuning.
- The test set must be **footbridge/roadside** views (the platform's main input).

| Split | Locations | Days | Clips | Hours | Frames labelled | E2 | E3 | Jams |
|---|---|---|---|---|---|---|---|---|
| train | | | | | | | | |
| val | | | | | | | | |
| test | | | | | | | | |
| hard test | | | | | | | | |
| held-out location | | | | | | | | |
