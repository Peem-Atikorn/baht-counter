"""ส่วนที่ 3: จัดกลุ่มสี + หาสเกล -> ชนิดเหรียญและยอดรวม"""
from __future__ import annotations

import cv2

from schemas import Coin, CountResult, PreprocessResult

from .coin_specs import COIN_SPECS, GROUP_TYPES
from .color import color_groups
from .mock import total_baht
from .scale import CLOSE_TYPES_MARGIN, MAX_REL_ERR, Assignment, assign_at_scale, fit_scale
from .template import MIN_MARGIN as TEMPLATE_MIN_MARGIN
from .template import Templates, decide, match_scores

# เหรียญสีเงินขนาดระหว่าง 1 กับ 5 บาท อาจเป็น 2 บาทสีเงินรุ่นเก่า (นอกขอบเขต)
OLD_2_BAHT_MM = (21.0, 22.8)

MSG_NO_COINS = "ไม่พบเหรียญในภาพ กรุณาถ่ายให้เห็นเหรียญชัดเจนบนพื้นสีเรียบ"
MSG_NEED_ANCHOR = "ระบบบอกขนาดจริงของเหรียญไม่ได้ กรุณากดเลือกชนิดของเหรียญ 1 เหรียญ เพื่อให้ระบบคำนวณที่เหลือ"
MSG_UNCERTAIN = "มีเหรียญ {n} เหรียญที่ระบบไม่แน่ใจ กรุณาตรวจสอบและเลือกชนิดเหรียญ"
MSG_COIN_SCALE = "ยังบอกชนิดไม่ได้จนกว่าจะรู้ขนาดจริง กรุณาเลือกชนิดของเหรียญ 1 เหรียญ"
MSG_COIN_UNKNOWN = "ขนาดหรือสีไม่ตรงกับเหรียญไทยชนิดใด (อาจเป็นเหรียญต่างประเทศหรือเหรียญที่ระลึก)"
MSG_COIN_BORDERLINE = "ขนาดก้ำกึ่งระหว่าง {a} กับ {b} กรุณาเลือกชนิดเหรียญ"
MSG_COIN_OLD_2_BAHT = "อาจเป็นเหรียญ 2 บาทสีเงินรุ่นเก่า กรุณาเลือกชนิดเหรียญ"
MSG_TEMPLATE_GUESS = "ระบบเดาชนิดเหรียญจากลวดลาย กรุณาตรวจสอบและยืนยันชนิดเหรียญ"
MSG_COIN_TEMPLATE = "ระบบเดาชนิดจากลวดลาย กรุณาตรวจสอบ"


def diameter_px(coin: Coin) -> float:
    """เส้นผ่านศูนย์กลางใช้แกนยาวของวงรี เพื่อรองรับภาพที่ถ่ายเอียง"""
    return coin.ellipse[0] if coin.ellipse is not None else 2 * coin.radius_px


def _image_size(pre: PreprocessResult) -> tuple[int, int]:
    if pre.image is None:
        return pre.original_size
    h, w = pre.image.shape[:2]
    return (w, h)


def _failed(pre: PreprocessResult, coins: list[Coin], reason: str) -> CountResult:
    return CountResult(
        image_size=_image_size(pre), coins=coins, total_baht=None,
        scale_mm_per_px=None, scale_source=None, status="failed", reason=reason,
    )


def _confidence(errs: list[float]) -> float:
    """ใกล้ขนาดจริงแค่ไหน และห่างจากชนิดอันดับสองแค่ไหน (0-1)"""
    e = sorted(errs)
    fit = max(0.0, 1 - e[0] / MAX_REL_ERR)
    if len(e) == 1:
        return round(fit, 3)
    sep = (e[1] - e[0]) / (e[1] + e[0] + 1e-9)
    return round(min(fit, sep), 3)


def summarize(pre: PreprocessResult, coins: list[Coin], scale: float | None,
              scale_source: str | None, need_anchor: bool = False) -> CountResult:
    """รวมยอดเงินและสถานะของทั้งภาพจากผลรายเหรียญ ใช้ซ้ำได้หลังผู้ใช้แก้ผล"""
    if not coins:
        return _failed(pre, coins, MSG_NO_COINS)
    # มีเหรียญที่ไม่รู้มูลค่า (ยังตัดสินไม่ได้ หรือ unknown) ยอดรวมเป็น None จนกว่าผู้ใช้จะแก้หรือลบเหรียญนั้น
    total = total_baht(coins)
    n_uncertain = sum(c.status != "ok" for c in coins)
    if need_anchor:
        status, reason = "needs_confirmation", MSG_NEED_ANCHOR
    elif n_uncertain:
        status, reason = "needs_confirmation", MSG_UNCERTAIN.format(n=n_uncertain)
    else:
        status, reason = "ok", None
    return CountResult(
        image_size=_image_size(pre), coins=coins, total_baht=total,
        scale_mm_per_px=scale, scale_source=scale_source, status=status, reason=reason,
    )


def _template_anchor(pre: PreprocessResult, coins: list[Coin], diams: list[float],
                     candidates: list[list[str]], ambiguous: set[int],
                     templates: Templates) -> tuple[int, str, float, Assignment] | None:
    """เหรียญที่ลวดลายบอกชนิดได้ชัดที่สุดในกลุ่มที่สเกลไม่ชัด -> (index, ชนิด, ระยะห่างคะแนน, ผลที่สเกลนั้น)

    ใช้ได้เฉพาะเมื่อทุกเหรียญที่ลวดลายตัดสินได้ ได้ชนิดตรงกับที่สเกลจาก anchor นี้ให้ ถ้าขัดกันคืน None
    """
    gray = pre.gray if pre.gray is not None else cv2.cvtColor(pre.image, cv2.COLOR_BGR2GRAY)
    decided = []
    for i in sorted(ambiguous):
        if len(candidates[i]) < 2:
            continue
        d = decide(match_scores(gray, coins[i], templates, candidates[i]))
        if d is not None:
            decided.append((i, *d))
    if not decided:
        return None
    idx, code, margin = max(decided, key=lambda d: d[2])
    cand = list(candidates)
    cand[idx] = [code]
    best = assign_at_scale(diams, cand, COIN_SPECS[code].diameter_mm / diams[idx])
    if any(best.types[i] != c for i, c, _ in decided):
        return None
    return idx, code, margin, best


def _label(coins: list[Coin], feats: list, diams: list[float], candidates: list[list[str]],
           fixed: dict[int, str], best: Assignment, ambiguous: set[int], need_anchor: bool,
           anchor_idx: int | None) -> list[Coin]:
    out: list[Coin] = []
    for i, (c, f) in enumerate(zip(coins, feats)):
        size_mm = diams[i] * best.scale
        upd: dict = {"color_group": f.group}
        if i in fixed:
            t = fixed[i]
            spec = COIN_SPECS.get(t)
            upd.update(
                coin_type=t, value_baht=spec.value_baht if spec else None,
                color_group=spec.color_group if spec else f.group,
                confidence=1.0, status="ok", reason=None,
                source="user_edited" if i == anchor_idx and c.source == "estimated" else c.source,
            )
        elif i in ambiguous and need_anchor:
            upd.update(coin_type=None, value_baht=None, confidence=None,
                       status="needs_confirmation", reason=MSG_COIN_SCALE)
        elif not need_anchor and f.group == "silver" and OLD_2_BAHT_MM[0] <= size_mm <= OLD_2_BAHT_MM[1]:
            upd.update(coin_type=None, value_baht=None, confidence=None,
                       status="needs_confirmation", reason=MSG_COIN_OLD_2_BAHT)
        elif best.types[i] == "unknown":
            upd.update(coin_type="unknown", value_baht=None, confidence=None,
                       status="needs_confirmation", reason=MSG_COIN_UNKNOWN)
        else:
            t = best.types[i]
            errs = best.errors[i]
            upd.update(coin_type=t, value_baht=COIN_SPECS[t].value_baht, confidence=_confidence(errs),
                       status="ok", reason=None)
            # ชนิดอันดับหนึ่งกับสองใกล้กันมาก หรือสเกลใกล้เคียงให้ชนิดอื่น -> ให้ผู้ใช้ยืนยัน (ยังเดาชนิดไว้)
            ranked = sorted(zip(errs, candidates[i]))
            if len(ranked) > 1 and (i in ambiguous or ranked[1][0] - ranked[0][0] < CLOSE_TYPES_MARGIN):
                upd.update(status="needs_confirmation", reason=MSG_COIN_BORDERLINE.format(
                    a=COIN_SPECS[ranked[0][1]].name_th, b=COIN_SPECS[ranked[1][1]].name_th))
            elif i in ambiguous:
                upd.update(status="needs_confirmation", reason=MSG_UNCERTAIN.format(n=1))
        out.append(c.model_copy(update=upd))
    return out


def _template_guess(pre: PreprocessResult, coins: list[Coin], feats: list, diams: list[float],
                    candidates: list[list[str]], fixed: dict[int, str], ambiguous: set[int],
                    idx: int, code: str, margin: float, best: Assignment) -> CountResult:
    """ใช้ชนิดที่ลวดลายบอกเป็น anchor แต่เป็นแค่การเดา: เติมชนิดให้ แล้วให้ผู้ใช้ยืนยันเหรียญที่ชนิดขึ้นกับสเกล"""
    cand = list(candidates)
    cand[idx] = [code]
    out = _label(coins, feats, diams, cand, {**fixed, idx: code}, best, set(), False, None)
    for i in ambiguous | {idx}:
        c = out[i]
        if c.source != "estimated" or c.coin_type not in COIN_SPECS:
            continue
        conf = c.confidence if i != idx else 1.0
        conf = min(conf, margin / (2 * TEMPLATE_MIN_MARGIN), 0.5)
        out[i] = c.model_copy(update=dict(confidence=round(conf, 3), status="needs_confirmation",
                                          reason=MSG_COIN_TEMPLATE))
    # อย่างน้อยเหรียญ idx เป็น needs_confirmation เสมอ จึงแทน reason ของทั้งภาพได้เลย
    return summarize(pre, out, best.scale, "inferred").model_copy(update=dict(reason=MSG_TEMPLATE_GUESS))


def classify_coins(pre: PreprocessResult, coins: list[Coin],
                   anchor: tuple[int, str] | None = None,
                   templates: Templates | None = None) -> CountResult:
    """จำแนกชนิดเหรียญทุกเหรียญและรวมยอดเงิน

    anchor = (coin_id, coin_type) ที่ผู้ใช้เลือก ใช้คำนวณสเกลจากเหรียญนั้นแทนการเดา
    เหรียญที่ source ไม่ใช่ estimated และมี coin_type แล้ว (ผู้ใช้แก้) จะคงชนิดเดิม
    และใช้เป็นข้อจำกัดตอนหาสเกล
    templates (ไม่บังคับ, จาก build_templates) ถ้าสเกลไม่ชัดและลวดลายบอกชนิดได้ชัดและไม่ขัดกัน
    เติมชนิดที่เดาไว้ให้ แต่สถานะยังเป็น needs_confirmation ให้ผู้ใช้ยืนยัน
    """
    if pre.status == "failed" or pre.image is None:
        return _failed(pre, coins, pre.reason or "ประมวลผลภาพไม่สำเร็จ")
    if not coins:
        return _failed(pre, coins, MSG_NO_COINS)

    fixed: dict[int, str] = {
        i: c.coin_type for i, c in enumerate(coins)
        if c.source != "estimated" and c.coin_type is not None
    }
    anchor_idx = None
    if anchor is not None:
        coin_id, anchor_type = anchor
        if anchor_type not in COIN_SPECS:
            raise ValueError(f"anchor coin_type ไม่ถูกต้อง: {anchor_type}")
        anchor_idx = next((i for i, c in enumerate(coins) if c.coin_id == coin_id), None)
        if anchor_idx is None:
            raise ValueError(f"ไม่พบเหรียญ coin_id={coin_id}")
        fixed[anchor_idx] = anchor_type

    feats = color_groups(pre.image, coins)
    diams = [diameter_px(c) for c in coins]
    candidates = [
        ([fixed[i]] if fixed[i] in COIN_SPECS else []) if i in fixed else GROUP_TYPES[f.group]
        for i, f in enumerate(feats)
    ]

    if anchor_idx is not None:
        scale = COIN_SPECS[fixed[anchor_idx]].diameter_mm / diams[anchor_idx]
        best = assign_at_scale(diams, candidates, scale)
        ambiguous, need_anchor, scale_source = set(), False, "user_anchor"
    else:
        fit = fit_scale(diams, candidates)
        if fit.best is None:
            return _failed(pre, coins, MSG_NO_COINS)
        best, ambiguous, need_anchor = fit.best, fit.ambiguous, fit.global_ambiguous
        if need_anchor and templates:
            auto = _template_anchor(pre, coins, diams, candidates, ambiguous, templates)
            if auto is not None:
                return _template_guess(pre, coins, feats, diams, candidates, fixed, ambiguous, *auto)
        scale = None if need_anchor else best.scale
        scale_source = None if need_anchor else "inferred"

    out = _label(coins, feats, diams, candidates, fixed, best, ambiguous, need_anchor, anchor_idx)
    return summarize(pre, out, scale, scale_source, need_anchor)
