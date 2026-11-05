# Dataset card

Record every dataset's licence **before** using it (PLAN §4.1). Most are research-only, which
matters if the platform becomes a product.

| Dataset | Version / URL | Licence | Commercial use? | Downloaded | Use | Notes |
|---|---|---|---|---|---|---|
| DhakaAI (2020) | [Harvard Dataverse doi:10.7910/DVN/POREXF](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/POREXF), [Kaggle](https://www.kaggle.com/datasets/rifat963/dhakaai-dhaka-based-traffic-detection-dataset) | GPL-2.0 (as listed by Dataset Ninja; confirm on Dataverse) | ⚠ unclear: copyleft may reach trained weights | no | detector | 3,953 images, 21 classes → unified (`--dataset dhakaai`). Hold until the licence is confirmed |
| Poribohon-BD | [Mendeley Data v2, doi:10.17632/pwyyg8zmk5.2](https://data.mendeley.com/datasets/pwyyg8zmk5/2) | CC BY 4.0 | yes, with attribution | no | detector (extra) | 9,058 images, 15 classes, VOC XML; mostly single-vehicle close-ups and augmented copies, faces blurred; 7.5 GB |
| BadODD | [Zenodo record 13823687](https://zenodo.org/records/13823687) ("complete"), paper [arXiv:2401.10659](https://arxiv.org/abs/2401.10659) | CC BY 4.0 | yes, with attribution | 2026-11-05 | detector (dashcam view) | 9,825 smartphone images from 9 districts incl. Dhaka, day + night; 13 classes; 4.36 GB, md5 6a0d3983b379302ab79a99baf7d47d74 |
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
