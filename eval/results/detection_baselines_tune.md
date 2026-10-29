## ผลการเปรียบเทียบ Detection Baselines (Split: tune)
- จำนวนภาพที่ทดสอบ: 84 ภาพ
- จำนวนเหรียญจริงทั้งหมด (Ground Truth): 479 เหรียญ

| วิธีการ (Method) | Precision | Recall | F1-Score | Mean Radius Error |
|---|:---:|:---:|:---:|:---:|
| **Proposed (Multi-cue + Watershed)** | 71.4% | 64.7% | 67.9% | 8.93% |
| Baseline A: No Watershed | 56.3% | 16.7% | 25.8% | 11.94% |
| Baseline B: K-Means | 53.7% | 15.2% | 23.7% | 11.60% |
| Baseline C: Hough Circles | 55.7% | 88.1% | 68.3% | 10.72% |

จำนวนที่ใช้คิด (TP / FP / GT): Proposed 310 / 124 / 479 · A 80 / 62 / 479 · B 73 / 63 / 479 · Hough 422 / 335 / 479
