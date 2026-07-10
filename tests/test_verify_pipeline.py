"""v1.0 验收管线测试"""
from __future__ import annotations

import os

import pytest

from modules.verify.pipeline import (
    AggregateMetrics,
    GateResult,
    StockResult,
    VerifyResult,
    _load_klines_with_precheck,
    _run_single_stock_backtest,
    verify_v10_pipeline,
)

# 真实数据回归：未配置 TUSHARE_TOKEN 时整条测试 skip
_TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
_RUN_REALDATA = os.environ.get("RUN_REALDATA", "").lower() == "true"


def test_dataclasses_importable():
    """数据契约能被外部 import"""
    assert VerifyResult is not None
    assert StockResult is not None
    assert AggregateMetrics is not None
    assert GateResult is not None


def test_pipeline_function_exists():
    """verify_v10_pipeline 是公开 API"""
    assert callable(verify_v10_pipeline)


def test_pipeline_empty_stocks_returns_empty_result():
    """空股票列表：返回带零指标的 VerifyResult，不抛异常"""
    result = verify_v10_pipeline(ts_codes=[], days=250)
    assert isinstance(result, VerifyResult)
    assert result.per_stock == []
    assert result.aggregate.total_trades == 0
    assert result.aggregate.win_rate == 0.0


def test_load_klines_skips_short_history():
    """数据 < 60 天的股票应被标记 skipped"""
    # 真实数据缺失时自动跳过（不需要 stub）
    result = _load_klines_with_precheck(
        ts_codes=["000001.SZ", "999999.SH"],  # 999999 不存在
        days=250,
    )
    assert isinstance(result, list)
    assert any(r.skipped for r in result)
    skipped_codes = [r.ts_code for r in result if r.skipped]
    assert "999999.SH" in skipped_codes


@pytest.mark.realdata
@pytest.mark.skipif(
    not _TUSHARE_TOKEN or not _RUN_REALDATA,
    reason="需配置 TUSHARE_TOKEN 并设置 RUN_REALDATA=true 才能跑真实数据回归",
)
def test_backtest_single_real_stock_returns_metrics():
    """真实股票回测返回有效指标（无 token 时 skip）"""
    result = _run_single_stock_backtest("600519.SH", days=250)
    assert isinstance(result, StockResult)
    assert result.ts_code == "600519.SH"
    assert not result.skipped
    # 至少有一个交易或零交易（极端行情）
    assert result.trades >= 0
    assert 0.0 <= result.win_rate <= 1.0
