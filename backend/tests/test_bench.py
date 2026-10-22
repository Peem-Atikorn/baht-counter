import pytest

from scripts.bench import parse_server_timing, summarize_row


def _outcome(request_sec: float, server_timing: dict[str, float], ok: bool = True) -> dict:
    return {"ok": ok, "request_sec": request_sec, "server_timing": server_timing}


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


def test_summarize_row_all_succeed():
    stages = {"preprocess": 0.1, "detection": 0.5, "classification": 0.05, "save": 0.1}
    outcomes = [_outcome(1.0, dict(stages)) for _ in range(3)]

    summary = summarize_row(outcomes)

    assert summary["n_total"] == 3
    assert summary["n_usable"] == 3
    assert summary["fail_count"] == 0
    assert summary["avg_request_sec"] == pytest.approx(1.0)
    assert summary["avg_other_sec"] == pytest.approx(0.25)
    for stage, seconds in stages.items():
        assert summary["stage_secs"][stage] == pytest.approx({"avg": seconds, "count": 3})


def test_summarize_row_one_of_three_fails():
    stages = {"preprocess": 0.1, "detection": 0.5, "classification": 0.05, "save": 0.1}
    outcomes = [
        _outcome(1.0, dict(stages)),
        _outcome(1.0, dict(stages)),
        _outcome(0.05, {}, ok=False),
    ]

    summary = summarize_row(outcomes)

    assert summary["n_total"] == 3
    assert summary["n_usable"] == 2
    assert summary["fail_count"] == 1
    assert summary["avg_other_sec"] >= 0
    assert summary["avg_other_sec"] == pytest.approx(0.25)
    assert summary["stage_secs"]["detection"] == pytest.approx({"avg": 0.5, "count": 2})


def test_summarize_row_all_fail():
    outcomes = [_outcome(0.05, {}, ok=False) for _ in range(3)]

    summary = summarize_row(outcomes)

    assert summary["n_total"] == 3
    assert summary["n_usable"] == 0
    assert summary["fail_count"] == 3
    assert summary["avg_request_sec"] is None
    assert summary["avg_other_sec"] is None
    assert summary["stage_secs"] == {}


def test_summarize_row_some_missing_classification_stage():
    with_classification = {"preprocess": 0.1, "detection": 0.5, "classification": 0.05, "save": 0.1}
    without_classification = {"preprocess": 0.1, "detection": 0.5, "save": 0.1}
    outcomes = [
        _outcome(1.0, dict(with_classification)),
        _outcome(1.0, dict(with_classification)),
        _outcome(0.9, dict(without_classification)),
    ]

    summary = summarize_row(outcomes)

    assert summary["n_usable"] == 3
    assert summary["stage_secs"]["preprocess"]["count"] == 3
    assert summary["stage_secs"]["classification"]["count"] == 2
    assert summary["stage_secs"]["classification"]["avg"] == pytest.approx(0.05)


def test_summarize_row_total_not_inflated_when_one_request_missing_a_stage():
    """"รวม" ต้องมาจากผลรวมต่อ request ก่อนแล้วค่อยเฉลี่ย ไม่ใช่ผลรวมของค่าเฉลี่ยแต่ละขั้น (รีวิว PR #39 ข้อ 5)
    ถ้าเอาค่าเฉลี่ยแต่ละขั้นมาบวกกัน classification จะถูกเฉลี่ยจากฐานที่เล็กกว่า (count=2 ไม่ใช่ 3) ทำให้
    "รวม" สูงเกินจริงกว่าที่ควรจะเป็น"""
    with_classification = {"preprocess": 0.1, "detection": 0.5, "classification": 0.05}
    without_classification = {"preprocess": 0.1, "detection": 0.5}
    outcomes = [
        _outcome(1.0, dict(with_classification)),
        _outcome(1.0, dict(with_classification)),
        _outcome(1.0, dict(without_classification)),
    ]

    summary = summarize_row(outcomes)

    correct_total = (0.65 + 0.65 + 0.6) / 3  # รวมต่อ request ก่อน (0.65, 0.65, 0.6) แล้วค่อยเฉลี่ย
    naive_buggy_total = 0.1 + 0.5 + 0.05  # ผลรวมของค่าเฉลี่ยแต่ละขั้น (classification เฉลี่ยจาก count=2) — ผิด

    assert summary["avg_stage_total_sec"] == pytest.approx(correct_total)
    assert summary["avg_stage_total_sec"] < naive_buggy_total
