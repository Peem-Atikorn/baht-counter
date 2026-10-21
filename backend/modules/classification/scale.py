"""หาสเกล (มม./พิกเซล) จากขนาดเหรียญเทียบกันเอง (docs/plan.md หัวข้อ 1)

    cost(s) = Σ_i min_{t ∈ ชนิดที่เป็นไปได้ของเหรียญ i} min(|d_i·s − D_t| / D_t, COST_CAP)

cost เป็นฟังก์ชันเส้นตรงเป็นช่วง จุดต่ำสุดเฉพาะที่ (local minimum) อยู่ที่ s = D_t / d_i เสมอ
จึงหาค่าต่ำสุดจริงได้โดยลองทุกจุดนี้ ไม่ต้อง grid search
COST_CAP จำกัดโทษของวัตถุแปลกปลอมไม่ให้ดึงสเกลทั้งภาพ
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .coin_specs import COIN_SPECS

MAX_REL_ERR = 0.07          # คลาดเกินนี้ถือว่าไม่ตรงกับชนิดใด -> unknown
COST_CAP = 0.10             # โทษสูงสุดต่อเหรียญ
AMBIGUITY_MARGIN = 0.05     # คำตอบอื่นที่ cost ห่างจากดีที่สุดไม่เกินนี้ = ไม่แน่ใจ
GLOBAL_SCALE_RATIO = 1.06   # คำตอบอื่นที่สเกลต่างเกินนี้ = สเกลทั้งภาพไม่ชัด ต้องให้ผู้ใช้เลือก anchor
CLOSE_TYPES_MARGIN = 0.03   # ความคลาดของชนิดอันดับหนึ่งกับสองต่างกันน้อยกว่านี้ = ขนาดก้ำกึ่ง


@dataclass
class Assignment:
    scale: float
    cost: float
    types: list[str | None]           # None = เหรียญที่ไม่มีชนิดให้เลือก (ข้ามไป)
    errors: list[list[float]]         # ความคลาดสัมพัทธ์ของทุกชนิดที่เป็นไปได้ ตามลำดับใน candidates


@dataclass
class ScaleFit:
    best: Assignment | None
    ambiguous: set[int] = field(default_factory=set)   # index ของเหรียญที่ชนิดเปลี่ยนได้ในคำตอบอื่น
    global_ambiguous: bool = False


def assign_at_scale(diameters_px: list[float], candidates: list[list[str]], scale: float) -> Assignment:
    types: list[str | None] = []
    errors: list[list[float]] = []
    cost = 0.0
    for d, cands in zip(diameters_px, candidates):
        if not cands:
            types.append(None)
            errors.append([])
            continue
        errs = [abs(d * scale - COIN_SPECS[t].diameter_mm) / COIN_SPECS[t].diameter_mm for t in cands]
        k = int(np.argmin(errs))
        types.append(cands[k] if errs[k] <= MAX_REL_ERR else "unknown")
        errors.append(errs)
        cost += min(errs[k], COST_CAP)
    return Assignment(scale, cost, types, errors)


def candidate_scales(diameters_px: list[float], candidates: list[list[str]]) -> list[float]:
    scales = {COIN_SPECS[t].diameter_mm / d for d, cands in zip(diameters_px, candidates) for t in cands if d > 0}
    return sorted(scales)


def fit_scale(diameters_px: list[float], candidates: list[list[str]]) -> ScaleFit:
    scales = candidate_scales(diameters_px, candidates)
    if not scales:
        return ScaleFit(best=None)
    options = [assign_at_scale(diameters_px, candidates, s) for s in scales]
    # cost เท่ากันให้เลือกสเกลเล็กกว่า เพื่อให้ผลซ้ำได้
    best = min(options, key=lambda a: (round(a.cost, 9), a.scale))

    fit = ScaleFit(best=best)
    for alt in options:
        if alt.cost - best.cost > AMBIGUITY_MARGIN:
            continue
        diff = {i for i, (a, b) in enumerate(zip(best.types, alt.types)) if a != b}
        if not diff:
            continue
        fit.ambiguous |= diff
        if max(alt.scale / best.scale, best.scale / alt.scale) > GLOBAL_SCALE_RATIO:
            fit.global_ambiguous = True
    return fit
