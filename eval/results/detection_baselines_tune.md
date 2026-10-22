## ผลการเปรียบเทียบ Detection Baselines (Split: tune)
- จำนวนภาพที่ทดสอบ: 5 ภาพ
- จำนวนเหรียญจริงทั้งหมด (Ground Truth): 49 เหรียญ

| วิธีการ (Method) | Precision | Recall | F1-Score | Mean Radius Error |
|---|:---:|:---:|:---:|:---:|
| **Proposed (Multi-cue + Watershed)** | 97.7% | 85.7% | 91.3% | 11.51% |
| Baseline A: No Watershed | 72.7% | 16.3% | 26.7% | 11.77% |
| Baseline B: K-Means | 72.7% | 16.3% | 26.7% | 12.17% |
| Baseline C: Hough Circles | 35.3% | 83.7% | 49.7% | 15.57% |
