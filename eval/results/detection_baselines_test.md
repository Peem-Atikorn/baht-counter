## ผลการเปรียบเทียบ Detection Baselines (Split: test)
- จำนวนภาพที่ทดสอบ: 43 ภาพ
- จำนวนเหรียญจริงทั้งหมด (Ground Truth): 212 เหรียญ

| วิธีการ (Method) | Precision | Recall | F1-Score | Mean Radius Error |
|---|:---:|:---:|:---:|:---:|
| **Proposed (Multi-cue + Watershed)** | 67.2% | 59.0% | 62.8% | 8.40% |
| Baseline A: No Watershed | 31.2% | 7.1% | 11.5% | 14.86% |
| Baseline B: K-Means | 31.2% | 7.1% | 11.5% | 15.18% |
| Baseline C: Hough Circles | 55.2% | 92.5% | 69.1% | 9.54% |

จำนวนที่ใช้คิด (TP / FP / GT): Proposed 125 / 61 / 212 · A 15 / 33 / 212 · B 15 / 33 / 212 · Hough 196 / 159 / 212
