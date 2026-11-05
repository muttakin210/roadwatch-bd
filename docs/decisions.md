# Phase 0 decisions (PLAN §15) — answer before Phase 1 ends

| # | Decision | Options | Answer | Date |
|---|---|---|---|---|
| 1 | **Open-source or closed?** | Open (AGPL) → Ultralytics YOLO OK · Closed → Apache-2.0 detector (RF-DETR, D-FINE, YOLOX, RT-DETR) or buy an Ultralytics licence | | |
| 2 | **Thesis/portfolio or product?** | Thesis → weight on §7 + write-up · Product → adoption, cost, moderation | | |
| 3 | **Who helps label?** | names, hours/week | | |
| 4 | **Night in or out of the MVP promise?** | Current: out (low-confidence warning only) | out | 2026-11-04 |

## Defaults chosen in the code until these are answered
- Detector default is `hf` (RT-DETR via Hugging Face Transformers, Apache-2.0), so nothing AGPL is
  pulled in by default. `--detector ultralytics` exists for prototyping, with a licence warning in `ml/roadwatch/detect.py`.
- Tracker: ByteTrack via `supervision` (MIT) when installed, else a simple IoU tracker (development only).
- Prototype backend uses SQLite + an in-process worker; Supabase + Redis/Celery + GPU worker in Phase 7.
