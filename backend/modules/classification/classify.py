"""ส่วนที่ 3: จัดกลุ่มสี + หาสเกล -> ชนิดเหรียญและยอดรวม"""
from __future__ import annotations

from schemas import Coin, CountResult, PreprocessResult

from .coin_specs import COIN_SPECS, GROUP_TYPES
from .color import color_groups
from .mock import total_baht
from .scale import CLOSE_TYPES_MARGIN, MAX_REL_ERR, assign_at_scale, fit_scale

# เหรียญสีเงินขนาดระหว่าง 1 กับ 5 บาท อาจเป็น 2 บาทสีเงินรุ่นเก่า (นอกขอบเขต)
OLD_2_BAHT_MM = (21.0, 22.8)

MSG_NO_COINS = "ไม่พบเหรียญในภาพ กรุณาถ่ายให้เห็นเหรียญชัดเจนบนพื้นสีเรียบ"
MSG_NEED_ANCHOR = "ระบบบอกขนาดจริงของเหรียญไม่ได้ กรุณากดเลือกชนิดของเหรียญ 1 เหรียญ เพื่อให้ระบบคำนวณที่เหลือ"
MSG_UNCERTAIN = "มีเหรียญ {n} เหรียญที่ระบบไม่แน่ใจ กรุณาตรวจสอบและเลือกชนิดเหรียญ"
MSG_COIN_SCALE = "ยังบอกชนิดไม่ได้จนกว่าจะรู้ขนาดจริง กรุณาเลือกชนิดของเหรียญ 1 เหรียญ"
MSG_COIN_UNKNOWN = "ขนาดหรือสีไม่ตรงกับเหรียญไทยชนิดใด (อาจเป็นเหรียญต่างประเทศหรือเหรียญที่ระลึก)"
MSG_COIN_BORDERLINE = "ขนาดก้ำกึ่งระหว่าง {a} กับ {b} กรุณาเลือกชนิดเหรียญ"
MSG_COIN_OLD_2_BAHT = "อาจเป็นเหรียญ 2 บาทสีเงินรุ่นเก่า กรุณาเลือกชนิดเหรียญ"


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


def classify_coins(pre: PreprocessResult, coins: list[Coin],
                   anchor: tuple[int, str] | None = None) -> CountResult:
    """จำแนกชนิดเหรียญทุกเหรียญและรวมยอดเงิน

    anchor = (coin_id, coin_type) ที่ผู้ใช้เลือก ใช้คำนวณสเกลจากเหรียญนั้นแทนการเดา
    เหรียญที่ source ไม่ใช่ estimated และมี coin_type แล้ว (ผู้ใช้แก้) จะคงชนิดเดิม
    และใช้เป็นข้อจำกัดตอนหาสเกล
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
        scale = None if need_anchor else best.scale
        scale_source = None if need_anchor else "inferred"

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

    return summarize(pre, out, scale, scale_source, need_anchor)
