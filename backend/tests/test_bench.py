import pytest

from scripts.bench import parse_server_timing


def test_parse_server_timing_normal():
    header = "preprocess;dur=46.1, detection;dur=460.3, classification;dur=5.8, save;dur=120.4"
    assert parse_server_timing(header) == pytest.approx({
        "preprocess": 0.0461,
        "detection": 0.4603,
        "classification": 0.0058,
        "save": 0.1204,
    })


def test_parse_server_timing_empty_header():
    assert parse_server_timing("") == {}
    assert parse_server_timing("   ") == {}


def test_parse_server_timing_weird_whitespace():
    header = "  preprocess ; dur = 46.1  ,   detection;dur=460.3  ,,  "
    result = parse_server_timing(header)
    assert result == pytest.approx({"preprocess": 0.0461, "detection": 0.4603})
