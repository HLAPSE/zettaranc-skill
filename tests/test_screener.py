"""
screener.py 选股测试
"""

from modules.indicators import calculate_ma
from modules.screener import (
    analyze_stock,
    calculate_bbi,
    calculate_kdj,
    calculate_vol_ma,
    format_stock_score,
    get_all_stocks,
    get_recent_klines,
    is_perfect_pattern,
    score_b1_opportunity,
    score_risk,
    score_trend,
    score_volume_pattern,
    screen_stocks,
)
from modules.screener.models import MarketStatus, StockScore
from tests.conftest import generate_downtrend_klines, generate_uptrend_klines


class TestStockScore:
    def test_rating_excellent(self):
        s = StockScore(ts_code="600519.SH", score=85)
        assert "★" in s.rating

    def test_rating_poor(self):
        s = StockScore(ts_code="600519.SH", score=10)
        assert "★" in s.rating


class TestMarketStatus:
    def test_defaults(self):
        ms = MarketStatus(trade_date="20260428")
        assert ms.is_trading is True
        assert ms.market_direction == "NEUTRAL"


class TestCalculateMA:
    def test_basic(self):
        assert calculate_ma([1, 2, 3, 4, 5], 5) == 3.0

    def test_insufficient(self):
        assert calculate_ma([1], 5) == 0


class TestCalculateVolMA:
    def test_basic(self):
        assert calculate_vol_ma([100, 200, 300, 400, 500], 5) == 300.0

    def test_insufficient(self):
        assert calculate_vol_ma([100], 5) == 0


class TestCalculateKDJ:
    def test_returns_tuple(self):
        klines = generate_uptrend_klines(n=20)
        k, d, j = calculate_kdj(klines)
        assert isinstance(k, float)

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        k, d, j = calculate_kdj(klines)
        assert (k, d, j) == (50, 50, 50)


class TestCalculateBBI:
    def test_basic(self):
        klines = generate_uptrend_klines(n=30)
        bbi = calculate_bbi(klines)
        assert bbi > 0

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        assert calculate_bbi(klines) == 0


class TestIsPerfectPattern:
    def test_uptrend_perfect(self):
        klines = generate_uptrend_klines(n=50)
        is_perfect, reasons = is_perfect_pattern(klines)
        assert isinstance(is_perfect, bool)
        assert isinstance(reasons, list)

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        is_perfect, reasons = is_perfect_pattern(klines)
        assert is_perfect is False
        assert "数据不足" in reasons


class TestScoreB1Opportunity:
    def test_uptrend_low_score(self):
        klines = generate_uptrend_klines(n=50)
        score, reasons = score_b1_opportunity(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, reasons = score_b1_opportunity(klines)
        assert score == 0
        assert "数据不足" in reasons


class TestScoreTrend:
    def test_uptrend(self):
        klines = generate_uptrend_klines(n=50, daily_pct=1.0)
        score, direction = score_trend(klines)
        assert 0 <= score <= 100
        assert any(direction.startswith(d) for d in ("上升", "下降", "震荡"))

    def test_downtrend(self):
        klines = generate_downtrend_klines(n=50)
        score, direction = score_trend(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, direction = score_trend(klines)
        assert score == 50
        assert direction == "震荡"


class TestScoreVolumePattern:
    def test_basic(self):
        klines = generate_uptrend_klines(n=20)
        score, reasons = score_volume_pattern(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=5)
        score, reasons = score_volume_pattern(klines)
        assert score == 50
        assert "数据不足" in reasons


class TestScoreRisk:
    def test_uptrend_low_risk(self):
        klines = generate_uptrend_klines(n=70)
        score, warnings = score_risk(klines)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        klines = generate_uptrend_klines(n=10)
        score, warnings = score_risk(klines)
        assert score == 50
        assert "数据不足" in warnings


class TestScreenerShim:
    """验证 modules.screener shim 仍导出公共 API"""

    def test_shim_exports_public_api(self):
        import modules.screener as shim

        public_names = [
            "StockScore",
            "MarketStatus",
            "get_all_stocks",
            "get_recent_klines",
            "analyze_stock",
            "screen_stocks",
            "format_stock_score",
            "daily_workflow",
            "is_perfect_pattern",
            "score_b1_opportunity",
            "score_trend",
            "score_volume_pattern",
            "score_risk",
            "calculate_kdj",
            "calculate_bbi",
            "calculate_vol_ma",
        ]
        for name in public_names:
            assert hasattr(shim, name), f"shim 缺少 {name}"
