"""ส่วนที่ 3: จัดกลุ่มสี หาสเกล จำแนกชนิด และรวมยอด

    classify_coins(pre, coins, anchor=None) -> CountResult    # วิธีหลัก: สี + หาสเกล
    classify_coins_baseline(pre, coins, mm_per_px)           # วิธีพื้นฐานสำหรับเปรียบเทียบ
    mock_classify_coins(pre, coins, anchor=None) -> CountResult
"""
from .baseline import classify_coins_baseline, fit_baseline_scale, radius_ranges_px
from .classify import classify_coins, diameter_px, summarize
from .coin_specs import COIN_CODES, COIN_SPECS, GROUP_TYPES
from .debug import draw_color_groups
from .mock import mock_classify_coins, total_baht

__all__ = [
    "classify_coins", "classify_coins_baseline", "fit_baseline_scale", "radius_ranges_px",
    "diameter_px", "summarize", "total_baht", "mock_classify_coins", "draw_color_groups",
    "COIN_CODES", "COIN_SPECS", "GROUP_TYPES",
]
