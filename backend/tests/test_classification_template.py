"""เทสต์ template matching ของส่วนที่ 3 ด้วยเหรียญสังเคราะห์ที่มีลวดลาย (ตัวเลข + จุดไม่สมมาตร)"""
import cv2
import numpy as np

from modules.classification import build_templates, classify_coins, match_scores
from modules.classification.template import _ncc_max, coin_features, decide
from schemas import Coin, PreprocessResult

SILVER = (175, 178, 182)
BG = 110
LABELS = {"THB_1": "1", "THB_5": "5"}


def _face_patch(r, text, angle, tilt=None):
    """เหรียญเงินมีตัวเลขกลางเหรียญ หมุน angle องศา และ (ถ้ามี) บีบเป็นวงรี tilt = (อัตราแกนสั้น/ยาว, มุม)"""
    s = int(2 * r + 8)
    c = s / 2
    p = np.full((s, s, 3), BG, np.uint8)
    cv2.circle(p, (round(c), round(c)), round(r), SILVER, -1)
    if text:
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        k = r / th
        cv2.putText(p, text, (round(c - tw * k / 2), round(c + th * k / 2)), cv2.FONT_HERSHEY_SIMPLEX,
                    k, (60, 60, 60), max(2, round(k * 2)))
        cv2.circle(p, (round(c + 0.62 * r), round(c - 0.35 * r)), max(2, round(0.1 * r)), (60, 60, 60), -1)
    m = cv2.getRotationMatrix2D((c, c), angle, 1.0)
    if tilt is not None:
        q, phi = tilt
        rot = cv2.getRotationMatrix2D((c, c), phi, 1.0)
        a = rot[:, :2].T @ np.diag([1.0, q]) @ rot[:, :2] @ m[:, :2]
        m = np.hstack([a, (np.array([c, c]) - a @ np.array([c, c]))[:, None]])
    return cv2.warpAffine(p, m, (s, s), borderValue=(BG, BG, BG))


def make_faces(specs, seed=0):
    """specs = [(code หรือ None, รัศมี, มุม, tilt)] วางเรียงแถว คืน (PreprocessResult, list[Coin])"""
    rng = np.random.default_rng(seed)
    w = int(sum(2 * r + 30 for _, r, _, _ in specs)) + 30
    h = int(2 * max(r for _, r, _, _ in specs)) + 60
    img = np.full((h, w, 3), BG, np.uint8)
    coins, x = [], 30
    for i, (code, r, angle, tilt) in enumerate(specs):
        p = _face_patch(r, LABELS.get(code, ""), angle, tilt)
        y0 = (h - p.shape[0]) // 2
        img[y0:y0 + p.shape[0], x:x + p.shape[1]] = p
        cx, cy = x + p.shape[1] / 2, y0 + p.shape[0] / 2
        ellipse = None if tilt is None else (2 * r, 2 * r * tilt[0], float(tilt[1]))
        coins.append(Coin(coin_id=i, center_xy=(cx, cy), radius_px=r, ellipse=ellipse))
        x += p.shape[1] + 22
    img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return PreprocessResult(image=img, gray=gray, resize_factor=1.0, original_size=(w, h), status="ok"), coins


def make_templates():
    pre, coins = make_faces([("THB_1", 60, 0, None), ("THB_5", 60, 0, None)])
    return build_templates([(pre.gray, coins[0], "THB_1"), (pre.gray, coins[1], "THB_5")])


def test_match_is_rotation_and_size_invariant():
    templates = make_templates()
    pre, coins = make_faces([("THB_5", 42, 73, None), ("THB_1", 75, -140, None)], seed=1)
    s5 = match_scores(pre.gray, coins[0], templates, ["THB_1", "THB_5"])
    s1 = match_scores(pre.gray, coins[1], templates, ["THB_1", "THB_5"])
    assert decide(s5)[0] == "THB_5"
    assert decide(s1)[0] == "THB_1"


def test_match_tilted_coin():
    """ภาพเอียง ~28° (แกนสั้น/ยาว 0.88) ยังจับคู่ถูก"""
    templates = make_templates()
    pre, coins = make_faces([("THB_5", 55, 20, (0.88, 35)), ("THB_1", 55, 200, (0.88, -60))], seed=2)
    assert decide(match_scores(pre.gray, coins[0], templates, ["THB_1", "THB_5"]))[0] == "THB_5"
    assert decide(match_scores(pre.gray, coins[1], templates, ["THB_1", "THB_5"]))[0] == "THB_1"


def test_templates_resolve_ambiguous_scale():
    """เหรียญ 5 บาทล้วนขนาดเดียว: ไม่มี template ต้องถาม anchor, มี template ระบบตัดสินเองได้"""
    pre, coins = make_faces([("THB_5", 50, 10, None), ("THB_5", 50, 130, None), ("THB_5", 50, 250, None)], seed=3)
    res = classify_coins(pre, coins)
    assert res.scale_mm_per_px is None and res.total_baht is None

    res = classify_coins(pre, coins, templates=make_templates())
    assert [c.coin_type for c in res.coins] == ["THB_5"] * 3
    assert res.total_baht == 15.0
    assert res.scale_source == "inferred"                     # ระบบประเมินเอง ไม่ใช่ผู้ใช้เลือก
    assert all(c.source == "estimated" for c in res.coins)
    # เป็นแค่การเดาจากลวดลาย ยังให้ผู้ใช้ยืนยัน
    assert res.status == "needs_confirmation" and "ลวดลาย" in res.reason
    assert all(c.status == "needs_confirmation" and c.confidence <= 0.5 for c in res.coins)


def test_conflicting_patterns_ask_user():
    """ขนาดเท่ากันแต่ลวดลายบอก 1 กับ 5 ขัดกัน ต้องไม่เลือกข้างใดข้างหนึ่งเอง"""
    pre, coins = make_faces([("THB_1", 50, 10, None), ("THB_5", 50, 130, None), ("THB_5", 50, 250, None)], seed=5)
    templates = make_templates()
    assert [decide(match_scores(pre.gray, c, templates, ["THB_1", "THB_5"]))[0] for c in coins] == \
        ["THB_1", "THB_5", "THB_5"]
    res = classify_coins(pre, coins, templates=templates)
    assert res.status == "needs_confirmation"
    assert res.scale_mm_per_px is None and res.total_baht is None
    assert all(c.coin_type is None for c in res.coins)


def test_similar_patterns_ask_user():
    """ลวดลายของสองชนิดเหมือนกันมาก (เช่น ด้านหัว) margin ไม่พอ ต้องไม่เดา"""
    pre, coins = make_faces([("THB_1", 60, 0, None), ("THB_1", 60, 0, None)])
    same = build_templates([(pre.gray, coins[0], "THB_1"), (pre.gray, coins[1], "THB_5")])
    pre, coins = make_faces([("THB_1", 50, 40, None), ("THB_1", 50, 160, None)], seed=6)
    res = classify_coins(pre, coins, templates=same)
    assert res.scale_mm_per_px is None
    assert all(c.coin_type is None for c in res.coins)


def test_zero_radius_coin_does_not_crash():
    pre, coins = make_faces([("THB_5", 50, 10, None), ("THB_5", 50, 130, None)], seed=7)
    coins.append(Coin(coin_id=2, center_xy=(10.0, 10.0), radius_px=0.0))
    assert match_scores(pre.gray, coins[2], make_templates(), ["THB_1", "THB_5"]) == {}
    classify_coins(pre, coins, templates=make_templates())


def test_template_from_tilted_coin_picks_major_axis():
    """angle ของ ellipse อาจเป็นของแกนสั้น (detection เรียงแกนใหม่) template ต้องออกมาเหมือนกัน"""
    pre, coins = make_faces([("THB_5", 60, 0, (0.8, 30))], seed=8)
    major, minor, angle = coins[0].ellipse
    swapped = coins[0].model_copy(update=dict(ellipse=(major, minor, angle + 90.0)))
    a = build_templates([(pre.gray, coins[0], "THB_5")])["THB_5"][0]
    b = build_templates([(pre.gray, swapped, "THB_5")])["THB_5"][0]
    assert _ncc_max(a, b) > 0.99          # เหมือนกันเมื่อหมุน (angle+180 = หมุนครึ่งรอบ)
    wrong = coin_features(pre.gray, coins[0])
    assert min(_ncc_max(a, f) for f in wrong) < 0.95   # อีกแบบที่ยืดผิดแกนต่างออกไปจริง


def test_plain_coin_still_asks_user():
    """เหรียญไม่มีลวดลายให้เทียบ ต้องไม่เดา ยังขอ anchor จากผู้ใช้"""
    pre, coins = make_faces([(None, 50, 0, None), (None, 50, 0, None)], seed=4)
    res = classify_coins(pre, coins, templates=make_templates())
    assert res.scale_mm_per_px is None
    assert res.status == "needs_confirmation"
    assert all(c.coin_type is None for c in res.coins)
