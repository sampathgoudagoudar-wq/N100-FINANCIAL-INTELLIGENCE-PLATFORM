import pytest
from src.analytics import cashflow_kpis as K


def test_fcf_negative_allowed():
    assert K.free_cash_flow(100, -300) == -200

def test_cfo_pat_none_when_pat_zero():
    assert K.cfo_pat_ratio(100, 0) is None

def test_cfo_quality_high():
    s, l = K.cfo_quality_score([(120, 100)] * 5)
    assert s == pytest.approx(1.2) and l == K.HIGH_QUALITY

def test_cfo_quality_moderate_and_accrual_risk():
    assert K.cfo_quality_score([(70, 100)] * 5)[1] == K.MODERATE
    assert K.cfo_quality_score([(30, 100)] * 5)[1] == K.ACCRUAL_RISK

def test_cfo_quality_needs_min_years():
    assert K.cfo_quality_score([(100, 100), (100, 100)]) == (None, None)

def test_capex_intensity_labels():
    assert K.capex_intensity_label(K.capex_intensity(-20, 1000)) == K.ASSET_LIGHT
    assert K.capex_intensity_label(K.capex_intensity(-50, 1000)) == K.CAPEX_MODERATE
    assert K.capex_intensity_label(K.capex_intensity(-200, 1000)) == K.CAPITAL_INTENSIVE

def test_fcf_conversion_none_for_zero_operating_profit():
    assert K.fcf_conversion(50, 0) is None and K.fcf_conversion(50, 100) == pytest.approx(50.0)

@pytest.mark.parametrize("cfo,cfi,cff,cfopat,label", [
    (1, -1, -1, 0.5, "Reinvestor"), (1, -1, -1, 1.5, "Shareholder Returns"), (1, 1, -1, None, "Liquidating Assets"),
    (-1, 1, 1, None, "Distress Signal"), (-1, -1, 1, None, "Growth Funded by Debt"), (1, 1, 1, None, "Cash Accumulator"),
    (-1, -1, -1, None, "Pre-Revenue"), (1, -1, 1, None, "Mixed"), (-1, 1, -1, None, "Asset Sales Fund Outflows"),
    (0, -1, -1, None, "Undetermined"), (None, -1, -1, None, "Undetermined"),
])
def test_capital_allocation_patterns(cfo, cfi, cff, cfopat, label):
    assert K.capital_allocation_pattern(cfo, cfi, cff, cfopat) == label
