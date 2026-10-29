import pytest
from src.analytics import cagr as C


def test_positive_positive_normal():
    v, f = C.cagr(100, 200, 5)
    assert f == C.OK and v == pytest.approx(14.8698, abs=1e-3)

def test_total_decline_to_zero_is_minus_100():
    assert C.cagr(100, 0, 3) == (pytest.approx(-100.0), C.OK)

def test_decline_to_loss():
    assert C.cagr(100, -20, 3) == (None, C.DECLINE_TO_LOSS)

def test_turnaround():
    assert C.cagr(-100, 20, 3) == (None, C.TURNAROUND)

def test_both_negative():
    assert C.cagr(-100, -20, 3) == (None, C.BOTH_NEGATIVE)

def test_zero_base():
    assert C.cagr(0, 50, 5) == (None, C.ZERO_BASE)

def test_insufficient_missing_start():
    assert C.cagr(None, 50, 5) == (None, C.INSUFFICIENT)

def test_shift_year_keeps_month():
    assert C.shift_year("2024-03", 5) == "2019-03" and C.shift_year("2023-12", 3) == "2020-12"

def test_window_cagr_uses_n_years_back():
    s = {"2019-03": 100.0, "2024-03": 200.0}
    assert C.window_cagr(s, "2024-03", 5)[1] == C.OK

def test_window_cagr_insufficient_when_start_year_absent():
    assert C.window_cagr({"2024-03": 200.0, "2021-03": 100.0}, "2024-03", 5) == (None, C.INSUFFICIENT)
