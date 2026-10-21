"""ส่วนที่ 3: จัดกลุ่มสี หาสเกล จำแนกชนิด และรวมยอด"""

from schemas import COIN_TYPES, COIN_TYPES_BY_CODE, Coin, CountResult, PreprocessResult


def classify_coins(
    pre: PreprocessResult,
    coins: list[Coin],
    anchor: tuple[int, str] | None = None,
) -> CountResult:
    """anchor = (coin_id, coin_type) ที่ผู้ใช้ยืนยัน ใช้คำนวณสเกลใหม่ทั้งภาพ

    TODO(ส่วนที่ 3): จัดกลุ่มสี HSV/YCbCr, หาสเกลด้วย cost(s) ตามหัวข้อ 1, needs_confirmation เมื่อสเกลไม่ชัด
    """
    raise NotImplementedError("classify_coins ยังไม่เสร็จ ใช้ mock_classify_coins ไปก่อน")


def total_baht(coins: list[Coin]) -> float | None:
    """ยอดรวม หรือ None ถ้ามีเหรียญที่ยังระบุมูลค่าไม่ได้"""
    if any(c.value_baht is None for c in coins):
        return None
    return round(sum(c.value_baht for c in coins), 2)


def mock_classify_coins(
    pre: PreprocessResult,
    coins: list[Coin],
    anchor: tuple[int, str] | None = None,
) -> CountResult:
    """ให้ชนิดเหรียญวนตามลำดับ coin_id และแสดง needs_confirmation ที่เหรียญสุดท้ายถ้ามีมากกว่า 1 เหรียญ"""
    out = []
    for c in coins:
        t = COIN_TYPES[c.coin_id % len(COIN_TYPES)]
        if anchor and anchor[0] == c.coin_id:
            t = COIN_TYPES_BY_CODE[anchor[1]]
        out.append(c.model_copy(update={
            "color_group": t.color_group,
            "coin_type": t.code,
            "value_baht": t.value_baht,
            "confidence": 0.9,
        }))
    if len(out) > 1 and not anchor:
        out[-1] = out[-1].model_copy(update={
            "coin_type": None,
            "value_baht": None,
            "confidence": None,
            "status": "needs_confirmation",
            "reason": "ตัวอย่างจาก mock: ระบบไม่แน่ใจชนิดของเหรียญนี้",
        })
    needs = any(c.status == "needs_confirmation" for c in out)
    h, w = pre.gray.shape[:2]
    return CountResult(
        image_size=(w, h),
        coins=out,
        total_baht=total_baht(out),
        scale_mm_per_px=None if needs else 0.1,
        scale_source="user_anchor" if anchor else ("inferred" if not needs else None),
        status="needs_confirmation" if needs else "ok",
        reason="กดเลือกชนิดของเหรียญที่มีเครื่องหมาย ? เพื่อให้ระบบคำนวณที่เหลือ" if needs else None,
    )
