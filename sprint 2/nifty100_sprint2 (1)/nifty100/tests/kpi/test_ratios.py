import pytest
from src.analytics import ratios as R


def test_npm_normal():
    assert R.net_profit_margin(100, 1000) == pytest.approx(10.0)

def test_npm_zero_sales_none():
    assert R.net_profit_margin(100, 0) is None

def test_npm_negative_profit_allowed():
    assert R.net_profit_margin(-50, 1000) == pytest.approx(-5.0)

def test_opm_computed():
    assert R.operating_profit_margin(200, 1000) == pytest.approx(20.0)

def test_opm_cross_check_mismatch_flagged():
    assert R.opm_mismatch(30, 20) is True

def test_opm_cross_check_within_tolerance():
    assert R.opm_mismatch(20.5, 20.0) is False

def test_roe_normal():
    assert R.return_on_equity(100, 10, 90) == pytest.approx(100.0)

def test_roe_negative_equity_none():
    assert R.return_on_equity(100, 10, -50) is None

def test_roe_zero_equity_none():
    assert R.return_on_equity(100, 0, 0) is None

def test_roce_uses_ebit_over_capital_employed():
    # EBIT = 200-50 = 150 ; capital = 100+300+100 = 500
    assert R.return_on_capital_employed(200, 50, 100, 300, 100) == pytest.approx(30.0)

def test_roce_none_if_capital_nonpositive():
    assert R.return_on_capital_employed(200, 50, 10, -100, 0) is None

def test_roa_zero_assets_none():
    assert R.return_on_assets(10, 0) is None and R.return_on_assets(10, 200) == pytest.approx(5.0)

def test_de_debt_free_is_zero_not_none():
    assert R.debt_to_equity(0, 10, 90) == 0.0

def test_de_normal_and_negative_equity():
    assert R.debt_to_equity(200, 10, 90) == pytest.approx(2.0) and R.debt_to_equity(200, 10, -50) is None

def test_high_leverage_flag_non_financial():
    assert R.high_leverage_flag(6.0, is_financial=False) is True

def test_high_leverage_flag_suppressed_for_financials():
    assert R.high_leverage_flag(12.0, is_financial=True) is False

def test_high_leverage_flag_boundary():
    assert R.high_leverage_flag(5.0, False) is False

def test_icr_normal():
    assert R.interest_coverage(100, 20, 40) == pytest.approx(3.0)

def test_icr_zero_interest_none_and_label():
    assert R.interest_coverage(100, 20, 0) is None and R.icr_label(0) == "Debt Free"

def test_icr_label_absent_when_interest_positive_or_missing():
    assert R.icr_label(5) is None and R.icr_label(None) is None

def test_icr_warning_below_1_5():
    assert R.icr_warning_flag(1.2) is True and R.icr_warning_flag(1.5) is False and R.icr_warning_flag(None) is False

def test_net_debt_uses_investments_proxy():
    assert R.net_debt(500, 120) == 380

def test_asset_turnover():
    assert R.asset_turnover(500, 250) == pytest.approx(2.0) and R.asset_turnover(500, 0) is None

def test_book_value_per_share():
    # (10+90) / (10/1) = 10
    assert R.book_value_per_share(10, 90, 1) == pytest.approx(10.0) and R.book_value_per_share(10, 90, None) is None

def test_nan_inputs_are_none():
    assert R.net_profit_margin(float("nan"), 100) is None
