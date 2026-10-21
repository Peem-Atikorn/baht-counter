import numpy as np

from modules.classification import mock_classify_coins, total_baht
from modules.detection import mock_detect_coins
from modules.preprocess import mock_preprocess
from schemas import Coin, CountResult


def test_mock_chain_matches_schema():
    pre = mock_preprocess(np.zeros((3000, 4000, 3), np.uint8))
    assert max(pre.gray.shape) == 1600
    coins = mock_detect_coins(pre)
    result = mock_classify_coins(pre, coins)
    CountResult.model_validate(result.model_dump())
    assert result.status == "needs_confirmation"
    assert result.total_baht is None  # มีเหรียญที่ระบุไม่ได้ ห้ามรวมเป็นตัวเลข


def test_anchor_resolves_confirmation():
    pre = mock_preprocess(np.zeros((600, 800, 3), np.uint8))
    coins = mock_detect_coins(pre)
    result = mock_classify_coins(pre, coins, anchor=(5, "THB_10"))
    assert result.status == "ok"
    assert result.scale_source == "user_anchor"
    assert result.total_baht == 18.75


def test_total_baht_none_when_unknown():
    coins = [
        Coin(coin_id=0, center_xy=(0, 0), radius_px=1, value_baht=5.0),
        Coin(coin_id=1, center_xy=(0, 0), radius_px=1, value_baht=None),
    ]
    assert total_baht(coins) is None
    assert total_baht(coins[:1]) == 5.0
