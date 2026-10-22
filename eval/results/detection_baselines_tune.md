## ผลการเปรียบเทียบ Detection Baselines (Split: tune)
- จำนวนภาพที่ทดสอบ: 84 ภาพ
- จำนวนเหรียญจริงทั้งหมด (Ground Truth): 479 เหรียญ

| วิธีการ (Method) | Precision | Recall | F1-Score | Mean Radius Error |
|---|:---:|:---:|:---:|:---:|
| **Proposed (Multi-cue + Watershed)** | **54.0%** | **62.2%** | **57.8%** | **9.93%** |
| Baseline A: No Watershed | 43.0% | 19.8% | 27.1% | 11.13% |
| Baseline B: K-Means | 43.4% | 19.8% | 27.2% | 11.71% |
| Baseline C: Hough Circles | 25.3% | 84.8% | 39.0% | 10.39% |

จำนวนที่ใช้คิด (TP / FP / GT): Proposed 298 / 254 / 479 · A 95 / 126 / 479 · B 95 / 124 / 479 · Hough 406 / 1198 / 479
